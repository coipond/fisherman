import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from fisherman.errors import RedmineError
from fisherman.integrations.redmine.client import Client


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def error(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"nope"))


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def serve(self, handler):
        def urlopen(request, timeout):
            self.calls.append(
                (request.get_method(), request.full_url, request.get_header("X-redmine-api-key"))
            )
            result = handler(request)
            if isinstance(result, Exception):
                raise result
            return Response(json.dumps(result).encode() if result is not None else b"")

        return mock.patch("urllib.request.urlopen", urlopen)

    def test_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("a", "b"):
                (Path(d) / name).write_text(name + "\n")
            client = Client.from_config({"url": "https://rm/", "key_files": [f"{d}/a", f"{d}/b"]})
            self.assertEqual(client._keys, ["a", "b"])
            self.assertEqual(
                Client.from_config({"url": "https://rm", "key_file": f"{d}/a"})._keys, ["a"]
            )
        with self.assertRaises(RedmineError):
            Client.from_config({"url": "https://rm"})

    def test_get_falls_back_to_the_next_key_and_returns_none_when_hidden(self):
        client = Client("https://rm", ["a", "b"])
        with self.serve(
            lambda r: error(403) if r.get_header("X-redmine-api-key") == "a" else {"ok": 1}
        ):
            self.assertEqual(client.get("/x.json", include="journals"), {"ok": 1})
        self.assertEqual(self.calls[1][1], "https://rm/x.json?include=journals")
        with self.serve(lambda r: error(404)):
            self.assertIsNone(client.get("/missing.json"))

    def test_post_uses_only_the_first_key_and_raises_on_client_errors(self):
        client = Client("https://rm", ["a", "b"])
        with self.serve(lambda r: None):
            self.assertIsNone(client.post("/issues.json", {"issue": {}}))
        self.assertEqual(self.calls[-1][0], "POST")
        with self.serve(lambda r: error(422)), self.assertRaises(RedmineError):
            client.post("/issues.json", {})
        with self.serve(lambda r: error(403)), self.assertRaises(RedmineError):
            client.post("/issues.json", {})
        self.assertEqual({c[2] for c in self.calls}, {"a"})

    def test_server_errors_are_retried(self):
        replies = [error(502), OSError("reset"), {"ok": 1}]
        client = Client("https://rm", ["a"])
        with self.serve(lambda r: replies.pop(0)), mock.patch("time.sleep"):
            self.assertEqual(client.get("/x.json"), {"ok": 1})
        with (
            self.serve(lambda r: error(500)),
            mock.patch("time.sleep"),
            self.assertRaises(RedmineError),
        ):
            client.get("/x.json")

    def test_paged(self):
        pages = {0: {"rows": [1, 2], "total_count": 3}, 2: {"rows": [3], "total_count": 3}}
        client = Client("https://rm", ["a"])
        with self.serve(lambda r: pages[int(r.full_url.split("offset=")[1].split("&")[0])]):
            self.assertEqual(list(client.paged("/rows.json", "rows")), [1, 2, 3])

    def test_urls(self):
        client = Client("https://rm", ["a"])
        self.assertEqual(client.issue_url(5), "https://rm/issues/5")
        self.assertEqual(client.wiki_url("p", "A B", 3), "https://rm/projects/p/wiki/A%20B/3")
        self.assertEqual(client.wiki_url("p", "A"), "https://rm/projects/p/wiki/A")
