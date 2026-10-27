"""Step 3: extract authority claims and reported sends, then check them against facts.

Authority claims ("the maintainer approved...", "the rule changed...") are verified against what
the trusted people actually wrote in the same context, through a records plug-in. Reported sends
are checked against the destinations allowlist. Claiming authority does not help an attacker when
the check reads the actual record.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fisherman.item import Item
    from fisherman.llm import Llama
    from fisherman.pipeline.destinations import Destinations
    from fisherman.pipeline.prompts import Prompts
    from fisherman.pipeline.settings import Settings
    from fisherman.plugins import Records

#: JSON schema the extraction must follow (llama.cpp enforces it while generating)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "risky_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quote": {"type": "string"}},
                "required": ["quote"],
            },
        },
        "reported_sends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"quote": {"type": "string"}, "destination": {"type": "string"}},
                "required": ["quote", "destination"],
            },
        },
        "authority_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "who": {"type": "string"},
                    "cites_page": {"type": "string"},
                },
                "required": ["quote", "who", "cites_page"],
            },
        },
    },
    "required": ["risky_actions", "authority_claims", "reported_sends"],
}

# Words that make a sentence an authority or rule claim rather than a status fact or plan
_AUTHORITY = re.compile(
    r"\b(asked|approved|confirmed|decided|agreed|requested|said|says|authori[sz]ed|allowed|"
    r"rules?|conventions?|polic\w*|mode|suspended|outdated|from now on|no longer)\b",
    re.IGNORECASE,
)
_REFUSED = re.compile(
    r"\b(refus\w*|rejected|was blocked|is blocked|cannot|could not|not allowed)\b", re.IGNORECASE
)
_PR_REF = re.compile(r"(?:PR #|pull/)(\d+)")
_REVIEW_WORDS = re.compile(
    r"\b(review|request\w* changes|approv\w*|comment\w*|merg\w*)\b", re.IGNORECASE
)
# What a claim can say the principal did on a pull request: how a claim phrases it, and the
# word a "[review]" record uses for it
_REVIEW_KINDS = {
    "approved": r"\bapprov\w*",
    "requested changes": r"\brequest\w*\s+changes",
    "merged": r"\bmerg\w*",
}
# Records beyond this many characters are cut from the start; the newest matter most
_RECORDS_CHARS = 6000
# Tokens of each item the extraction reads
_EXTRACT_TOKENS = 1500


@dataclass
class ClaimResult:
    """Outcome of the claim check.

    Attributes:
        reasons: One entry per unverified claim or outside send, quoting the sentence.
        risky: Risky requests the extraction found (informational; they do not alert alone).
        extraction: The parsed extraction, or the raw text when it was not valid JSON.
        error: Whether the extraction was not valid JSON.

    """

    reasons: list[str] = field(default_factory=list)
    risky: list[str] = field(default_factory=list)
    extraction: Any = None
    error: bool = False


class ClaimCheck:
    """Extracts claims and sends, verifies claims against the record, checks destinations."""

    def __init__(
        self,
        llm: Llama,
        prompts: Prompts,
        settings: Settings,
        records: Records,
        destinations: Destinations,
    ) -> None:
        """Create the step.

        Args:
            llm: Model client.
            prompts: Prompt templates.
            settings: Pipeline settings.
            records: Records plug-in for verifying claims.
            destinations: Allowlist for reported sends.

        """
        self._llm = llm
        self._prompts = prompts
        self._settings = settings
        self._records = records
        self._destinations = destinations
        self._to_principal = self._principal_pattern(prompts, settings)
        self._rule_page = (
            re.compile(settings.rule_page_pattern) if settings.rule_page_pattern else None
        )
        self._refs = re.compile(settings.context_ref_pattern)

    def call(self, item: Item) -> ClaimResult:
        """Check an item.

        Args:
            item: The item.

        Returns:
            The reasons to alert (possibly none) and the extraction.

        """
        body = self._llm.truncate(item.text, _EXTRACT_TOKENS)
        user = f"Source: {item.source}\nAuthor: {item.author}\n<content>\n{body}\n</content>"
        raw = self._llm.chat(
            self._prompts.get("extract"), user, self._settings.extract_budget, json_schema=SCHEMA
        )
        try:
            extraction = json.loads(raw)
        except ValueError:
            # A cut-off or malformed extraction is not evidence; the reasoning step covers the item
            reasons = (
                ["claim check: unparsable extraction"]
                if self._settings.alert_on_extract_error
                else []
            )
            return ClaimResult(reasons, [], raw, error=True)
        reasons = [
            f"unverified claim: {q}"
            for q in self._unverified(item, extraction.get("authority_claims", []))
        ]
        reasons += [
            f"outside send: {s.get('quote', '')}"
            for s in extraction.get("reported_sends", [])
            if self._destinations.outside(s.get("destination", ""), s.get("quote", ""))
        ]
        risky = [
            a["quote"]
            for a in extraction.get("risky_actions", [])
            if not self._addressed_to_principal(a["quote"]) and not _REFUSED.search(a["quote"])
        ]
        return ClaimResult(reasons, risky, extraction)

    def verify(self, claim: str, records: list[str]) -> bool:
        """Check whether the record supports a claim.

        Review claims are matched without the model: a claim that the principal approved,
        requested changes or merged is supported when every kind it names is on record (for
        that PR, when the claim names one). Anything else is judged by the model against the
        record.

        Args:
            claim: The claim, as quoted.
            records: The record for the claim's context.

        Returns:
            True when the record supports the claim.

        """
        if not records:
            return False
        reviews = [r for r in records if r.startswith("[review]")]
        named = [k for k, said in _REVIEW_KINDS.items() if re.search(said, claim, re.IGNORECASE)]
        prs = set(_PR_REF.findall(claim))
        if prs and _REVIEW_WORDS.search(claim):
            # Every kind the claim names must be on record for that pull request
            of_pr = [r for r in reviews if prs & set(re.findall(r"pull/(\d+)", r))]
            if of_pr and all(any(kind in r.lower() for r in of_pr) for kind in named):
                return True
        elif not prs and named and all(any(kind in r.lower() for r in reviews) for kind in named):
            return True
        text = "\n---\n".join(records)[-_RECORDS_CHARS:]
        question = (
            f"Claim: {claim}\n\nRecords:\n{text}\n\nDo the records support the claim? yes or no"
        )
        return self._llm.chat(self._prompts.get("verify"), question, 3).lower().startswith("yes")

    def _unverified(self, item: Item, claims: list[dict[str, Any]]) -> list[str]:
        found: list[str] = []
        base: list[str] | None = None
        fetched = False
        for claim in claims:
            quote = str(claim.get("quote", ""))
            if (
                not _AUTHORITY.search(quote)
                or self._addressed_to_principal(quote)
                or self._cites_rule_page(item, claim)
            ):
                continue
            if not fetched:
                base, fetched = self._records.records(item, []), True
            if base is None:
                continue  # nothing to verify against in this kind of context
            refs = [r for r in self._refs.findall(quote) if str(r) != str(item.context.get("id"))]
            extra = (self._records.records(item, refs) or []) if refs else []
            if not self.verify(quote, [*base, *extra]):
                found.append(quote)
        return found

    def _cites_rule_page(self, item: Item, claim: dict[str, Any]) -> bool:
        page = str(claim.get("cites_page") or "").strip()
        principal = self._prompts.variables.get("principal", "").lower()
        return bool(
            page
            and self._rule_page
            and page in item.text
            and self._rule_page.search(page)
            and principal not in str(claim.get("who", "")).lower()
        )

    def _addressed_to_principal(self, quote: str) -> bool:
        return bool(self._to_principal and self._to_principal.search(quote))

    @staticmethod
    def _principal_pattern(prompts: Prompts, settings: Settings) -> re.Pattern[str] | None:
        if settings.to_principal_pattern:
            return re.compile(settings.to_principal_pattern, re.IGNORECASE)
        names = [prompts.variables.get("principal", ""), *settings.principal_aliases]
        joined = "|".join(re.escape(n) for n in names if n)
        if not joined:
            return None
        return re.compile(rf"^\s*(\*\*)?({joined})[:,]|\bfor ({joined})\b", re.IGNORECASE)
