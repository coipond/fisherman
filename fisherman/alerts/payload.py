"""The JSON form of an alert, shared by the file and stdout plug-ins."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fisherman.item import Item, Verdict


def payload(item: Item, verdict: Verdict) -> dict[str, Any]:
    """Describe a flagged item.

    Args:
        item: The flagged item.
        verdict: Why it was flagged.

    Returns:
        A JSON-serialisable mapping.

    """
    return {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uid": item.uid,
        "source": item.source,
        "author": item.author,
        "link": item.link,
        "reasons": verdict.reasons,
        "scores": verdict.scores,
        "text": item.text,
    }
