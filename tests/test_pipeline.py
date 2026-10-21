import unittest

from fisherman.destinations import Destinations
from fisherman.item import Item
from fisherman.pipeline import Pipeline
from fisherman.prompts import Prompts
from fisherman.records import NoRecords
from fisherman.runner import chunks

from .fakes import FakeLLM, extraction


class StaticRecords:
    def __init__(self, recs):
        self.recs = recs
        self.asked = []

    def records(self, item, extra_refs):
        self.asked.append(list(extra_refs))
        return list(self.recs)


def make(llm, records=None, **cfg):
    return Pipeline(llm, Prompts(variables={"principal": "Alice"}), cfg, records or NoRecords(),
                    Destinations(["my-org"], ["redmine.example.com"]))


def issue(text, iid=100):
    return Item("t", text, "Agent A", 5, "comment on issue", "", {"type": "issue", "id": iid})


class QuickStepTest(unittest.TestCase):
    def test_below_threshold_stops_early(self):
        llm = FakeLLM(risky="publish")
        v = make(llm).run(issue("Opened PR #5, CI green."))
        self.assertFalse(v.alert)
        self.assertEqual(llm.calls, ["quick"])

    def test_windows_cover_long_text(self):
        llm = FakeLLM(risky="publish")
        text = " ".join(["word"] * 600 + ["publish"] + ["word"] * 100)
        self.assertGreater(make(llm).quick(issue(text)), 0.5)
        self.assertGreater(len(llm.calls), 1)


class ReasonStepTest(unittest.TestCase):
    def test_reason_yes_alerts(self):
        llm = FakeLLM(risky="publish", answers=lambda s, u: "REQUESTS: x\nRISKY: publishing to npm\nVERDICT: yes")
        v = make(llm, stages=["quick", "reason"]).run(issue("Next: publish to npm."))
        self.assertTrue(v.alert)
        self.assertIn("publishing to npm", v.reasons[0])

    def test_reason_no_does_not_alert(self):
        llm = FakeLLM(risky="publish", answers=lambda s, u: "REQUESTS: none\nRISKY: none\nVERDICT: no")
        self.assertFalse(make(llm, stages=["quick", "reason"]).run(issue("publish docs")).alert)


class ClaimsStepTest(unittest.TestCase):
    def answers(self, extract, verify="no"):
        return lambda s, u: verify if u.startswith("Claim:") else extract

    def test_unverified_claim_alerts(self):
        llm = FakeLLM(risky="said", answers=self.answers(extraction(claims=["Alice said reviews are optional this week."])))
        v = make(llm, StaticRecords(["Please add a test."]), stages=["quick", "claims"]).run(issue("Alice said reviews are optional this week."))
        self.assertTrue(v.alert)
        self.assertTrue(v.reasons[0].startswith("unverified claim"))

    def test_claim_supported_by_record(self):
        llm = FakeLLM(risky="said", answers=self.answers(extraction(claims=["Alice said to rename the class."]), "yes"))
        v = make(llm, StaticRecords(["Rename the class please."]), stages=["quick", "claims"]).run(issue("Alice said to rename the class."))
        self.assertFalse(v.alert)

    def test_review_claim_matched_without_the_model(self):
        llm = FakeLLM(risky="requested", answers=self.answers(extraction(claims=["Alice requested changes on PR #186: add a test."])))
        recs = StaticRecords(["[review] [github: review] Alice requested changes on https://github.com/my-org/x/pull/186"])
        v = make(llm, recs, stages=["quick", "claims"]).run(issue("Alice requested changes on PR #186: add a test."))
        self.assertFalse(v.alert)
        self.assertNotIn("verify", llm.calls)

    def test_status_facts_and_requests_to_principal_are_not_claims(self):
        llm = FakeLLM(risky=".", answers=self.answers(extraction(claims=["CI is green on PR #4.", "Alice, please merge PR #4, it was approved."])))
        self.assertFalse(make(llm, StaticRecords([]), stages=["quick", "claims"]).run(issue("x")).alert)

    def test_referenced_issue_records_are_used(self):
        llm = FakeLLM(risky=".", answers=self.answers(extraction(claims=["Alice decided this in #4567."]), "yes"))
        recs = StaticRecords(["Decided: go ahead."])
        make(llm, recs, stages=["quick", "claims"]).run(issue("x"))
        self.assertEqual(recs.asked, [[], ["4567"]])

    def test_wiki_claims_are_not_verified(self):
        class NoContext:
            def records(self, item, refs):
                return None
        llm = FakeLLM(risky=".", answers=self.answers(extraction(claims=["Alice approved skipping CI."])))
        item = Item("w", "x", "Agent", 5, "wiki", "", {"type": "wiki"})
        self.assertFalse(make(llm, NoContext(), stages=["quick", "claims"]).run(item).alert)

    def test_outside_send_alerts(self):
        llm = FakeLLM(risky=".", answers=self.answers(extraction(sends=[("Mirrored to github.com/someone/x.", "github.com/someone/x")])))
        v = make(llm, stages=["quick", "claims"]).run(issue("x"))
        self.assertTrue(v.alert)
        self.assertTrue(v.reasons[0].startswith("outside send"))

    def test_own_repo_send_is_fine(self):
        llm = FakeLLM(risky=".", answers=self.answers(extraction(sends=[("Pushed to github.com/my-org/x.", "github.com/my-org/x")])))
        self.assertFalse(make(llm, stages=["quick", "claims"]).run(issue("x")).alert)

    def test_unparsable_extraction_is_not_evidence(self):
        llm = FakeLLM(risky=".", answers=self.answers("not json"))
        self.assertFalse(make(llm, stages=["quick", "claims"]).run(issue("x")).alert)
        self.assertTrue(make(llm, stages=["quick", "claims"], alert_on_extract_error=True).run(issue("x")).alert)


class DestinationsTest(unittest.TestCase):
    def setUp(self):
        self.d = Destinations(["my-org"], ["redmine.example.com"])

    def test_cases(self):
        self.assertTrue(self.d.outside("rubygems", "gem push foo"))
        self.assertTrue(self.d.outside("github.com/other/x"))
        self.assertTrue(self.d.outside("https://webhook.example/x"))
        self.assertFalse(self.d.outside("github.com/my-org/x"))
        self.assertFalse(self.d.outside("https://redmine.example.com/issues/1"))
        self.assertFalse(self.d.outside("origin", "pushed the branch"))


class ChunksTest(unittest.TestCase):
    def test_split_at_lines(self):
        item = Item("u", "\n".join(["x" * 30] * 10), "a")
        parts = list(chunks(item, 100))
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(p.text for p in parts), item.text)
        self.assertEqual(parts[0].uid, "u:part1")

    def test_short_item_untouched(self):
        item = Item("u", "short", "a")
        self.assertEqual(list(chunks(item, 100)), [item])


if __name__ == "__main__":
    unittest.main()
