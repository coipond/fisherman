import io
import json
import logging
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from fisherman_redmine.github import GitHubReviews, PullRequest, pull_requests

PR = PullRequest("karafka", "karafka", 3413)


def setUpModule():
    # The no-token warning is expected in most tests; keep it out of the test output
    logging.getLogger("fisherman").addHandler(logging.NullHandler())


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def review(uid, state, login="mensfeld", body=""):
    return {"user": {"id": uid, "login": login}, "state": state, "body": body}


# The pull request itself, read after its reviews
OPEN = {"merged": False, "merged_by": None}


def merged(uid, login="mensfeld"):
    return {"merged": True, "merged_by": {"id": uid, "login": login}}


def rate_limited(code=403, remaining="0"):
    return urllib.error.HTTPError("u", code, "x", {"x-ratelimit-remaining": remaining}, None)


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
        with self.serve(page, OPEN):
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
        self.assertTrue(self.requests[1].full_url.endswith("/repos/karafka/karafka/pulls/3413"))

    def test_a_merge_by_a_trusted_account_is_a_record(self):
        reviews = GitHubReviews({"trusted_github_ids": [392754]})
        with self.serve([review(392754, "APPROVED")], merged(392754)):
            self.assertEqual(
                reviews.records(PR),
                [f"[review] mensfeld approved {PR.url}", f"[review] mensfeld merged {PR.url}"],
            )

    def test_merges_by_others_and_unmerged_pull_requests_add_nothing(self):
        reviews = GitHubReviews({"trusted_github_ids": [392754]})
        for pull in (merged(999, "attacker"), OPEN, {"merged": True, "merged_by": None}, []):
            reviews.clear()
            with self.serve([], pull):
                self.assertEqual(reviews.records(PR), [], pull)

    def test_rate_limits_are_logged_once_and_read_as_no_record(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        limits = (rate_limited(), rate_limited(429, "5"))
        with self.serve(*limits), self.assertLogs("fisherman") as logs:
            self.assertEqual(reviews.records(PR), [])
        self.assertEqual(len(logs.output), 1)
        self.assertIn("rate limit", logs.output[0])
        self.assertIn("token_file", logs.output[0])

    def test_a_forbidden_page_with_quota_left_is_not_a_rate_limit(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        forbidden = rate_limited(remaining="10")
        with self.serve(forbidden, forbidden), self.assertNoLogs("fisherman"):
            self.assertEqual(reviews.records(PR), [])

    def test_no_token_file_is_warned_about(self):
        with self.assertLogs("fisherman") as logs:
            GitHubReviews({"trusted_github_ids": [1]})
        self.assertIn("60 requests an hour", logs.output[0])

    def test_caches_until_cleared(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        with self.serve([review(1, "APPROVED")], OPEN, [review(1, "COMMENTED")], OPEN):
            first = reviews.records(PR)
            self.assertEqual(reviews.records(PR), first)
            reviews.clear()
            self.assertIn("commented on", reviews.records(PR)[0])
        self.assertEqual(len(self.requests), 4)

    def test_pages(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        with self.serve([review(2, "APPROVED")] * 100, [review(1, "APPROVED")], OPEN):
            self.assertEqual(len(reviews.records(PR)), 1)
        self.assertIn("page=2", self.requests[1].full_url)

    def test_token_and_api_url(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "t").write_text("ghtoken\n")
            with self.assertNoLogs("fisherman"):
                reviews = GitHubReviews(
                    {
                        "trusted_github_ids": [1],
                        "token_file": f"{d}/t",
                        "api_url": "https://ghe/api/",
                    }
                )
        with self.serve([], OPEN):
            self.assertEqual(reviews.records(PR), [])
        self.assertEqual(self.requests[0].get_header("Authorization"), "Bearer ghtoken")
        self.assertTrue(self.requests[0].full_url.startswith("https://ghe/api/repos/"))
        reviews.clear()
        with self.serve(rate_limited(), OPEN), self.assertLogs("fisherman") as logs:
            reviews.records(PR)
        self.assertNotIn("token_file", logs.output[0])

    def test_unreadable_pull_requests_have_no_reviews(self):
        reviews = GitHubReviews({"trusted_github_ids": [1]})
        for code in (401, 403, 404):
            reviews.clear()
            error = urllib.error.HTTPError("u", code, "x", {}, None)
            with self.serve(error, error):
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
                OPEN,
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
