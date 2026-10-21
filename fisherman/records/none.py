"""Records plug-in for setups with nothing to verify against."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fisherman.item import Item


class NoRecords:
    """Treats every authority claim as unverifiable, so each one raises an alert."""

    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        """Create the plug-in.

        Args:
            cfg: Ignored.

        """
        self._cfg = cfg

    def records(self, item: Item, extra_refs: list[str]) -> list[str] | None:  # noqa: ARG002
        """Return an empty record.

        Args:
            item: Ignored.
            extra_refs: Ignored.

        Returns:
            An empty list: checked, and nobody trusted said anything.

        """
        return []
