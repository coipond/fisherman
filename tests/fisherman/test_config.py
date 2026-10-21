import json
import tempfile
import unittest
from pathlib import Path

from fisherman import config
from fisherman.errors import InvalidConfigurationError
from tests.support.plugins import registered


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        cfg = config.prepare({})
        self.assertEqual(cfg["records"], {"type": "none"})
        self.assertEqual(cfg["alerts"], {"type": "stdout"})
        self.assertEqual(cfg["state_file"], config.DEFAULT_STATE_FILE)

    def test_shared_integration_settings(self):
        with registered():
            cfg = config.prepare(
                {
                    "remote": {"url": "https://rm", "key_file": "k"},
                    "sources": [{"type": "remote"}],
                    "records": {"type": "remote", "trusted_user_ids": [1]},
                    "alerts": {"type": "remote", "project": "f", "url": "https://other"},
                }
            )
        self.assertEqual(cfg["sources"][0]["url"], "https://rm")
        self.assertEqual(cfg["records"]["key_file"], "k")
        self.assertEqual(cfg["alerts"]["url"], "https://other")

    def test_every_problem_is_reported(self):
        with registered(), self.assertRaises(InvalidConfigurationError) as ctx:
            config.prepare(
                {
                    "sources": [{"type": "remote"}, {"type": "nope"}],
                    "alerts": {"type": "jsonl"},
                    "records": {"type": "remote", "url": "https://rm"},
                }
            )
        message = str(ctx.exception)
        for expected in (
            "sources[0].url: is missing",
            "sources[1].type: unknown sources type: 'nope'",
            "alerts.path: is missing",
            "records.trusted_user_ids: is missing",
        ):
            self.assertIn(expected, message)

    def test_root_contract(self):
        with self.assertRaises(InvalidConfigurationError) as ctx:
            config.prepare(
                {"pipeline": {"threshold": 3}, "sources": "x", "model": {"url": "ftp://x"}}
            )
        self.assertIn("pipeline.threshold", str(ctx.exception))
        self.assertIn("model.url", str(ctx.exception))
        self.assertIn("sources:", str(ctx.exception))

    def test_root_and_plugin_problems_together(self):
        with registered(), self.assertRaises(InvalidConfigurationError) as ctx:
            config.prepare({"pipeline": {"threshold": 3}, "sources": [{"type": "remote"}, "x"]})
        message = str(ctx.exception)
        self.assertIn("pipeline.threshold", message)
        self.assertIn("sources[0].url: is missing", message)

    def test_not_an_object(self):
        with self.assertRaises(InvalidConfigurationError):
            config.prepare([])

    def test_plugins_without_a_contract(self):
        with registered():
            config.prepare({"alerts": {"type": "unchecked"}})

    def test_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.json"
            path.write_text(json.dumps({"pipeline": {"threshold": 0.6}}))
            self.assertEqual(config.load(str(path))["pipeline"]["threshold"], 0.6)
            path.write_text("{nope")
            with self.assertRaises(InvalidConfigurationError):
                config.load(str(path))
            with self.assertRaises(InvalidConfigurationError):
                config.load(str(Path(d) / "missing.json"))

    def test_example_config_is_valid(self):
        example = Path(__file__).parents[2] / "examples" / "config.example.json"
        config.prepare(json.loads(example.read_text()))
