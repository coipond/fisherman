import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fisherman import cli
from fisherman.item import Verdict
from fisherman.processing.evaluator import Report


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.config = Path(self.dir.name) / "c.json"
        self.config.write_text(json.dumps({"state_file": f"{self.dir.name}/s.json"}))

    def run_cli(self, *args, stdin=""):
        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main([*args, "--config", str(self.config)])
        return code, out.getvalue()

    def test_check(self):
        pipeline = mock.Mock()
        pipeline.run.return_value = Verdict(
            alert=True, reasons=["outside send: x"], scores={"quick": 1}
        )
        with mock.patch("fisherman.cli.Pipeline.from_config", return_value=pipeline):
            code, out = self.run_cli("check", stdin="gem push")
        self.assertEqual(code, cli.EXIT_ALERT)
        self.assertEqual(json.loads(out)["reasons"], ["outside send: x"])
        pipeline.run.return_value = Verdict(alert=False)
        with mock.patch("fisherman.cli.Pipeline.from_config", return_value=pipeline):
            self.assertEqual(self.run_cli("check", stdin="fine")[0], cli.EXIT_OK)

    def test_scan_and_run(self):
        with mock.patch("fisherman.cli.Scanner") as scanner:
            scanner.return_value.scan.return_value = 2
            self.assertEqual(self.run_cli("scan"), (cli.EXIT_OK, "2 alerts\n"))
            self.run_cli("run", "--interval", "60")
            scanner.return_value.run_forever.assert_called_with(60)

    def test_eval(self):
        items = Path(self.dir.name) / "set.jsonl"
        items.write_text(json.dumps({"text": "x", "label": True, "group": "a"}))
        out_file = Path(self.dir.name) / "out.json"
        report = Report(
            caught=1, attacks=1, groups={"a": {"flagged": 1, "total": 1}}, results=[{"uid": "x"}]
        )
        with (
            mock.patch("fisherman.cli.Evaluator") as evaluator,
            mock.patch("fisherman.cli.Pipeline.from_config") as build,
        ):
            evaluator.return_value.call.return_value = report
            code, out = self.run_cli(
                "eval", str(items), "--steps", "quick,reason", "--out", str(out_file)
            )
        self.assertEqual(code, cli.EXIT_OK)
        self.assertEqual(build.call_args.args[1], ["quick", "reason"])
        self.assertIn("caught 1/1 | false alarms 0/0", out)
        self.assertIn("a: flagged 1/1", out)
        self.assertEqual(json.loads(out_file.read_text()), [{"uid": "x"}])

    def test_configuration_errors_exit_cleanly(self):
        self.config.write_text(json.dumps({"pipeline": {"threshold": 5}}))
        with self.assertLogs("fisherman", "ERROR"):
            self.assertEqual(self.run_cli("scan")[0], cli.EXIT_ERROR)
