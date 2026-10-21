"""Prints alerts as JSON lines."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fisherman.alerts.payload import payload

if TYPE_CHECKING:
    from fisherman.item import Item, Verdict


class StdoutAlerts:
    """Writes one JSON object per alert to standard output."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        """Create the plug-in.

        Args:
            cfg: Ignored.

        """
        self._cfg = cfg

    def send(self, item: Item, verdict: Verdict) -> None:
        """Print an alert.

        Args:
            item: The flagged item.
            verdict: Why it was flagged.

        """
        print(json.dumps(payload(item, verdict), ensure_ascii=False), flush=True)  # noqa: T201
