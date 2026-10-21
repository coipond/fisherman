import unittest

from fisherman.pipeline.settings import STEPS, Settings


class SettingsTest(unittest.TestCase):
    def test_defaults_and_unknown_keys(self):
        settings = Settings.from_config({"threshold": 0.6, "unknown": 1})
        self.assertEqual(settings.threshold, 0.6)
        self.assertEqual(settings.steps, list(STEPS))

    def test_a_single_step_string(self):
        self.assertEqual(Settings.from_config({"steps": "quick"}).steps, ["quick"])

    def test_contract(self):
        errors = Settings.CONTRACT.errors(
            {"threshold": 2, "steps": ["nope"], "rule_page_pattern": "("}, "pipeline"
        )
        self.assertEqual(len(errors), 3)
        self.assertEqual(Settings.CONTRACT.errors({"steps": ["quick", "claims"]}), [])
