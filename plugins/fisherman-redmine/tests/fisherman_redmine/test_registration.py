import unittest

from fisherman import config, plugins
from fisherman_redmine.alerts import RedmineAlerts
from fisherman_redmine.records import RedmineRecords
from fisherman_redmine.source import RedmineSource


class RegistrationTest(unittest.TestCase):
    """Needs the package installed (pip install -e .), as entry points come from its metadata."""

    def test_entry_points(self):
        self.assertIs(plugins.resolve("sources", "redmine"), RedmineSource)
        self.assertIs(plugins.resolve("records", "redmine"), RedmineRecords)
        self.assertIs(plugins.resolve("alerts", "redmine"), RedmineAlerts)

    def test_shared_settings_and_contracts(self):
        cfg = config.prepare(
            {
                "redmine": {"url": "https://rm", "key_file": "k"},
                "sources": [{"type": "redmine"}],
                "records": {"type": "redmine", "trusted_user_ids": [1]},
                "alerts": {"type": "redmine", "project": "fisherman"},
            }
        )
        self.assertEqual(cfg["alerts"]["url"], "https://rm")
