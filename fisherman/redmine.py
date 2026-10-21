"""Minimal Redmine REST client (JSON API, API-key auth)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class RedmineError(Exception):
    pass


class Redmine:
    def __init__(self, url: str, key: str, timeout: int = 60):
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Redmine":
        key = cfg.get("key")
        if cfg.get("key_file"):
            key = Path(cfg["key_file"]).expanduser().read_text().strip()
        if not key:
            raise RedmineError("redmine: set key_file (or key)")
        return cls(cfg["url"], key, int(cfg.get("timeout", 60)))

    def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Any = None) -> Any:
        url = self.url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-Redmine-API-Key": self.key, "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data, headers, method=method)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code < 500:
                    raise RedmineError(f"{method} {path}: HTTP {e.code} {e.read()[:300]!r}") from e
                err: Exception = e
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                err = e
            time.sleep(3 * (attempt + 1))
        raise RedmineError(f"{method} {path}: {err}")

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params or None)

    def paged(self, path: str, key: str, **params: Any) -> Iterator[Dict[str, Any]]:
        offset = 0
        while True:
            page = self.get(path, offset=offset, limit=100, **params) or {}
            rows = page.get(key, [])
            yield from rows
            offset += len(rows)
            if not rows or offset >= page.get("total_count", 0):
                return

    def issue_url(self, issue_id: Any) -> str:
        return f"{self.url}/issues/{issue_id}"

    def wiki_url(self, project: str, title: str, version: Any = None) -> str:
        base = f"{self.url}/projects/{project}/wiki/{urllib.parse.quote(title)}"
        return f"{base}/{version}" if version else base
