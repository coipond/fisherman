"""Items from a JSON Lines file or stdin, one object per line.

Fields: text (required), uid, author, author_id, source, link, context, label, group.
Used for evaluation sets and for piping content in from other tools.
"""
from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Dict, Iterator, List

from ..item import Item


def read_items(path: str) -> List[Item]:
    stream = sys.stdin if path == "-" else open(path, encoding="utf-8")
    items = []
    with stream:
        for n, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            label = row.get("label")
            items.append(Item(
                uid=str(row.get("uid") or "jsonl:" + hashlib.sha1(row["text"].encode()).hexdigest()[:16]),
                text=row["text"],
                author=row.get("author", ""),
                author_id=row.get("author_id"),
                source=row.get("source", ""),
                link=row.get("link", ""),
                context=row.get("context") or {},
                label=None if label is None else bool(label),
                group=row.get("group", ""),
            ))
    return items


class JsonlSource:
    def __init__(self, cfg: Dict[str, Any]):
        self.name = cfg.get("name", "jsonl")
        self.path = cfg["path"]

    def items(self, state: Dict[str, Any]) -> Iterator[Item]:
        yield from read_items(self.path)

    def commit(self, state: Dict[str, Any]) -> None:
        pass
