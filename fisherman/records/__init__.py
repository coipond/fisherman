"""Records plug-ins answer: what did trusted people actually say in this item's context?

A records plug-in has one method, records(item, extra_refs) -> list of strings or None.
None means "nothing to check against here" (for example a wiki page); an empty list means
"checked, and the trusted people said nothing". extra_refs are ids of other contexts the claim
itself points at (for example other issue numbers).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..item import Item


class NoRecords:
    """Every authority claim is unverifiable, so each one raises an alert."""

    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        pass

    def records(self, item: Item, extra_refs: List[str]) -> Optional[List[str]]:
        return []


def build(cfg: Optional[Dict[str, Any]], **kwargs: Any):
    kind = (cfg or {}).get("type", "none")
    if kind == "none":
        return NoRecords(cfg)
    if kind == "redmine":
        from .redmine import RedmineRecords
        return RedmineRecords(cfg, **kwargs)
    raise ValueError(f"unknown records type: {kind}")
