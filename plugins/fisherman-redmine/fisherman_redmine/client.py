"""Minimal Redmine REST client (JSON API, API-key auth)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fisherman.contracts import Contract, is_int_at_least, is_list_of_strings, is_string, is_url
from fisherman.errors import RedmineError

if TYPE_CHECKING:
    from collections.abc import Iterator

# Statuses that mean "this key may not see it" or "it is not there"; another key may still see it
_NOT_VISIBLE = (403, 404)
# Server errors at or above this status are retried
_SERVER_ERROR = 500
# Redmine's maximum page size
_PAGE = 100


class Client:
    """A Redmine client that can try several read keys in turn."""

    #: Contract for the connection settings of every Redmine plug-in
    CONTRACT = (
        Contract()
        .required("url", is_url, "must be an http(s) URL")
        .optional("key_file", is_string, "must be a path")
        .optional("key_files", is_list_of_strings, "must be a list of paths")
        .optional("timeout", is_int_at_least(1), "must be an integer >= 1")
    )

    def __init__(self, url: str, keys: list[str], timeout: int = 60) -> None:
        """Create a client.

        Args:
            url: Base URL of the Redmine instance.
            keys: API keys. GETs a key may not see are retried with the next one.
            timeout: Seconds to wait for one request.

        """
        self.url = url.rstrip("/")
        self._keys = keys
        self._timeout = timeout

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Client:
        """Build a client from a Redmine plug-in's configuration section.

        Args:
            cfg: The section: url, key_files or key_file, timeout.

        Returns:
            The client.

        Raises:
            RedmineError: When no key is configured.

        """
        files = cfg.get("key_files") or ([cfg["key_file"]] if cfg.get("key_file") else [])
        keys = [Path(f).expanduser().read_text().strip() for f in files]
        if not keys:
            msg = "redmine: set key_file or key_files"
            raise RedmineError(msg)
        return cls(str(cfg["url"]), keys, int(cfg.get("timeout", 60)))

    def get(self, path: str, **params: Any) -> Any:
        """GET a JSON resource.

        Args:
            path: Path such as "/issues/1.json".
            **params: Query parameters.

        Returns:
            The parsed body, or None when no key may see the resource or it does not exist.

        """
        return self.request("GET", path, params or None)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        """POST a JSON body with the first key.

        Args:
            path: Path such as "/issues.json".
            body: The body.

        Returns:
            The parsed response body, if any.

        """
        return self.request("POST", path, None, body)

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request.

        Args:
            method: HTTP method.
            path: Path such as "/issues.json".
            params: Query parameters.
            body: JSON body.

        Returns:
            The parsed body. None for a GET that no key may see or that does not exist. Any
            other client error, and server or network errors that persist after retries, raise
            `RedmineError`.

        """
        keys = self._keys if method == "GET" else self._keys[:1]
        for key in keys:
            found, result = self._try_key(key, method, path, params, body)
            if found:
                return result
        return None

    def _try_key(
        self,
        key: str,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> tuple[bool, Any]:
        try:
            return True, self._send(key, method, path, params, body)
        except urllib.error.HTTPError as e:
            if e.code in _NOT_VISIBLE and method == "GET":
                return False, None
            msg = f"{method} {path}: HTTP {e.code} {e.read()[:300]!r}"
            raise RedmineError(msg) from e

    def paged(self, path: str, key: str, **params: Any) -> Iterator[dict[str, Any]]:
        """Iterate over every row of a paginated listing.

        Args:
            path: Listing path such as "/issues.json".
            key: Key of the rows in the response, such as "issues".
            **params: Query parameters.

        Yields:
            The rows.

        """
        offset = 0
        while True:
            page = self.get(path, offset=offset, limit=_PAGE, **params) or {}
            rows = page.get(key, [])
            yield from rows
            offset += len(rows)
            if not rows or offset >= page.get("total_count", 0):
                return

    def issue_url(self, issue_id: Any) -> str:
        """Build an issue's web URL.

        Args:
            issue_id: The issue id.

        Returns:
            The URL.

        """
        return f"{self.url}/issues/{issue_id}"

    def wiki_url(self, project: str, title: str, version: Any = None) -> str:
        """Build a wiki page's web URL.

        Args:
            project: Project identifier.
            title: Page title.
            version: Page version, for a link to that version.

        Returns:
            The URL.

        """
        base = f"{self.url}/projects/{project}/wiki/{urllib.parse.quote(title)}"
        return f"{base}/{version}" if version else base

    def _send(
        self,
        key: str,
        method: str,
        path: str,
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> Any:
        url = self.url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {"X-Redmine-API-Key": key, "Content-Type": "application/json"}
        error: Exception | None = None
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, data, headers, method=method)  # noqa: S310 - configured URL
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                    raw = response.read()
                    return json.loads(raw) if raw.strip() else None
            except urllib.error.HTTPError as e:
                if e.code < _SERVER_ERROR:
                    raise
                error = e
            except OSError as e:
                error = e
            time.sleep(3 * (attempt + 1))
        msg = f"{method} {path}: {error}"
        raise RedmineError(msg)
