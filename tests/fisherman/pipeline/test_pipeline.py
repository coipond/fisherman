import unittest

from fisherman.item import Item
from fisherman.pipeline import Destinations, Pipeline, Prompts
from fisherman.pipeline.settings import Settings
from fisherman.records.none import NoRecords
from tests.support.fakes import FakeLLM, extraction


def make(llm, records=None, **settings):
    return Pipeline(
        llm,
        Prompts(variables={"principal": "Alice"}),
        Settings.from_config(settings),
        records or NoRecords(),
        Destinations(["my-org"]),
    )


def issue(text):
    return Item("t", text, "Agent A", 5, "comment", "", {"type": "issue", "id": 100})


class PipelineTest(unittest.TestCase):
    def test_below_threshold_stops_after_the_quick_check(self):
        llm = FakeLLM(risky="publish")
        verdict = make(llm).run(issue("Opened PR #5, CI green."))
        self.assertFalse(verdict.alert)
        self.assertEqual(llm.calls, ["quick"])
        self.assertEqual(verdict.scores, {"quick": 0.1})

    def test_reasoning_yes_alerts_with_the_risky_request(self):
        llm = FakeLLM("publish", lambda s, u: "REQUESTS: x\nRISKY: publishing to npm\nVERDICT: yes")
        verdict = make(llm, steps=["quick", "reason"]).run(issue("Next: publish to npm."))
        self.assertTrue(verdict.alert)
        self.assertEqual(verdict.reasons, ["reasoning: publishing to npm"])

    def test_reasoning_no_and_clean_claims_do_not_alert(self):
        def answers(system, user):
            return (
                extraction() if "Extract" in system else "REQUESTS: none\nRISKY: none\nVERDICT: no"
            )

        verdict = make(FakeLLM("publish", answers)).run(issue("publish docs"))
        self.assertFalse(verdict.alert)
        self.assertEqual(verdict.scores, {"quick": 0.9, "reason": "no", "claims": 0})

    def test_claims_alone_can_alert(self):
        answers = lambda s, u: extraction(sends=[("Mirrored to github.com/x/y.", "github.com/x/y")])  # noqa: E731
        verdict = make(FakeLLM(".", answers), steps=["quick", "claims"]).run(issue("x"))
        self.assertEqual(verdict.reasons, ["outside send: Mirrored to github.com/x/y."])

    def test_without_the_quick_step_every_item_is_judged(self):
        llm = FakeLLM(answers=lambda s, u: "VERDICT: no")
        verdict = make(llm, steps=["reason"]).run(issue("anything"))
        self.assertEqual(llm.calls, ["reason"])
        self.assertEqual(verdict.scores["quick"], 1.0)

    def test_from_config_builds_every_part(self):
        cfg = {
            "model": {"url": "http://127.0.0.1:1"},
            "pipeline": {"threshold": 0.7},
            "destinations": {"github_owners": ["a"]},
        }
        pipeline = Pipeline.from_config(cfg, steps=["quick"])
        self.assertEqual(pipeline.settings.threshold, 0.7)
        self.assertEqual(pipeline.settings.steps, ["quick"])
        self.assertIsInstance(pipeline.records, NoRecords)
