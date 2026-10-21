"""An in-memory Redmine client."""

from __future__ import annotations

from typing import Any


class FakeRedmine:
    """Answers GET paths from a dict and records POSTs."""

    url = "https://rm.example"

    def __init__(self, routes: dict[str, Any] | None = None):
        self.routes = routes or {}
        self.posts: list[Any] = []

    def get(self, path: str, **params: Any) -> Any:
        return self.routes.get(path)

    def paged(self, path: str, key: str, **params: Any):
        yield from (self.routes.get(path) or {}).get(key, [])

    def post(self, path: str, body: Any) -> Any:
        self.posts.append((path, body))
        return {}

    def issue_url(self, issue_id: Any) -> str:
        return f"{self.url}/issues/{issue_id}"

    def wiki_url(self, project: str, title: str, version: Any = None) -> str:
        return f"{self.url}/projects/{project}/wiki/{title}/{version}"
