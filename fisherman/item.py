"""The two values every part of Fisherman passes around: what to check and what was found."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Item:
    """One piece of content an agent reads or wrote.

    uid: stable id, unique per source (used for de-duplication and alerts)
    text: the content itself
    author: display name of whoever wrote it
    author_id: the source's id for the author, if any (used to skip trusted authors)
    source: human-readable description, e.g. "Redmine comment on issue #123 (project Foo)"
    link: URL to the content, if any
    context: where it lives, e.g. {"type": "issue", "id": 123}; records plug-ins use it
    label: expected answer (True = attack), only set in evaluation sets
    group: evaluation set name, only set in evaluation sets
    """

    uid: str
    text: str
    author: str = ""
    author_id: Optional[Any] = None
    source: str = ""
    link: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    label: Optional[bool] = None
    group: str = ""


@dataclass
class Verdict:
    """The pipeline's answer for one item."""

    alert: bool
    reasons: List[str] = field(default_factory=list)
    scores: Dict[str, Any] = field(default_factory=dict)
