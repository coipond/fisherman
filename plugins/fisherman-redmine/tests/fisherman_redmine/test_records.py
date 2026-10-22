import unittest

from fisherman.contracts import Contract
from fisherman.item import Item
from fisherman_redmine.github import PullRequest
from fisherman_redmine.records import RedmineRecords
from tests.support.fakes import FakeRedmine

ROUTES = {
    "/issues/10.json": {
        "issue": {
            "author": {"id": 1},
            "description": "Spec by Alice.",
            "journals": [
                {"user": {"id": 1}, "notes": "Thanks."},
                {
                    "user": {"id": 7},
                    "notes": "[github:review] Alice approved https://github.com/o/x/pull/9",
                },
                {"user": {"id": 7}, "notes": "[github:review] Alice approved o/x#9 again"},
                {"user": {"id": 7}, "notes": "[github:review] Alice approved o/x#10, ship it"},
                {"user": {"id": 7}, "notes": "[github:check] CI green on o/x#9"},
                {"user": {"id": 5}, "notes": ""},
            ],
        }
    },
}
ISSUE = Item("x", "t", context={"type": "issue", "id": 10})


class FakeReviews:
    """GitHub knows one real review: Alice approved o/x#9. PR o/x#10 has none."""

    def __init__(self):
        self.asked = []
        self.cleared = False

    def records(self, pr):
        self.asked.append(pr)
        return ["[review] alice approved https://github.com/o/x/pull/9"] if pr.number == 9 else []

    def clear(self):
        self.cleared = True


class RedmineRecordsTest(unittest.TestCase):
    def setUp(self):
        self.rm = FakeRedmine(dict(ROUTES))
        self.reviews = FakeReviews()
        self.records = RedmineRecords(
            {"trusted_user_ids": [1], "review_note_pattern": r"^\[github:review"},
            self.rm,
            self.reviews,
        )

    def test_trusted_statements_and_confirmed_reviews_only(self):
        self.assertEqual(
            self.records.records(ISSUE, []),
            ["Spec by Alice.", "Thanks.", "[review] alice approved https://github.com/o/x/pull/9"],
        )
        self.assertEqual(self.records.records(ISSUE, ["999"]), [])

    def test_review_notes_are_pointers_not_evidence(self):
        records = self.records.records(ISSUE, [])
        self.assertFalse(
            any("ship it" in r or "#10" in r for r in records)
        )  # forged, GitHub has no such review
        self.assertNotIn(PullRequest("o", "x", 11), self.reviews.asked)
        self.assertIn(PullRequest("o", "x", 10), self.reviews.asked)

    def test_non_review_notes_are_not_followed(self):
        self.records.records(ISSUE, [])
        self.assertEqual(
            self.reviews.asked.count(PullRequest("o", "x", 9)), 2
        )  # two review notes, not the CI note

    def test_no_record_outside_issues(self):
        self.assertIsNone(self.records.records(Item("w", "t", context={"type": "wiki"}), []))

    def test_cache_until_cleared(self):
        self.records.records(ISSUE, [])
        self.rm.routes.clear()
        self.assertEqual(len(self.records.records(ISSUE, [])), 3)
        self.records.clear()
        self.assertTrue(self.reviews.cleared)
        self.assertEqual(self.records.records(ISSUE, []), [])

    def test_without_review_settings_only_trusted_users_count(self):
        plain = RedmineRecords({"trusted_user_ids": [1]}, self.rm)
        self.assertEqual(plain.records(ISSUE, []), ["Spec by Alice.", "Thanks."])
        plain.clear()

    def test_contract_requires_verification_with_a_review_pattern(self):
        base = {"url": "https://rm", "trusted_user_ids": [1], "review_note_pattern": "^x"}
        errors = RedmineRecords.CONTRACT.errors(base, "records")
        self.assertEqual(len(errors), 1)
        self.assertIn("review_note_pattern needs review_verification", errors[0])
        ok = {**base, "review_verification": {"trusted_github_ids": [392754]}}
        self.assertEqual(RedmineRecords.CONTRACT.errors(ok, "records"), [])
        bad = {**base, "review_verification": {"trusted_github_ids": ["mensfeld"]}}
        self.assertIn(
            "records.review_verification.trusted_github_ids",
            RedmineRecords.CONTRACT.errors(bad, "records")[0],
        )
        self.assertIsInstance(RedmineRecords.CONTRACT, Contract)

    def test_builds_its_own_github_reader(self):
        records = RedmineRecords(
            {
                "trusted_user_ids": [1],
                "review_note_pattern": "x",
                "review_verification": {"trusted_github_ids": [1]},
            },
            self.rm,
        )
        self.assertIsNotNone(records._reviews)
