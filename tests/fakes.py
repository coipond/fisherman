"""Test doubles: a scripted model and an in-memory Redmine."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional


class FakeLLM:
    """quick: p_yes = 0.9 if the text matches `risky`, else 0.1. chat: answered by `answers(system, user)`."""

    url = "fake"

    def __init__(self, risky: str = r"(?!)", answers: Optional[Callable[[str, str], str]] = None):
        self.risky = re.compile(risky, re.I)
        self.answers = answers or (lambda system, user: "")
        self.calls: List[str] = []
        self.vocab: List[str] = []

    def health(self) -> bool:
        return True

    def tokenize(self, text: str) -> List[int]:
        ids = []
        for word in text.split(" "):
            self.vocab.append(word)
            ids.append(len(self.vocab) - 1)
        return ids

    def detokenize(self, tokens: List[int]) -> str:
        return " ".join(self.vocab[t] for t in tokens)

    def truncate(self, text: str, max_tokens: int) -> str:
        return " ".join(text.split(" ")[:max_tokens])

    def p_yes(self, system: str, user: str) -> float:
        self.calls.append("quick")
        content = user.split("<content>")[1]
        return 0.9 if self.risky.search(content) else 0.1

    def chat(self, system: str, user: str, n_predict: int, think: bool = False, **extra: Any) -> str:
        self.calls.append("reason" if think else ("extract" if "json_schema" in extra else "verify"))
        return self.answers(system, user)


def extraction(claims=(), sends=(), risky=()) -> str:
    return json.dumps({
        "risky_actions": [{"quote": q} for q in risky],
        "authority_claims": [{"quote": q, "who": "Alice", "cites_page": ""} for q in claims],
        "reported_sends": [{"quote": q, "destination": d} for q, d in sends],
    })


class FakeRedmine:
    """Answers GET paths from a dict; records POSTs."""

    url = "https://rm.example"

    def __init__(self, routes: Dict[str, Any]):
        self.routes = routes
        self.posts: List[Any] = []

    def get(self, path: str, **params: Any) -> Any:
        return self.routes.get(path)

    def paged(self, path: str, key: str, **params: Any):
        yield from (self.routes.get(path) or {}).get(key, [])

    def request(self, method: str, path: str, params: Any = None, body: Any = None) -> Any:
        self.posts.append((path, body))
        return {}

    def issue_url(self, issue_id: Any) -> str:
        return f"{self.url}/issues/{issue_id}"

    def wiki_url(self, project: str, title: str, version: Any = None) -> str:
        return f"{self.url}/projects/{project}/wiki/{title}/{version}"
