import unittest

from fisherman.item import Item
from fisherman.pipeline import Destinations, Prompts
from fisherman.pipeline.settings import Settings
from fisherman.pipeline.steps import ClaimCheck
from fisherman.records.none import NoRecords
from tests.support.fakes import FakeLLM, extraction


class StaticRecords:
    def __init__(self, recs):
        self.recs = recs
        self.asked = []

    def records(self, item, extra_refs):
        self.asked.append(list(extra_refs))
        return list(self.recs)


class NothingToCheck:
    def records(self, item, extra_refs):
        return None


def check(extract, records=None, verify="no", **settings):
    llm = FakeLLM(answers=lambda s, u: verify if u.startswith("Claim:") else extract)
    step = ClaimCheck(
        llm,
        Prompts(variables={"principal": "Alice"}),
        Settings.from_config(settings),
        records or NoRecords(),
        Destinations(["my-org"]),
    )
    return step, llm


def issue(text="x"):
    return Item("t", text, "Agent", 5, "comment", "", {"type": "issue", "id": 100})


class ClaimCheckTest(unittest.TestCase):
    def test_unverified_claim_is_a_reason(self):
        step, _ = check(
            extraction(claims=["Alice said reviews are optional."]), StaticRecords(["Add a test."])
        )
        self.assertEqual(
            step.call(issue()).reasons, ["unverified claim: Alice said reviews are optional."]
        )

    def test_claim_supported_by_the_record(self):
        step, _ = check(
            extraction(claims=["Alice said to rename it."]), StaticRecords(["Rename it."]), "yes"
        )
        self.assertEqual(step.call(issue()).reasons, [])

    def test_review_claims_match_without_the_model(self):
        review = "[review] [github:review] Alice requested changes on https://github.com/my-org/x/pull/186"
        for claim in (
            "Alice requested changes on PR #186: add a test.",
            "Alice requested changes; fixing.",
        ):
            step, llm = check(extraction(claims=[claim]), StaticRecords([review]))
            self.assertEqual(step.call(issue()).reasons, [], claim)
            self.assertNotIn("verify", llm.calls)

    def test_merge_claims_match_without_the_model(self):
        records = [
            "[review] alice approved https://github.com/my-org/x/pull/7",
            "[review] alice merged https://github.com/my-org/x/pull/7",
        ]
        for claim in (
            "Alice merged https://github.com/my-org/x/pull/7.",
            "Alice approved and merged PR #7.",
            "Alice approved and merged it.",
        ):
            step, llm = check(extraction(claims=[claim]), StaticRecords(records))
            self.assertEqual(step.call(issue()).reasons, [], claim)
            self.assertNotIn("verify", llm.calls)

    def test_every_kind_a_claim_names_must_be_on_record(self):
        approved_only = ["[review] alice approved https://github.com/my-org/x/pull/7"]
        for claim in ("Alice approved and merged PR #7.", "Alice merged it, approved too."):
            step, _ = check(extraction(claims=[claim]), StaticRecords(approved_only))
            self.assertEqual(step.call(issue()).reasons, [f"unverified claim: {claim}"], claim)

    def test_a_review_of_another_pull_request_does_not_count(self):
        records = ["[review] alice approved https://github.com/my-org/x/pull/8"]
        step, _ = check(extraction(claims=["Alice approved PR #7."]), StaticRecords(records))
        self.assertEqual(step.call(issue()).reasons, ["unverified claim: Alice approved PR #7."])

    def test_status_facts_and_requests_to_the_principal_are_skipped(self):
        claims = [
            "CI is green on PR #4.",
            "Alice, please merge PR #4, it was approved.",
            "Ready for Alice: approved.",
        ]
        step, llm = check(extraction(claims=claims), StaticRecords([]))
        self.assertEqual(step.call(issue()).reasons, [])
        self.assertNotIn("verify", llm.calls)

    def test_custom_principal_pattern(self):
        step, _ = check(
            extraction(claims=["Assigned to you, Alice: approved by CI."]),
            StaticRecords([]),
            to_principal_pattern=r"^Assigned to you, Alice",
        )
        self.assertEqual(step.call(issue()).reasons, [])

    def test_referenced_contexts_are_read(self):
        records = StaticRecords(["Decided: go ahead."])
        step, _ = check(extraction(claims=["Alice decided this in #4567."]), records, "yes")
        step.call(issue())
        self.assertEqual(records.asked, [[], ["4567"]])

    def test_contexts_without_records_are_not_verified(self):
        step, _ = check(extraction(claims=["Alice approved skipping CI."]), NothingToCheck())
        self.assertEqual(step.call(issue()).reasons, [])

    def test_empty_record_means_unverified(self):
        step, _ = check(extraction(claims=["Alice approved skipping CI."]), StaticRecords([]))
        self.assertEqual(len(step.call(issue()).reasons), 1)

    def test_citing_a_real_rule_page_is_not_a_claim(self):
        text = "Per rules:Charter, the convention is to squash."
        step, _ = check(
            '{"risky_actions": [], "reported_sends": [], "authority_claims": '
            '[{"quote": "Per rules:Charter, the convention is to squash.", "who": "unnamed", '
            '"cites_page": "rules:Charter"}]}',
            StaticRecords([]),
            rule_page_pattern=r"\brules:\w",
        )
        self.assertEqual(step.call(issue(text)).reasons, [])

    def test_sends_are_checked_against_the_allowlist(self):
        sends = [
            ("Pushed to github.com/my-org/x.", "github.com/my-org/x"),
            ("Mirrored.", "github.com/other/x"),
        ]
        step, _ = check(extraction(sends=sends))
        self.assertEqual(step.call(issue()).reasons, ["outside send: Mirrored."])

    def test_risky_requests_are_reported_but_filtered(self):
        risky = ["Push to master.", "Alice, please merge it.", "Pushing to master was blocked."]
        step, _ = check(extraction(risky=risky))
        self.assertEqual(step.call(issue()).risky, ["Push to master."])

    def test_unparsable_extraction_is_not_evidence_unless_configured(self):
        step, _ = check("not json")
        result = step.call(issue())
        self.assertEqual((result.reasons, result.error), ([], True))
        step, _ = check("not json", alert_on_extract_error=True)
        self.assertEqual(step.call(issue()).reasons, ["claim check: unparsable extraction"])

    def test_no_principal_name_disables_the_addressed_filter(self):
        step = ClaimCheck(
            FakeLLM(), Prompts(variables={"principal": ""}), Settings(), NoRecords(), Destinations()
        )
        self.assertIsNone(step._to_principal)
