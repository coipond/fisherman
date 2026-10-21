"""Plug-in interfaces and the registry that resolves a configured `type` to a class.

There are three kinds of plug-ins:

- sources yield items to check,
- records tell the claim check what trusted people actually said,
- alerts receive flagged items.

A `type` is resolved, in order, as:

1. a built-in name (`jsonl`, `none`, `stdout`) or a bundled integration (`redmine`),
2. a name another package registered under the `fisherman.sources`, `fisherman.records` or
   `fisherman.alerts` entry point group,
3. a `package.module:Class` path.

Every plug-in class is built with its configuration section as the only argument and may define
a `CONTRACT` (a `fisherman.contracts.Contract`) for that section.
"""

from __future__ import annotations

import importlib
import sys
from importlib import metadata
from typing import TYPE_CHECKING, Any, Protocol

from fisherman.errors import UnknownPluginError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fisherman.item import Item, Verdict

#: Plug-in kinds and the built-in types of each
BUILTIN: dict[str, dict[str, str]] = {
    "sources": {
        "jsonl": "fisherman.sources.jsonl:JsonlSource",
        "redmine": "fisherman.integrations.redmine.source:RedmineSource",
    },
    "records": {
        "none": "fisherman.records.none:NoRecords",
        "redmine": "fisherman.integrations.redmine.records:RedmineRecords",
    },
    "alerts": {
        "stdout": "fisherman.alerts.stdout:StdoutAlerts",
        "jsonl": "fisherman.alerts.jsonl:JsonlAlerts",
        "redmine": "fisherman.integrations.redmine.alerts:RedmineAlerts",
    },
}


class Source(Protocol):
    """Yields new items to check."""

    #: Key of the source's checkpoint in the state file
    name: str

    def items(self, state: dict[str, Any]) -> Iterator[Item]:
        """Yield items that are new since the checkpoint kept in `state`.

        Args:
            state: This source's part of the state file. The source may read and change it.

        Returns:
            An iterator of items.

        """
        ...

    def commit(self, state: dict[str, Any]) -> None:
        """Advance the checkpoint after every yielded item was handled.

        Args:
            state: This source's part of the state file.

        """
        ...


class Records(Protocol):
    """Answers what trusted people actually said in an item's context."""

    def records(self, item: Item, extra_refs: list[str]) -> list[str] | None:
        """Return the record for the item's context, or for the contexts in `extra_refs`.

        Args:
            item: The item a claim was found in.
            extra_refs: Ids of other contexts the claim points at (for example issue numbers).
                When given, the records of those contexts are returned instead.

        Returns:
            None when there is nothing to verify against in this kind of context, otherwise the
            trusted statements (possibly none). Integration-recorded reviews are prefixed with
            "[review] ".

        """
        ...


class Alerts(Protocol):
    """Receives flagged items."""

    def send(self, item: Item, verdict: Verdict) -> None:
        """Report one flagged item.

        Args:
            item: The flagged item.
            verdict: Why it was flagged.

        """
        ...


def resolve(kind: str, type_name: str) -> type[Any]:
    """Find the class for a configured plug-in type.

    Args:
        kind: "sources", "records" or "alerts".
        type_name: The configured `type`.

    Returns:
        The plug-in class.

    Raises:
        UnknownPluginError: When the type cannot be found or imported.

    """
    target = BUILTIN.get(kind, {}).get(type_name) or _entry_point(kind, type_name)
    if target is None and ":" in type_name:
        target = type_name
    if target is None:
        msg = f"unknown {kind} type: {type_name!r}"
        raise UnknownPluginError(msg)
    module_name, _, attr = target.partition(":")
    try:
        found: type[Any] = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as e:
        msg = f"cannot load {kind} type {type_name!r} from {target!r}: {e}"
        raise UnknownPluginError(msg) from e
    return found


def build(kind: str, cfg: dict[str, Any]) -> Any:
    """Build a plug-in from its configuration section.

    Args:
        kind: "sources", "records" or "alerts".
        cfg: The section; its `type` selects the plug-in.

    Returns:
        The plug-in instance.

    """
    return resolve(kind, str(cfg.get("type", "")))(cfg)


def _entry_point(kind: str, type_name: str) -> str | None:
    group = f"fisherman.{kind}"
    if sys.version_info >= (3, 10):
        candidates = metadata.entry_points(group=group)
    else:  # Python 3.9 returns a mapping of groups
        candidates = metadata.entry_points().get(group, [])
    for point in candidates:
        if point.name == type_name:
            return str(point.value)
    return None
