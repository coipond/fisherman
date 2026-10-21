"""Appends alerts to a JSON Lines file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fisherman.alerts.payload import payload
from fisherman.contracts import Contract, is_string

if TYPE_CHECKING:
    from fisherman.item import Item, Verdict


class JsonlAlerts:
    """Writes one JSON object per alert to a file."""

    #: Contract for this plug-in's configuration section
    CONTRACT = Contract().required("path", is_string, "must be a file path")

    def __init__(self, cfg: dict[str, Any]) -> None:
        """Create the plug-in.

        Args:
            cfg: The section: path.

        """
        self._path = Path(cfg["path"]).expanduser()

    def send(self, item: Item, verdict: Verdict) -> None:
        """Append an alert.

        Args:
            item: The flagged item.
            verdict: Why it was flagged.

        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload(item, verdict), ensure_ascii=False) + "\n")
