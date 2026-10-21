"""Source checkpoints and handled item ids, kept in one JSON file written atomically."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

#: Handled ids are remembered this long, then forgotten
KEEP_DAYS = 30


class State:
    """The scanner's memory between runs."""

    def __init__(self, path: str, keep_days: float = KEEP_DAYS) -> None:
        """Load the state file, or start empty.

        Args:
            path: State file path.
            keep_days: How long handled item ids are remembered.

        """
        self._path = Path(path).expanduser()
        self._keep = keep_days * 86400
        self.data: dict[str, Any] = {"sources": {}, "seen": {}}
        if self._path.exists():
            self.data = json.loads(self._path.read_text())
            self.data.setdefault("sources", {})
            self.data.setdefault("seen", {})

    def source(self, name: str) -> dict[str, Any]:
        """Return a source's part of the state, creating it if needed.

        Args:
            name: The source's name.

        Returns:
            The source's mutable state.

        """
        found: dict[str, Any] = self.data["sources"].setdefault(name, {})
        return found

    def replace_source(self, name: str, value: dict[str, Any]) -> None:
        """Replace a source's part of the state.

        Args:
            name: The source's name.
            value: The new state.

        """
        self.data["sources"][name] = value

    def seen(self, uid: str) -> bool:
        """Check whether an item was already handled.

        Args:
            uid: The item's uid.

        Returns:
            True when it was handled within the retention period.

        """
        return uid in self.data["seen"]

    def mark(self, uid: str) -> None:
        """Remember that an item was handled.

        Args:
            uid: The item's uid.

        """
        self.data["seen"][uid] = int(time.time())

    def save(self) -> None:
        """Drop expired ids and write the file atomically."""
        cutoff = time.time() - self._keep
        self.data["seen"] = {k: v for k, v in self.data["seen"].items() if v >= cutoff}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(self._path)
