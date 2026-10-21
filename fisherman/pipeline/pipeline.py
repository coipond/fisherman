"""Runs the steps and combines their results into a verdict."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fisherman.item import Item, Verdict
from fisherman.llm import Llama
from fisherman.pipeline.destinations import Destinations
from fisherman.pipeline.prompts import Prompts
from fisherman.pipeline.settings import Settings
from fisherman.pipeline.steps import ClaimCheck, QuickCheck, ReasonCheck
from fisherman.plugins import build

if TYPE_CHECKING:
    from fisherman.plugins import Records

# Longest model explanation kept in an alert reason
_REASON_CHARS = 500


class Pipeline:
    """quick check, then the reasoning check and the claim check on what it flagged.

    An item alerts when the quick check scores it at or above the threshold AND either the
    reasoning check says yes, or the claim check finds an unverified claim or an outside send.
    """

    def __init__(
        self,
        llm: Llama,
        prompts: Prompts,
        settings: Settings,
        records: Records,
        destinations: Destinations,
    ) -> None:
        """Create a pipeline.

        Args:
            llm: Model client shared by every step.
            prompts: Prompt templates.
            settings: Pipeline settings.
            records: Records plug-in for the claim check.
            destinations: Allowlist for the claim check.

        """
        self.llm = llm
        self.settings = settings
        self.records = records
        self.quick = QuickCheck(llm, prompts, settings)
        self.reason = ReasonCheck(llm, prompts, settings)
        self.claims = ClaimCheck(llm, prompts, settings, records, destinations)

    @classmethod
    def from_config(cls, cfg: dict[str, Any], steps: list[str] | None = None) -> Pipeline:
        """Build a pipeline from a validated configuration.

        Args:
            cfg: The whole configuration.
            steps: Run only these steps, overriding the configuration.

        Returns:
            The pipeline.

        """
        settings = Settings.from_config(cfg.get("pipeline", {}))
        if steps:
            settings.steps = steps
        return cls(
            Llama.from_config(cfg.get("model", {})),
            Prompts(cfg.get("prompts_dir"), cfg.get("prompt_vars")),
            settings,
            build("records", cfg.get("records", {"type": "none"})),
            Destinations.from_config(cfg.get("destinations", {})),
        )

    def run(self, item: Item) -> Verdict:
        """Check one item.

        Args:
            item: The item.

        Returns:
            The verdict.

        """
        steps = self.settings.steps
        score = self.quick.call(item) if "quick" in steps else 1.0
        scores: dict[str, Any] = {"quick": round(score, 4)}
        if score < self.settings.threshold:
            return Verdict(alert=False, scores=scores)
        reasons: list[str] = []
        if "reason" in steps:
            reasoned = self.reason.call(item)
            scores["reason"] = reasoned.verdict
            if reasoned.verdict == "yes":
                reasons.append("reasoning: " + (reasoned.risky or "risky request")[:_REASON_CHARS])
        if "claims" in steps:
            claimed = self.claims.call(item)
            scores["claims"] = len(claimed.reasons)
            reasons.extend(claimed.reasons)
        return Verdict(alert=bool(reasons), reasons=reasons, scores=scores)
