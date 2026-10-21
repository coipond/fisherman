import unittest

from fisherman.integrations.redmine.records import RedmineRecords
from fisherman.item import Item
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
                {"user": {"id": 7}, "notes": "[github:check] CI green"},
                {"user": {"id": 5}, "notes": ""},
            ],
        }
    },
}


class RedmineRecordsTest(unittest.TestCase):
    def setUp(self):
        self.rm = FakeRedmine(dict(ROUTES))
        self.records = RedmineRecords(
            {"trusted_user_ids": [1], "review_note_pattern": r"^\[github:.*\bAlice\b"}, self.rm
        )

    def test_trusted_statements_and_reviews(self):
        item = Item("x", "t", context={"type": "issue", "id": 10})
        self.assertEqual(
            self.records.records(item, []),
            [
                "Spec by Alice.",
                "Thanks.",
                "[review] [github:review] Alice approved https://github.com/o/x/pull/9",
            ],
        )
        self.assertEqual(self.records.records(item, ["999"]), [])

    def test_no_record_outside_issues(self):
        self.assertIsNone(self.records.records(Item("w", "t", context={"type": "wiki"}), []))

    def test_cache_until_cleared(self):
        item = Item("x", "t", context={"type": "issue", "id": 10})
        self.records.records(item, [])
        self.rm.routes.clear()
        self.assertEqual(len(self.records.records(item, [])), 3)
        self.records.clear()
        self.assertEqual(self.records.records(item, []), [])

    def test_without_review_pattern(self):
        plain = RedmineRecords({"trusted_user_ids": [1]}, self.rm)
        self.assertEqual(
            len(plain.records(Item("x", "t", context={"type": "issue", "id": 10}), [])), 2
        )
