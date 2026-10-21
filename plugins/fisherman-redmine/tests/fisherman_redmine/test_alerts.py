import unittest

from fisherman.item import Item, Verdict
from fisherman_redmine.alerts import RedmineAlerts
from tests.support.fakes import FakeRedmine


class RedmineAlertsTest(unittest.TestCase):
    def test_issue_escapes_the_content(self):
        rm = FakeRedmine()
        alerts = RedmineAlerts({"project": "fisherman", "assigned_to_id": 1, "tracker_id": 3}, rm)
        alerts.send(
            Item("u", "<script>x</script> & more", "Agent", 5),
            Verdict(alert=True, reasons=["outside send: x"], scores={"quick": 0.9}),
        )
        path, body = rm.posts[0]
        issue = body["issue"]
        self.assertEqual(path, "/issues.json")
        self.assertEqual(
            (issue["project_id"], issue["assigned_to_id"], issue["tracker_id"]), ("fisherman", 1, 3)
        )
        self.assertIn("&lt;script&gt;", issue["description"])
        self.assertNotIn("<script>", issue["description"])
        self.assertEqual(issue["subject"], "[fisherman] Agent: outside send: x")

    def test_minimal(self):
        body = RedmineAlerts({"project": "p"}, FakeRedmine()).body(
            Item("u", "t"), Verdict(alert=True)
        )
        self.assertEqual(body["issue"]["subject"], "[fisherman] unknown: flagged")
        self.assertNotIn("assigned_to_id", body["issue"])
