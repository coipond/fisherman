import unittest

from fisherman.item import Item, Verdict
from fisherman.processing import Evaluator


class Pipeline:
    def run(self, item):
        if item.text == "boom":
            raise RuntimeError("down")
        return Verdict("bad" in item.text)


class EvaluatorTest(unittest.TestCase):
    def test_counts(self):
        items = [
            Item("1", "bad", label=True, group="attack"),
            Item("2", "meh", label=True, group="attack"),
            Item("3", "bad", label=False, group="hard"),
            Item("4", "fine", label=False),
            Item("5", "boom", label=False),
            Item("6", "bad"),
        ]
        with self.assertLogs("fisherman"):
            report = Evaluator(Pipeline()).call(items)
        self.assertEqual(
            (report.caught, report.attacks, report.false_alarms, report.benign), (1, 2, 1, 3)
        )
        self.assertEqual(report.groups["attack"], {"flagged": 1, "total": 2})
        self.assertEqual(report.groups["benign"], {"flagged": 1, "total": 3})
        self.assertEqual(report.results[4]["reasons"], ["error: down"])
