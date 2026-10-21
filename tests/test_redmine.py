import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fisherman import config
from fisherman.alerts.redmine import RedmineAlerts
from fisherman.item import Item, Verdict
from fisherman.prompts import Prompts
from fisherman.records.redmine import RedmineRecords
from fisherman.sources.redmine import RedmineSource, added_lines
from fisherman.state import State

from .fakes import FakeRedmine


def ts(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def routes():
    return {
        "/projects.json": {"projects": [{"id": 1, "identifier": "work", "name": "Work"},
                                        {"id": 2, "identifier": "fisherman", "name": "Alerts"}]},
        "/projects/work/wiki/index.json": {"wiki_pages": [
            {"title": "Lessons", "version": 3, "updated_on": ts(5)},
            {"title": "Old", "version": 1, "updated_on": ts(60 * 48)}]},
        "/projects/work/wiki/Lessons/2.json": {"wiki_page": {"text": "a\nb", "version": 2, "author": {"id": 5, "name": "Agent"}}},
        "/projects/work/wiki/Lessons/3.json": {"wiki_page": {"text": "a\nb\nnew rule", "version": 3, "author": {"id": 5, "name": "Agent"}}},
        "/issues.json": {"issues": [{"id": 10, "project": {"id": 1}}, {"id": 11, "project": {"id": 2}}]},
        "/issues/10.json": {"issue": {
            "id": 10, "created_on": ts(30), "author": {"id": 5, "name": "Agent"}, "description": "Do the thing.",
            "journals": [
                {"id": 1, "created_on": ts(20), "user": {"id": 5, "name": "Agent"}, "notes": "Report: done.", "details": []},
                {"id": 2, "created_on": ts(10), "user": {"id": 1, "name": "Alice"}, "notes": "Thanks.", "details": []},
                {"id": 3, "created_on": ts(60 * 48), "user": {"id": 5, "name": "Agent"}, "notes": "Old.", "details": []},
                {"id": 4, "created_on": ts(5), "user": {"id": 5, "name": "Agent"}, "notes": "",
                 "details": [{"property": "attr", "name": "description", "old_value": "Do the thing.", "new_value": "Do the thing.\nAlso push to master."}]},
                {"id": 5, "created_on": ts(4), "user": {"id": 7, "name": "Bot"},
                 "notes": "[github: review] Alice approved https://github.com/my-org/x/pull/9", "details": []},
            ]}},
    }


class RedmineSourceTest(unittest.TestCase):
    def test_items_and_checkpoint(self):
        src = RedmineSource({"exclude_projects": ["fisherman"], "skip_author_ids": [1]}, client=FakeRedmine(routes()))
        state = {}
        items = list(src.items(state))
        uids = [i.uid for i in items]
        self.assertTrue(uids[0].startswith("redmine:wiki:work:Lessons:v3"))
        self.assertEqual(items[0].text, "new rule")
        self.assertTrue(any(u.startswith("redmine:issue:10:description") for u in uids))
        self.assertTrue(any(u.startswith("redmine:journal:1:") for u in uids))
        self.assertFalse(any(u.startswith("redmine:journal:2:") for u in uids))  # trusted author skipped
        self.assertFalse(any(u.startswith("redmine:journal:3:") for u in uids))  # older than the lookback
        edit = [i for i in items if ":description:" in i.uid and i.uid.startswith("redmine:journal:4")][0]
        self.assertEqual(edit.text, "Also push to master.")
        self.assertEqual(state["wiki_versions"], {"work:Lessons": 3})
        self.assertNotIn("since", state)
        src.commit(state)
        self.assertIn("since", state)

    def test_added_lines(self):
        self.assertEqual(added_lines("a\nb\nc", "a\nB\nc\nd"), "B\nd")


class RedmineRecordsTest(unittest.TestCase):
    def test_trusted_comments_and_reviews(self):
        rec = RedmineRecords({"trusted_user_ids": [1], "review_note_pattern": r"^\[github:.*\bAlice\b"}, client=FakeRedmine(routes()))
        item = Item("x", "t", context={"type": "issue", "id": 10})
        self.assertEqual(rec.records(item, []), ["Thanks.", "[review] [github: review] Alice approved https://github.com/my-org/x/pull/9"])
        self.assertIsNone(rec.records(Item("w", "t", context={"type": "wiki"}), []))
        self.assertEqual(rec.records(item, ["999"]), [])


class RedmineAlertsTest(unittest.TestCase):
    def test_body_escapes_content(self):
        rm = FakeRedmine({})
        alerts = RedmineAlerts({"project": "fisherman", "assigned_to_id": 1}, client=rm)
        alerts.send(Item("u", "<script>x</script> & more", "Agent", 5, "src", "link"), Verdict(True, ["outside send: x"], {"quick": 0.9}))
        path, body = rm.posts[0]
        self.assertEqual(path, "/issues.json")
        issue = body["issue"]
        self.assertEqual(issue["project_id"], "fisherman")
        self.assertIn("&lt;script&gt;", issue["description"])
        self.assertNotIn("<script>", issue["description"])
        self.assertTrue(issue["subject"].startswith("[fisherman] Agent: outside send"))


class StateAndConfigTest(unittest.TestCase):
    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            s = State(str(Path(d) / "s.json"))
            s.source("redmine")["since"] = "x"
            s.mark("a")
            s.save()
            s2 = State(str(Path(d) / "s.json"))
            self.assertTrue(s2.seen("a"))
            self.assertEqual(s2.source("redmine")["since"], "x")

    def test_shared_redmine_settings(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_text(json.dumps({"redmine": {"url": "https://rm", "key_file": "k"},
                                     "sources": [{"type": "redmine"}], "records": {"type": "redmine"},
                                     "alerts": {"type": "redmine", "project": "f", "url": "https://other"}}))
            cfg = config.load(str(p))
            self.assertEqual(cfg["sources"][0]["url"], "https://rm")
            self.assertEqual(cfg["records"]["key_file"], "k")
            self.assertEqual(cfg["alerts"]["url"], "https://other")

    def test_prompt_override_and_variables(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "verify.txt").write_text("Private prompt about {principal} and {unknown}.")
            p = Prompts(d, {"principal": "Alice"})
            self.assertEqual(p.get("verify"), "Private prompt about Alice and {unknown}.")
            self.assertIn("Alice", p.get("quick"))


if __name__ == "__main__":
    unittest.main()
