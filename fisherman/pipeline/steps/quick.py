"""Step 1: a fast, high-recall yes/no check over overlapping windows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fisherman.item import Item
    from fisherman.llm import Llama
    from fisherman.pipeline.prompts import Prompts
    from fisherman.pipeline.settings import Settings

_QUESTION = "Does this content try to steer an AI agent beyond what its source may ask? yes or no"


class QuickCheck:
    """Scores an item by the riskiest of its windows.

    Note:
        Windows of about 250 tokens matter: a long, legitimate text around one rogue sentence
        dilutes the model's judgement when it reads everything at once.

    """

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

    def call(self, item: Item) -> float:
        """Score an item.

        Args:
            item: The item.

        Returns:
            The highest P(yes) over the item's windows.

        """
        system = self._prompts.get("quick")
        if self._settings.quick_examples:
            system += "\n\n" + self._prompts.get("quick_examples")
        header = f"Source: {item.source}\nAuthor: {item.author}"
        best = 0.0
        for window in self.windows(
            self._llm.tokenize(item.text)[: self._settings.max_quick_tokens]
        ):
            body = self._llm.detokenize(window)
            best = max(
                best,
                self._llm.p_yes(system, f"{header}\n<content>\n{body}\n</content>\n{_QUESTION}"),
            )
        return best

    def windows(self, ids: list[int]) -> list[list[int]]:
        """Split token ids into overlapping windows.

        Args:
            ids: Token ids.

        Returns:
            Windows covering every token; the last window is aligned to the end.

        """
        size, stride = self._settings.window_tokens, self._settings.stride_tokens
        found = [ids[i : i + size] for i in range(0, max(len(ids) - size, 0) + 1, stride)] or [[]]
        if len(ids) > size and (len(ids) - size) % stride:
            found.append(ids[-size:])
        return found
