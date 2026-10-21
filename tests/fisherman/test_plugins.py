import sys
import unittest
from unittest import mock

from fisherman import plugins
from fisherman.alerts.stdout import StdoutAlerts
from fisherman.errors import UnknownPluginError
from fisherman.records.none import NoRecords


class EntryPoint:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class PluginsTest(unittest.TestCase):
    def test_builtins(self):
        self.assertIs(plugins.resolve("alerts", "stdout"), StdoutAlerts)
        self.assertNotIn("redmine", str(plugins.BUILTIN))
        self.assertIsInstance(plugins.build("records", {"type": "none"}), NoRecords)

    def test_dotted_path(self):
        self.assertIs(plugins.resolve("records", "fisherman.records.none:NoRecords"), NoRecords)

    def test_entry_points(self):
        found = [EntryPoint("mine", "fisherman.records.none:NoRecords")]
        if sys.version_info < (3, 10):
            found = {"fisherman.records": found}  # Python 3.9 returns a mapping of groups
        with mock.patch("importlib.metadata.entry_points", return_value=found):
            self.assertIs(plugins.resolve("records", "mine"), NoRecords)

    def test_unknown(self):
        with self.assertRaises(UnknownPluginError):
            plugins.resolve("alerts", "nope")
        with self.assertRaises(UnknownPluginError):
            plugins.resolve("alerts", "fisherman.nope:Thing")
        with self.assertRaises(UnknownPluginError):
            plugins.resolve("alerts", "fisherman.records.none:Nope")
