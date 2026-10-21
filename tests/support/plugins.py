"""A fake integration, registered under the type "remote" by `registered()`."""

from __future__ import annotations

from unittest import mock

from fisherman.contracts import Contract, is_list_of_ints, is_string, is_url
from fisherman.plugins import BUILTIN

CONNECTION = (
    Contract()
    .required("url", is_url, "must be an http(s) URL")
    .optional("key_file", is_string, "x")
)


class RemoteSource:
    CONTRACT = CONNECTION

    def __init__(self, cfg):
        self.cfg = cfg


class RemoteRecords:
    CONTRACT = CONNECTION.extend(
        Contract().required("trusted_user_ids", is_list_of_ints, "must be a list of user ids")
    )

    def __init__(self, cfg):
        self.cfg = cfg


class RemoteAlerts:
    CONTRACT = CONNECTION.extend(Contract().required("project", is_string, "must be a project"))

    def __init__(self, cfg):
        self.cfg = cfg


class Unchecked:
    def __init__(self, cfg):
        self.cfg = cfg


def registered():
    """Patch the registry so "remote" resolves to the classes above."""
    entries = {
        "sources": {"remote": "tests.support.plugins:RemoteSource"},
        "records": {"remote": "tests.support.plugins:RemoteRecords"},
        "alerts": {
            "remote": "tests.support.plugins:RemoteAlerts",
            "unchecked": "tests.support.plugins:Unchecked",
        },
    }
    merged = {kind: {**BUILTIN[kind], **extra} for kind, extra in entries.items()}
    return mock.patch.dict("fisherman.plugins.BUILTIN", merged)
