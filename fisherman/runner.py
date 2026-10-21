"""Wires the configured plug-ins together and runs scans and evaluations."""
from __future__ import annotations

import copy
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Iterator, List, Optional

from . import alerts as alerts_mod
from . import records as records_mod
from . import sources as sources_mod
from .destinations import Destinations
from .item import Item, Verdict
from .llm import Llama
from .pipeline import Pipeline
from .prompts import Prompts
from .state import State

log = logging.getLogger("fisherman")


def build_pipeline(cfg: Dict[str, Any], stages: Optional[List[str]] = None) -> Pipeline:
    pcfg = dict(cfg["pipeline"])
    if stages:
        pcfg["stages"] = stages
    dest = cfg.get("destinations", {})
    return Pipeline(
        Llama.from_config(cfg["model"]),
        Prompts(cfg.get("prompts_dir"), cfg.get("prompt_vars")),
        pcfg,
        records_mod.build(cfg["records"]),
        Destinations(dest.get("github_owners", []), dest.get("hosts", []), **({"registries": dest["registries"]} if "registries" in dest else {})),
    )


def chunks(item: Item, max_chars: int) -> Iterator[Item]:
    """Long items are split at line boundaries so every part gets a full look."""
    if len(item.text) <= max_chars:
        yield item
        return
    part, size, n = [], 0, 0
    lines = item.text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        part.append(line)
        size += len(line)
        if size >= max_chars or i == len(lines) - 1:
            n += 1
            yield Item(f"{item.uid}:part{n}", "".join(part), item.author, item.author_id, f"{item.source} (part {n})",
                       item.link, item.context, item.label, item.group)
            part, size = [], 0


def scan(cfg: Dict[str, Any]) -> int:
    """One pass over every source. Returns the number of alerts."""
    pipeline = build_pipeline(cfg)
    if not pipeline.llm.health():
        raise RuntimeError(f"model server not reachable at {pipeline.llm.url}")
    alerts = alerts_mod.build(cfg["alerts"])
    state = State(cfg["state_file"])
    max_chars = int(cfg["pipeline"].get("max_item_chars", 4000))
    count = 0
    for scfg in cfg["sources"]:
        source = sources_mod.build(scfg)
        sstate = state.source(source.name)
        before = copy.deepcopy(sstate)
        handled = failed = 0
        for item in source.items(sstate):
            for part in chunks(item, max_chars):
                if state.seen(part.uid):
                    continue
                try:
                    verdict = pipeline.run(part)
                except Exception:
                    log.exception("%s: check failed, will retry next scan", part.uid)
                    failed += 1
                    continue
                log.info("%s quick=%s alert=%s", part.uid, verdict.scores.get("quick"), verdict.alert)
                if verdict.alert:
                    alerts.send(part, verdict)
                    count += 1
                state.mark(part.uid)
                handled += 1
                state.save()
        if failed:
            log.warning("source %s: %d items failed; checkpoint kept so they are read again", source.name, failed)
            state.data["sources"][source.name] = before
        else:
            source.commit(sstate)
        state.save()
        log.info("source %s: %d items checked", source.name, handled)
    if hasattr(pipeline.records, "cache"):
        pipeline.records.cache.clear()
    return count


def run_forever(cfg: Dict[str, Any], interval: int) -> None:
    while True:
        started = time.time()
        try:
            n = scan(cfg)
            log.info("scan done: %d alerts in %.0fs", n, time.time() - started)
        except Exception:
            log.exception("scan failed")
        time.sleep(max(30, interval - (time.time() - started)))


def evaluate(cfg: Dict[str, Any], items: List[Item], stages: Optional[List[str]] = None) -> Dict[str, Any]:
    """Runs labelled items through the pipeline and counts caught attacks and false alarms per group."""
    pipeline = build_pipeline(cfg, stages)
    groups: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    results = []
    for n, item in enumerate(items, 1):
        try:
            v: Verdict = pipeline.run(item)
        except Exception as e:
            log.exception("%s: check failed", item.uid)
            v = Verdict(False, [f"error: {e}"], {"error": True})
        g = groups[item.group or ("attack" if item.label else "benign")]
        g[0] += v.alert
        g[1] += 1
        results.append({"uid": item.uid, "group": item.group, "label": item.label, "alert": v.alert,
                        "reasons": v.reasons, "scores": v.scores})
        log.info("%d/%d %s label=%s alert=%s", n, len(items), item.uid, item.label, v.alert)
    attacks = [r for r in results if r["label"]]
    benign = [r for r in results if r["label"] is False]
    return {
        "caught": sum(r["alert"] for r in attacks), "attacks": len(attacks),
        "false_alarms": sum(r["alert"] for r in benign), "benign": len(benign),
        "groups": {k: {"flagged": a, "total": t} for k, (a, t) in groups.items()},
        "results": results,
    }
