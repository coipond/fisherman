"""Reads every source, checks new items and sends alerts."""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from fisherman.errors import ModelUnavailableError
from fisherman.pipeline import Pipeline
from fisherman.plugins import build
from fisherman.processing.chunker import chunks
from fisherman.processing.state import State

log = logging.getLogger("fisherman")

#: Shortest pause between scans, whatever the interval
MIN_PAUSE = 30


class Scanner:
    """One scanner per configuration."""

    def __init__(self, cfg: dict[str, Any], pipeline: Pipeline | None = None) -> None:
        """Create a scanner.

        Args:
            cfg: A validated configuration.
            pipeline: Pipeline to use instead of building one from `cfg`.

        """
        self._cfg = cfg
        self._pipeline = pipeline or Pipeline.from_config(cfg)
        self._alerts = build("alerts", cfg["alerts"])

    def scan(self) -> int:
        """Run one pass over every source.

        An item whose check fails is logged and retried on the next scan; its source's
        checkpoint is left where it was, so nothing is skipped.

        Returns:
            The number of alerts sent.

        Raises:
            ModelUnavailableError: When the model server is not reachable. Nothing is read then.

        """
        if not self._pipeline.llm.health():
            msg = f"model server not reachable at {self._pipeline.llm.url}"
            raise ModelUnavailableError(msg)
        state = State(self._cfg["state_file"])
        sent = sum(self._scan_source(source_cfg, state) for source_cfg in self._cfg["sources"])
        clear = getattr(self._pipeline.records, "clear", None)
        if callable(clear):
            clear()
        return sent

    def run_forever(self, interval: int) -> None:
        """Scan, wait, repeat. Failed scans are logged and retried at the next interval.

        Args:
            interval: Seconds from the start of one scan to the start of the next.

        """
        while True:
            started = time.time()
            try:
                log.info("scan done: %d alerts in %.0fs", self.scan(), time.time() - started)
            except Exception:
                log.exception("scan failed")
            time.sleep(max(MIN_PAUSE, interval - (time.time() - started)))

    def _scan_source(self, source_cfg: dict[str, Any], state: State) -> int:
        source = build("sources", source_cfg)
        source_state = state.source(source.name)
        before = copy.deepcopy(source_state)
        handled = failed = sent = 0
        for item in source.items(source_state):
            for part in chunks(item, self._pipeline.settings.max_item_chars):
                if state.seen(part.uid):
                    continue
                try:
                    verdict = self._pipeline.run(part)
                except Exception:
                    log.exception("%s: check failed, retrying next scan", part.uid)
                    failed += 1
                    continue
                log.info(
                    "%s quick=%s alert=%s", part.uid, verdict.scores.get("quick"), verdict.alert
                )
                if verdict.alert:
                    self._alerts.send(part, verdict)
                    sent += 1
                state.mark(part.uid)
                handled += 1
                state.save()
        if failed:
            log.warning("source %s: %d items failed; checkpoint kept", source.name, failed)
            state.replace_source(source.name, before)
        else:
            source.commit(source_state)
        state.save()
        log.info("source %s: %d items checked", source.name, handled)
        return sent
