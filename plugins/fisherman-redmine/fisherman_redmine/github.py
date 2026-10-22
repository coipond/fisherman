"""Confirms code reviews with GitHub, the source of truth, instead of trusting notes about them."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fisherman.contracts import Contract, is_list_of_ints, is_string, is_url

# Pull request references a review note may use
_PR_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)")
_PR_SHORT = re.compile(r"(?<![\w/.-])([\w.-]+)/([\w.-]+)#(\d+)\b")
# Review states that matter for claims, and how records phrase them
_STATES = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "requested changes",
    "COMMENTED": "commented on",
}
# Characters of a review body kept in the record
_BODY_CHARS = 300
# Statuses meaning "this token may not see it" or "it does not exist"
_NOT_VISIBLE = (401, 403, 404)
# Server errors at or above this status are retried
_SERVER_ERROR = 500
# Reviews per page (GitHub's maximum)
_PAGE = 100


@dataclass(frozen=True)
class PullRequest:
    """A pull request reference.

    Attributes:
        owner: Repository owner.
        repo: Repository name.
        number: Pull request number.

    """

    owner: str
    repo: str
    number: int

    @property
    def url(self) -> str:
        """The pull request's web URL.

        Returns:
            The URL.

        """
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.number}"


def pull_requests(text: str) -> list[PullRequest]:
    """Find pull request references in a note.

    Args:
        text: The note.

    Returns:
        Every distinct `github.com/<owner>/<repo>/pull/<n>` and `<owner>/<repo>#<n>`, in order.

    """
    found: list[PullRequest] = []
    for pattern in (_PR_URL, _PR_SHORT):
        for owner, repo, number in pattern.findall(text):
            pr = PullRequest(owner, repo, int(number))
            if pr not in found:
                found.append(pr)
    return found


class GitHubReviews:
    """Reads pull request reviews and keeps those by trusted GitHub accounts."""

    #: Contract for the "review_verification" section of the records configuration
    CONTRACT = (
        Contract()
        .required("trusted_github_ids", is_list_of_ints, "must be a list of GitHub user ids")
        .optional("api_url", is_url, "must be an http(s) URL")
        .optional("token_file", is_string, "must be a path")
    )

    def __init__(self, cfg: dict[str, Any]) -> None:
        """Create the reader.

        Args:
            cfg: The section: trusted_github_ids (numeric account ids, which survive renames),
                token_file (a read-only token; without it only public repositories can be
                read), api_url (default https://api.github.com).

        """
        self._trusted = {int(i) for i in cfg["trusted_github_ids"]}
        self._api = str(cfg.get("api_url", "https://api.github.com")).rstrip("/")
        token = (
            Path(cfg["token_file"]).expanduser().read_text().strip()
            if cfg.get("token_file")
            else ""
        )
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._cache: dict[PullRequest, list[str]] = {}

    def records(self, pr: PullRequest) -> list[str]:
        """Describe the trusted accounts' reviews of a pull request.

        Args:
            pr: The pull request.

        Returns:
            One "[review] ..." line per review by a trusted account, for example
            "[review] mensfeld approved https://github.com/o/r/pull/9: Looks good". Empty when
            the pull request has none, does not exist, or is not readable with the token.

        """
        if pr not in self._cache:
            self._cache[pr] = [
                self._line(pr, review) for review in self._reviews(pr) if self._counts(review)
            ]
        return self._cache[pr]

    def clear(self) -> None:
        """Forget cached reviews, so the next scan reads fresh ones."""
        self._cache.clear()

    def _counts(self, review: dict[str, Any]) -> bool:
        user = review.get("user") or {}
        return user.get("id") in self._trusted and review.get("state") in _STATES

    @staticmethod
    def _line(pr: PullRequest, review: dict[str, Any]) -> str:
        login = (review.get("user") or {}).get("login", "")
        body = " ".join(str(review.get("body") or "").split())[:_BODY_CHARS]
        line = f"[review] {login} {_STATES[review['state']]} {pr.url}"
        return f"{line}: {body}" if body else line

    def _reviews(self, pr: PullRequest) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        page = 1
        while True:
            reviews_path = f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/reviews"
            batch = self._get(f"{reviews_path}?per_page={_PAGE}&page={page}")
            if not batch:
                return reviews
            reviews.extend(batch)
            if len(batch) < _PAGE:
                return reviews
            page += 1

    def _get(self, path: str) -> list[dict[str, Any]] | None:
        error: Exception | None = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(self._api + path, headers=self._headers)  # noqa: S310 - configured URL
                with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                    result: list[dict[str, Any]] = json.load(response)
                    return result
            except urllib.error.HTTPError as e:
                if e.code in _NOT_VISIBLE:
                    return None
                if e.code < _SERVER_ERROR:
                    raise
                error = e
            except OSError as e:
                error = e
            time.sleep(2 * (attempt + 1))
        raise OSError(f"GitHub {path}: {error}")  # noqa: EM102 - retried network failure
