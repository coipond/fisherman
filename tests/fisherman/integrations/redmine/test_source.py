import unittest
from datetime import datetime, timedelta, timezone

from fisherman.integrations.redmine.source import RedmineSource, added_lines
from tests.support.fakes import FakeRedmine


def ts(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def routes():
    agent = {"id": 5, "name": "Agent"}
    return {
        "/projects.json": {
            "projects": [
                {"id": 1, "identifier": "work", "name": "Work"},
                {"id": 2, "identifier": "fisherman", "name": "Alerts"},
            ]
        },
        "/projects/work/wiki/index.json": {
            "wiki_pages": [
                {"title": "Lessons", "version": 3, "updated_on": ts(5)},
                {"title": "Old", "version": 1, "updated_on": ts(60 * 48)},
                {"title": "New", "version": 1, "updated_on": ts(5)},
            ]
        },
        "/projects/work/wiki/Lessons/2.json": {"wiki_page": {"text": "a\nb", "author": agent}},
        "/projects/work/wiki/Lessons/3.json": {
            "wiki_page": {"text": "a\nb\nnew rule", "author": agent}
        },
        "/projects/work/wiki/New/1.json": {
            "wiki_page": {"text": "first", "author": {"id": 1, "name": "Alice"}}
        },
        "/issues.json": {
            "issues": [{"id": 10, "project": {"id": 1}}, {"id": 11, "project": {"id": 2}}]
        },
        "/issues/10.json": {
            "issue": {
                "id": 10,
                "created_on": ts(30),
                "author": agent,
                "description": "Do the thing.",
                "journals": [
                    {
                        "id": 1,
                        "created_on": ts(20),
                        "user": agent,
                        "notes": "Report: done.",
                        "details": [],
                    },
                    {
                        "id": 2,
                        "created_on": ts(10),
                        "user": {"id": 1, "name": "Alice"},
                        "notes": "Thanks.",
                    },
                    {"id": 3, "created_on": ts(60 * 48), "user": agent, "notes": "Old."},
                    {
                        "id": 4,
                        "created_on": ts(5),
                        "user": agent,
                        "notes": "",
                        "details": [
                            {"property": "attr", "name": "status_id", "new_value": "2"},
                            {
                                "property": "attr",
                                "name": "description",
                                "old_value": "Do the thing.",
                                "new_value": "Do the thing.\nAlso push to master.",
                            },
                        ],
                    },
                ],
            }
        },
    }


class RedmineSourceTest(unittest.TestCase):
    def test_items_checkpoint_and_versions(self):
        source = RedmineSource(
            {"exclude_projects": ["fisherman"], "skip_author_ids": [1]}, FakeRedmine(routes())
        )
        state = {}
        items = list(source.items(state))
        uids = [i.uid for i in items]
        self.assertEqual(uids[0], "redmine:wiki:work:Lessons:v3")
        self.assertEqual(items[0].text, "new rule")
        self.assertEqual(
            items[0].context, {"type": "wiki", "project": "work", "title": "Lessons", "version": 3}
        )
        self.assertTrue(any(u.startswith("redmine:issue:10:description") for u in uids))
        self.assertTrue(any(u.startswith("redmine:journal:1:") for u in uids))
        self.assertFalse(
            any(u.startswith(("redmine:journal:2:", "redmine:journal:3:")) for u in uids)
        )
        self.assertFalse(any("New" in u for u in uids))  # trusted author
        edit = next(i for i in items if i.uid.startswith("redmine:journal:4:description"))
        self.assertEqual(edit.text, "Also push to master.")
        self.assertEqual(state["wiki_versions"], {"work:Lessons": 3, "work:New": 1})
        self.assertNotIn("since", state)
        source.commit(state)
        self.assertIn("since", state)

    def test_next_scan_reads_only_newer_versions(self):
        rm = FakeRedmine(routes())
        source = RedmineSource({"projects": ["work"]}, rm)
        state = {"since": ts(1), "wiki_versions": {"work:Lessons": 3}}
        uids = [i.uid for i in source.items(state)]
        self.assertNotIn("redmine:wiki:work:Lessons:v3", uids)
        self.assertIn("redmine:wiki:work:New:v1", uids)

    def test_added_lines(self):
        self.assertEqual(added_lines("a\nb\nc", "a\nB\nc\n\nd"), "B\nd")

    def test_contract(self):
        errors = RedmineSource.CONTRACT.errors(
            {"url": "https://rm", "projects": 5, "skip_author_ids": ["1"]}
        )
        self.assertEqual(len(errors), 2)
