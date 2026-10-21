"""Redmine records: what trusted users actually wrote on an issue.

Config:
  url, key_file            may be omitted to reuse the first Redmine source's settings
  trusted_user_ids         Redmine user ids whose descriptions and comments count as the record
  review_note_pattern      regex for comments that record a trusted person's code review, posted by
                           an integration (for example a GitHub webhook). Matching comments are added
                           to the record prefixed with "[review]" (default: none)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..item import Item
from ..redmine import Redmine


class RedmineRecords:
    def __init__(self, cfg: Dict[str, Any], client: Optional[Redmine] = None, **_: Any):
        self.rm = client or Redmine.from_config(cfg)
        self.trusted = {int(i) for i in cfg.get("trusted_user_ids", [])}
        pattern = cfg.get("review_note_pattern")
        self.review = re.compile(pattern, re.S) if pattern else None
        self.cache: Dict[str, List[str]] = {}

    def records(self, item: Item, extra_refs: List[str]) -> Optional[List[str]]:
        if item.context.get("type") != "issue":
            return None  # nothing to verify against (wiki pages, tool output)
        ids = [str(r) for r in extra_refs] if extra_refs else [str(item.context["id"])]
        out: List[str] = []
        for iid in ids:
            out += self._issue(iid)
        return out

    def _issue(self, iid: str) -> List[str]:
        if iid not in self.cache:
            issue = (self.rm.get(f"/issues/{iid}.json", include="journals") or {}).get("issue")
            recs: List[str] = []
            if issue:
                if (issue.get("author") or {}).get("id") in self.trusted and issue.get("description"):
                    recs.append(issue["description"][:1500])
                for j in issue.get("journals", []):
                    note = (j.get("notes") or "").strip()
                    if not note:
                        continue
                    if (j.get("user") or {}).get("id") in self.trusted:
                        recs.append(note[:1500])
                    elif self.review and self.review.search(note[:500]):
                        recs.append("[review] " + note[:800])
            self.cache[iid] = recs
        return self.cache[iid]
