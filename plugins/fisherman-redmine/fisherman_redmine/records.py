"""Redmine records: what trusted users actually wrote on an issue, and their confirmed reviews."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fisherman.contracts import Contract, is_list_of_ints, is_regex
from fisherman_redmine.client import Client
from fisherman_redmine.github import GitHubReviews, pull_requests

if TYPE_CHECKING:
    from fisherman.item import Item

# Characters of each record kept; claims are checked against the gist, not whole essays
_NOTE_CHARS = 1500
# Characters of a comment searched for the review pattern
_REVIEW_HEAD = 500


def _pattern_needs_verification(cfg: Any) -> bool:
    return (
        not isinstance(cfg, dict)
        or "review_note_pattern" not in cfg
        or "review_verification" in cfg
    )


class RedmineRecords:
    """Collects trusted users' descriptions and comments, and their reviews confirmed by GitHub.

    Note:
        Comments that record a review (for example from a GitHub webhook pipeline) are written by
        whatever account runs that pipeline, often an agent. Their text is never trusted: they
        only point at pull requests, and the reviews themselves are read from GitHub and kept
        only when a trusted GitHub account wrote them. A forged "approved" comment therefore
        adds nothing to the record.

    """

    #: Contract for this plug-in's configuration section (connection settings included)
    CONTRACT = Client.CONTRACT.extend(
        Contract()
        .required("trusted_user_ids", is_list_of_ints, "must be a list of user ids")
        .optional("review_note_pattern", is_regex, "must be a valid regular expression")
        .nested("review_verification", GitHubReviews.CONTRACT)
        .rule(
            _pattern_needs_verification,
            "review_note_pattern needs review_verification: review comments are only pointers, "
            "the reviews are confirmed with GitHub",
        )
    )

    def __init__(
        self,
        cfg: dict[str, Any],
        client: Client | None = None,
        reviews: GitHubReviews | None = None,
    ) -> None:
        """Create the plug-in.

        Args:
            cfg: The section: trusted_user_ids, review_note_pattern (regex for comments that
                record a code review and name its pull request), review_verification (how to
                confirm those reviews with GitHub, see `GitHubReviews`), plus the connection
                settings.
            client: Client to use instead of building one from `cfg`.
            reviews: Review reader to use instead of building one from `cfg`.

        """
        self._rm = client or Client.from_config(cfg)
        self._trusted = {int(i) for i in cfg.get("trusted_user_ids", [])}
        pattern = cfg.get("review_note_pattern")
        self._review = re.compile(pattern, re.DOTALL) if pattern else None
        verification = cfg.get("review_verification")
        self._reviews = reviews or (GitHubReviews(verification) if verification else None)
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
        """Forget cached records and reviews, so the next scan reads fresh ones."""
        self._cache.clear()
        if self._reviews:
            self._reviews.clear()

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
            elif self._reviews and self._review and self._review.search(note[:_REVIEW_HEAD]):
                found.extend(
                    r
                    for pr in pull_requests(note)
                    for r in self._reviews.records(pr)
                    if r not in found
                )
        return found
