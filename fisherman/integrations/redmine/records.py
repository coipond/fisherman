"""Redmine records: what trusted users actually wrote on an issue."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fisherman.contracts import Contract, is_list_of_ints, is_regex
from fisherman.integrations.redmine.client import Client

if TYPE_CHECKING:
    from fisherman.item import Item

# Characters of each record kept; claims are checked against the gist, not whole essays
_NOTE_CHARS = 1500
_REVIEW_CHARS = 800
# Characters of a comment searched for the review pattern
_REVIEW_HEAD = 500


class RedmineRecords:
    """Collects trusted users' descriptions and comments, and integration-recorded reviews."""

    #: Contract for this plug-in's configuration section (connection settings included)
    CONTRACT = Client.CONTRACT.extend(
        Contract()
        .required("trusted_user_ids", is_list_of_ints, "must be a list of user ids")
        .optional("review_note_pattern", is_regex, "must be a valid regular expression")
    )

    def __init__(self, cfg: dict[str, Any], client: Client | None = None) -> None:
        """Create the plug-in.

        Args:
            cfg: The section: trusted_user_ids, review_note_pattern (regex for comments an
                integration posted to record a trusted person's code review, for example a
                GitHub webhook), plus the connection settings.
            client: Client to use instead of building one from `cfg`.

        """
        self._rm = client or Client.from_config(cfg)
        self._trusted = {int(i) for i in cfg.get("trusted_user_ids", [])}
        pattern = cfg.get("review_note_pattern")
        self._review = re.compile(pattern, re.DOTALL) if pattern else None
        self._cache: dict[str, list[str]] = {}

    def records(self, item: Item, extra_refs: list[str]) -> list[str] | None:
        """Return the trusted record of the item's issue, or of the referenced issues.

        Args:
            item: The item a claim was found in.
            extra_refs: Other issue ids the claim points at.

        Returns:
            None for items outside issues (wiki pages, tool output), otherwise the record.

        """
        if item.context.get("type") != "issue":
            return None
        ids = [str(r) for r in extra_refs] if extra_refs else [str(item.context["id"])]
        return [record for iid in ids for record in self._issue(iid)]

    def clear(self) -> None:
        """Forget cached records, so the next scan reads fresh ones."""
        self._cache.clear()

    def _issue(self, iid: str) -> list[str]:
        if iid not in self._cache:
            issue = (self._rm.get(f"/issues/{iid}.json", include="journals") or {}).get("issue")
            self._cache[iid] = self._collect(issue) if issue else []
        return self._cache[iid]

    def _collect(self, issue: dict[str, Any]) -> list[str]:
        found: list[str] = []
        if (issue.get("author") or {}).get("id") in self._trusted and issue.get("description"):
            found.append(issue["description"][:_NOTE_CHARS])
        for journal in issue.get("journals", []):
            note = (journal.get("notes") or "").strip()
            if not note:
                continue
            if (journal.get("user") or {}).get("id") in self._trusted:
                found.append(note[:_NOTE_CHARS])
            elif self._review and self._review.search(note[:_REVIEW_HEAD]):
                found.append("[review] " + note[:_REVIEW_CHARS])
        return found
