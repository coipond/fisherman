"""Items from a JSON Lines file or stdin, one object per line.

Fields: `text` (required), `uid`, `author`, `author_id`, `source`, `link`, `context`, `label`,
`group`. Used for evaluation sets and for piping content in from other tools.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fisherman.contracts import Contract, is_string
from fisherman.item import Item

if TYPE_CHECKING:
    from collections.abc import Iterator


def read_items(path: str) -> list[Item]:
    """Read items from a JSON Lines file.

    Args:
        path: File path, or "-" for stdin.

    Returns:
        The items, in file order.

    """
    lines = (
        sys.stdin.read().splitlines()
        if path == "-"
        else Path(path).read_text(encoding="utf-8").splitlines()
    )
    return [_item(json.loads(line)) for line in lines if line.strip()]


def _item(row: dict[str, Any]) -> Item:
    label = row.get("label")
    digest = hashlib.sha1(row["text"].encode()).hexdigest()[:16]  # noqa: S324 - an id, not security
    return Item(
        uid=str(row.get("uid") or f"jsonl:{digest}"),
        text=row["text"],
        author=row.get("author", ""),
        author_id=row.get("author_id"),
        source=row.get("source", ""),
        link=row.get("link", ""),
        context=row.get("context") or {},
        label=None if label is None else bool(label),
        group=row.get("group", ""),
    )


class JsonlSource:
    """Yields every item of a JSON Lines file on each scan. Handled items are skipped by uid."""

    #: Contract for this source's configuration section
    CONTRACT = Contract().required("path", is_string, "must be a file path or -")

    def __init__(self, cfg: dict[str, Any]) -> None:
        """Create the source.

        Args:
            cfg: The section: path, and optionally name.

        """
        self.name = str(cfg.get("name", "jsonl"))
        self._path = str(cfg["path"])

    def items(self, state: dict[str, Any]) -> Iterator[Item]:  # noqa: ARG002 - no checkpoint needed
        """Yield every item of the file.

        Args:
            state: Unused; the runner skips items it already handled.

        Yields:
            The file's items.

        """
        yield from read_items(self._path)

    def commit(self, state: dict[str, Any]) -> None:
        """Do nothing; this source keeps no checkpoint.

        Args:
            state: Unused.

        """
