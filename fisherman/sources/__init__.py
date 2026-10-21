"""Source plug-ins yield new items to check.

A source has:
  name: str                               key for its checkpoint in the state file
  items(state: dict) -> Iterator[Item]    new items since the checkpoint kept in `state`
  commit(state: dict) -> None             called after every item was handled; advances the checkpoint

Items may come again after a crash; the runner skips uids it has already handled.
"""
from __future__ import annotations

from typing import Any, Dict


def build(cfg: Dict[str, Any]):
    kind = cfg.get("type")
    if kind == "jsonl":
        from .jsonl import JsonlSource
        return JsonlSource(cfg)
    if kind == "redmine":
        from .redmine import RedmineSource
        return RedmineSource(cfg)
    raise ValueError(f"unknown source type: {kind}")
