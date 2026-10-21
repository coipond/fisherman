"""Alert plug-ins receive every flagged item: send(item, verdict) -> None."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ..item import Item, Verdict


def record(item: Item, verdict: Verdict) -> Dict[str, Any]:
    return {"time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "uid": item.uid, "source": item.source,
            "author": item.author, "link": item.link, "reasons": verdict.reasons, "scores": verdict.scores,
            "text": item.text}


class StdoutAlerts:
    def __init__(self, cfg: Dict[str, Any]):
        pass

    def send(self, item: Item, verdict: Verdict) -> None:
        print(json.dumps(record(item, verdict), ensure_ascii=False), flush=True)


class JsonlAlerts:
    def __init__(self, cfg: Dict[str, Any]):
        self.path = Path(cfg["path"]).expanduser()

    def send(self, item: Item, verdict: Verdict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record(item, verdict), ensure_ascii=False) + "\n")


def build(cfg: Dict[str, Any]):
    kind = cfg.get("type", "stdout")
    if kind == "stdout":
        return StdoutAlerts(cfg)
    if kind == "jsonl":
        return JsonlAlerts(cfg)
    if kind == "redmine":
        from .redmine import RedmineAlerts
        return RedmineAlerts(cfg)
    raise ValueError(f"unknown alerts type: {kind}")

