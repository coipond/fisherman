import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fisherman import config
from fisherman.errors import ModelUnavailableError
from fisherman.item import Item, Verdict
from fisherman.processing import Scanner
from fisherman.processing.state import State


class ScriptedPipeline:
    """Alerts on texts containing "bad", fails on texts containing "boom"."""

    def __init__(self, *, healthy=True):
        self.llm = mock.Mock(url="http://fake")
        self.llm.health.return_value = healthy
        self.settings = mock.Mock(max_item_chars=4000)
        self.records = mock.Mock()
        self.checked = []

    def run(self, item):
        self.checked.append(item.uid)
        if "boom" in item.text:
            raise RuntimeError("model hiccup")
        return Verdict("bad" in item.text, ["bad"] if "bad" in item.text else [], {"quick": 1})


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.set = Path(self.dir.name) / "items.jsonl"
        self.alerts = Path(self.dir.name) / "alerts.jsonl"
        self.state = Path(self.dir.name) / "state.json"

    def cfg(self, rows):
        self.set.write_text("\n".join(json.dumps(r) for r in rows))
        return config.prepare(
            {
                "sources": [{"type": "jsonl", "path": str(self.set)}],
                "alerts": {"type": "jsonl", "path": str(self.alerts)},
                "state_file": str(self.state),
            }
        )

    def test_scan_alerts_once_and_remembers(self):
        pipeline = ScriptedPipeline()
        scanner = Scanner(
            self.cfg([{"uid": "1", "text": "fine"}, {"uid": "2", "text": "bad"}]), pipeline
        )
        self.assertEqual(scanner.scan(), 1)
        self.assertEqual(scanner.scan(), 0)
        self.assertEqual(pipeline.checked, ["1", "2"])
        self.assertEqual(len(self.alerts.read_text().splitlines()), 1)
        pipeline.records.clear.assert_called()

    def test_failed_items_are_retried_and_keep_the_checkpoint(self):
        pipeline = ScriptedPipeline()
        scanner = Scanner(
            self.cfg([{"uid": "1", "text": "boom"}, {"uid": "2", "text": "fine"}]), pipeline
        )
        with self.assertLogs("fisherman", "WARNING"):
            scanner.scan()
        self.assertFalse(State(str(self.state)).seen("1"))
        self.assertTrue(State(str(self.state)).seen("2"))
        with self.assertLogs("fisherman", "WARNING"):
            scanner.scan()
        self.assertEqual(pipeline.checked, ["1", "2", "1"])

    def test_model_down_reads_nothing(self):
        pipeline = ScriptedPipeline(healthy=False)
        with self.assertRaises(ModelUnavailableError):
            Scanner(self.cfg([{"text": "bad"}]), pipeline).scan()
        self.assertEqual(pipeline.checked, [])

    def test_run_forever_survives_a_failed_scan(self):
        scanner = Scanner(self.cfg([]), ScriptedPipeline(healthy=False))
        with (
            mock.patch("time.sleep", side_effect=[None, KeyboardInterrupt]),
            self.assertLogs("fisherman"),
            self.assertRaises(KeyboardInterrupt),
        ):
            scanner.run_forever(60)

    def test_long_items_are_split(self):
        pipeline = ScriptedPipeline()
        pipeline.settings.max_item_chars = 200
        Scanner(self.cfg([{"uid": "1", "text": "\n".join(["line " * 10] * 20)}]), pipeline).scan()
        self.assertTrue(all(uid.startswith("1:part") for uid in pipeline.checked))

    def test_builds_its_own_pipeline(self):
        self.assertIsNotNone(Scanner(self.cfg([]))._pipeline)

    def test_item_helper(self):
        self.assertEqual(Item("u", "t").author, "")
