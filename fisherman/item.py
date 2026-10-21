"""The two values every part of Fisherman passes around: what to check and what was found."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Item:
    """One piece of content an agent reads or wrote.

    Attributes:
        uid: Stable id, unique per source. Used for de-duplication and in alerts.
        text: The content itself.
        author: Display name of whoever wrote it.
        author_id: The source's id for the author, if any.
        source: Human-readable origin, for example "Redmine comment on issue #123 (project Foo)".
        link: URL of the content, if any.
        context: Where the content lives, for example `{"type": "issue", "id": 123}`.
            Records plug-ins use it to find what trusted people said in the same place.
        label: Expected answer (True for an attack). Only set in evaluation sets.
        group: Evaluation group name. Only set in evaluation sets.

    """

    uid: str
    text: str
    author: str = ""
    author_id: Any = None
    source: str = ""
    link: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    label: bool | None = None
    group: str = ""


@dataclass
class Verdict:
    """The pipeline's answer for one item.

    Attributes:
        alert: Whether the item should be reported.
        reasons: Human-readable reasons, each quoting the sentence that triggered it.
        scores: Per-step results, for example `{"quick": 0.98, "reason": "no", "claims": 1}`.

    """

    alert: bool
    reasons: list[str] = field(default_factory=list)
    scores: dict[str, Any] = field(default_factory=dict)
