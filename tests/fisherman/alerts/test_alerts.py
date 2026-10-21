import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fisherman.alerts.jsonl import JsonlAlerts
from fisherman.alerts.stdout import StdoutAlerts
from fisherman.item import Item, Verdict

ITEM = Item("u", "text", "Agent", 5, "src", "link")
VERDICT = Verdict(alert=True, reasons=["outside send: x"], scores={"quick": 0.9})


class AlertsTest(unittest.TestCase):
    def test_stdout(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            StdoutAlerts().send(ITEM, VERDICT)
        row = json.loads(out.getvalue())
        self.assertEqual(
            (row["uid"], row["reasons"], row["text"]), ("u", ["outside send: x"], "text")
        )

    def test_jsonl_appends(self):
        with tempfile.TemporaryDirectory() as d:
            alerts = JsonlAlerts({"path": f"{d}/sub/alerts.jsonl"})
            alerts.send(ITEM, VERDICT)
            alerts.send(ITEM, VERDICT)
            lines = Path(f"{d}/sub/alerts.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["source"], "src")
