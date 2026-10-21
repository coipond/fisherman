"""Splits long items so every part gets a full look."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fisherman.item import Item

if TYPE_CHECKING:
    from collections.abc import Iterator


def chunks(item: Item, max_chars: int) -> Iterator[Item]:
    """Split an item at line boundaries.

    Args:
        item: The item.
        max_chars: Parts are cut once they reach this size.

    Yields:
        The item itself when short enough, otherwise its parts with uids ending in ":partN".

    """
    if len(item.text) <= max_chars:
        yield item
        return
    part: list[str] = []
    size = n = 0
    lines = item.text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        part.append(line)
        size += len(line)
        if size >= max_chars or i == len(lines) - 1:
            n += 1
            yield Item(
                f"{item.uid}:part{n}",
                "".join(part),
                item.author,
                item.author_id,
                f"{item.source} (part {n})",
                item.link,
                item.context,
                item.label,
                item.group,
            )
            part, size = [], 0
