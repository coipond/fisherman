"""Redmine alerts: one issue per flagged item, in a project no agent can see.

Config:
  url, key_file      an account that may add issues to the alerts project
  project            identifier of the alerts project (keep it private, with no agent members)
  assigned_to_id     optional user id to assign alerts to
  tracker_id         optional tracker id
  max_text_chars     how much of the flagged content to include (default 4000)
"""
from __future__ import annotations

import html
from typing import Any, Dict, Optional

from ..item import Item, Verdict
from ..redmine import Redmine


def _pre(text: str) -> str:
    return "<pre>\n" + html.escape(text, quote=False) + "\n</pre>"


class RedmineAlerts:
    def __init__(self, cfg: Dict[str, Any], client: Optional[Redmine] = None):
        self.rm = client or Redmine.from_config(cfg)
        self.project = cfg["project"]
        self.assignee = cfg.get("assigned_to_id")
        self.tracker = cfg.get("tracker_id")
        self.max_text = int(cfg.get("max_text_chars", 4000))

    def body(self, item: Item, verdict: Verdict) -> Dict[str, Any]:
        first = verdict.reasons[0] if verdict.reasons else "flagged"
        subject = f"[fisherman] {item.author or 'unknown'}: {first}".replace("\n", " ")[:250]
        scores = ", ".join(f"{k}={v}" for k, v in verdict.scores.items())
        description = "\n\n".join([
            "Fisherman flagged content that may steer an AI agent beyond what its source may ask.",
            f"Source: {item.source}\nAuthor: {item.author} (id {item.author_id})\nLink: {item.link}\nScores: {scores}",
            "Reasons:\n" + _pre("\n".join(verdict.reasons)),
            "Flagged content:\n" + _pre(item.text[:self.max_text]),
            f"Item id: {item.uid}",
        ])
        issue: Dict[str, Any] = {"project_id": self.project, "subject": subject, "description": description}
        if self.assignee:
            issue["assigned_to_id"] = self.assignee
        if self.tracker:
            issue["tracker_id"] = self.tracker
        return {"issue": issue}

    def send(self, item: Item, verdict: Verdict) -> None:
        self.rm.request("POST", "/issues.json", body=self.body(item, verdict))
