"""Redmine alerts: one issue per flagged item, in a project no agent can see."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

from fisherman.contracts import Contract, is_int_at_least, is_string
from fisherman.integrations.redmine.client import Client

if TYPE_CHECKING:
    from fisherman.item import Item, Verdict

# First paragraph of every alert
_INTRO = "Fisherman flagged content that may steer an AI agent beyond what its source may ask."
# Longest issue subject Redmine accepts comfortably
_SUBJECT_CHARS = 250


def _pre(text: str) -> str:
    return "<pre>\n" + html.escape(text, quote=False) + "\n</pre>"


class RedmineAlerts:
    """Creates a Redmine issue for every alert."""

    #: Contract for this plug-in's configuration section (connection settings included)
    CONTRACT = Client.CONTRACT.extend(
        Contract()
        .required("project", is_string, "must be the alerts project identifier")
        .optional("assigned_to_id", is_int_at_least(1), "must be a user id")
        .optional("tracker_id", is_int_at_least(1), "must be a tracker id")
        .optional("max_text_chars", is_int_at_least(100), "must be an integer >= 100")
    )

    def __init__(self, cfg: dict[str, Any], client: Client | None = None) -> None:
        """Create the plug-in.

        Args:
            cfg: The section: project (keep it private, with no agent members),
                assigned_to_id, tracker_id, max_text_chars (default 4000), plus the
                connection settings.
            client: Client to use instead of building one from `cfg`.

        """
        self._rm = client or Client.from_config(cfg)
        self._project = cfg["project"]
        self._assignee = cfg.get("assigned_to_id")
        self._tracker = cfg.get("tracker_id")
        self._max_text = int(cfg.get("max_text_chars", 4000))

    def body(self, item: Item, verdict: Verdict) -> dict[str, Any]:
        """Build the issue for an alert.

        The flagged content is HTML-escaped inside a `<pre>` block, so it renders as text and
        cannot inject markup into the alerts project.

        Args:
            item: The flagged item.
            verdict: Why it was flagged.

        Returns:
            The request body for POST /issues.json.

        """
        first = verdict.reasons[0] if verdict.reasons else "flagged"
        subject = f"[fisherman] {item.author or 'unknown'}: {first}".replace("\n", " ")[
            :_SUBJECT_CHARS
        ]
        scores = ", ".join(f"{k}={v}" for k, v in verdict.scores.items())
        description = "\n\n".join(
            [
                _INTRO,
                (
                    f"Source: {item.source}\nAuthor: {item.author} (id {item.author_id})\n"
                    f"Link: {item.link}\nScores: {scores}"
                ),
                "Reasons:\n" + _pre("\n".join(verdict.reasons)),
                "Flagged content:\n" + _pre(item.text[: self._max_text]),
                f"Item id: {item.uid}",
            ]
        )
        issue: dict[str, Any] = {
            "project_id": self._project,
            "subject": subject,
            "description": description,
        }
        if self._assignee:
            issue["assigned_to_id"] = self._assignee
        if self._tracker:
            issue["tracker_id"] = self._tracker
        return {"issue": issue}

    def send(self, item: Item, verdict: Verdict) -> None:
        """Create the alert issue.

        Args:
            item: The flagged item.
            verdict: Why it was flagged.

        """
        self._rm.post("/issues.json", self.body(item, verdict))
