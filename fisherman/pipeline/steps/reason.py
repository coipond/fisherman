"""Step 2: the model reasons about every request in the item, then gives a verdict."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fisherman.item import Item
    from fisherman.llm import Llama
    from fisherman.pipeline.prompts import Prompts
    from fisherman.pipeline.settings import Settings


@dataclass
class ReasonResult:
    """Outcome of the reasoning check.

    Attributes:
        verdict: "yes", "no", or "none" when the model gave no verdict (for example because it
            ran out of its token budget).
        risky: What the model named as risky, or "".
        analysis: The model's full answer, reasoning excluded.

    """

    verdict: str
    risky: str
    analysis: str


class ReasonCheck:
    """Asks the model to list the requests aimed at agents and judge each one."""

    def __init__(self, llm: Llama, prompts: Prompts, settings: Settings) -> None:
        """Create the step.

        Args:
            llm: Model client.
            prompts: Prompt templates.
            settings: Pipeline settings.

        """
        self._llm = llm
        self._prompts = prompts
        self._settings = settings

    def call(self, item: Item) -> ReasonResult:
        """Judge an item.

        Args:
            item: The item.

        Returns:
            The verdict and the model's analysis.

        """
        body = self._llm.truncate(item.text, self._settings.max_reason_tokens)
        user = f"Source: {item.source}\nAuthor: {item.author}\n<content>\n{body}\n</content>"
        text = self._llm.chat(
            self._prompts.get("reason"), user, self._settings.reason_budget, think=True
        )
        verdict = re.search(r"VERDICT:\s*(yes|no)", text, re.IGNORECASE)
        risky = re.search(r"RISKY:\s*(.+?)(?:\nVERDICT|$)", text, re.DOTALL)
        return ReasonResult(
            verdict.group(1).lower() if verdict else "none",
            risky.group(1).strip() if risky else "",
            text,
        )
