import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from fisherman_redmine.github import GitHubReviews, PullRequest, pull_requests

PR = PullRequest("karafka", "karafka", 3413)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def review(uid, state, login="mensfeld", body=""):
    return {"user": {"id": uid, "login": login}, "state": state, "body": body}


class PullRequestsTest(unittest.TestCase):
    def test_finds_urls_and_short_references_once(self):
        text = (
            "[github:review:1] Maciej approved https://github.com/karafka/karafka/pull/3413 "
            "(karafka/karafka#3413), also karafka/rdkafka-ruby#1016 and #12 and see a/b/c#4"
        )
        self.assertEqual(
            pull_requests(text),
            [PR, PullRequest("karafka", "rdkafka-ruby", 1016)],
        )
        self.assertEqual(PR.url, "https://github.com/karafka/karafka/pull/3413")


class GitHubReviewsTest(unittest.TestCase):
    def serve(self, *bodies):
        queue = list(bodies)
        self.requests = []

        def urlopen(request, timeout):
            self.requests.append(request)
            body = queue.pop(0)
            if isinstance(body, Exception):
                raise body
            return Response(json.dumps(body).encode())

        return mock.patch("urllib.request.urlopen", urlopen)

    def test_keeps_only_trusted_accounts_and_known_states(self):
        reviews = GitHubReviews({"trusted_github_ids": [392754]})
        page = [
            review(392754, "CHANGES_REQUESTED", body="Please   resolve\nconflicts"),
            review(392754, "APPROVED"),
            review(392754, "DISMISSED"),
            review(999, "APPROVED", login="attacker"),
            {"user": None, "state": "APPROVED"},
        ]
        with self.serve(page):
            records = reviews.records(PR)
        self.assertEqual(
            records,
            [
                f"[review] mensfeld requested changes {PR.url}: Please resolve conflicts",
                f"[review] mensfeld approved {PR.url}",
            ],
        )
        self.assertNotIn("Authorization", self.requests[0].headers)
        self.assertIn("/repos/karafka/karafka/pulls/3413/reviews", self.requests[0].full_url)

    def test_caches_until_cleared(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        with self.serve([review(1, "APPROVED")], [review(1, "COMMENTED")]):
            first = reviews.records(PR)
            self.assertEqual(reviews.records(PR), first)
            reviews.clear()
            self.assertIn("commented on", reviews.records(PR)[0])
        self.assertEqual(len(self.requests), 2)

    def test_pages(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        with self.serve([review(2, "APPROVED")] * 100, [review(1, "APPROVED")]):
            self.assertEqual(len(reviews.records(PR)), 1)
        self.assertIn("page=2", self.requests[1].full_url)

    def test_token_and_api_url(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "t").write_text("ghtoken\n")
            reviews = GitHubReviews(
                {"trusted_github_ids": [1], "token_file": f"{d}/t", "api_url": "https://ghe/api/"}
            )
        with self.serve([]):
            self.assertEqual(reviews.records(PR), [])
        self.assertEqual(self.requests[0].get_header("Authorization"), "Bearer ghtoken")
        self.assertTrue(self.requests[0].full_url.startswith("https://ghe/api/repos/"))

    def test_unreadable_pull_requests_have_no_reviews(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        for code in (401, 403, 404):
            reviews.clear()
            with self.serve(urllib.error.HTTPError("u", code, "x", {}, None)):
                self.assertEqual(reviews.records(PR), [])

    def test_client_errors_raise_and_server_errors_retry(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        with (
            self.serve(urllib.error.HTTPError("u", 422, "x", {}, None)),
            self.assertRaises(urllib.error.HTTPError),
        ):
            reviews.records(PR)
        with (
            self.serve(
                urllib.error.HTTPError("u", 502, "x", {}, None),
                OSError("reset"),
                [review(1, "APPROVED")],
            ),
            mock.patch("time.sleep"),
        ):
            self.assertEqual(len(reviews.records(PR)), 1)
        reviews.clear()
        with (
            self.serve(OSError("a"), OSError("b"), OSError("c")),
            mock.patch("time.sleep"),
            self.assertRaises(OSError),
        ):
            reviews.records(PR)
