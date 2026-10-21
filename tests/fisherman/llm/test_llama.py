import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from fisherman.errors import ModelError
from fisherman.llm import Llama


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def respond(*bodies):
    """urlopen stand-in returning the given bodies (or raising given exceptions) in order."""
    queue = list(bodies)
    requests = []

    def urlopen(request, timeout):
        requests.append(request)
        body = queue.pop(0)
        if isinstance(body, Exception):
            raise body
        return Response(json.dumps(body).encode())

    return urlopen, requests


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


class LlamaTest(unittest.TestCase):
    def setUp(self):
        self.llm = Llama("http://srv/", key="secret", retries=2)

    def test_from_config_reads_the_key_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "k").write_text("abc\n")
            llm = Llama.from_config(
                {"url": "http://x", "key_file": str(Path(d) / "k"), "timeout": 5}
            )
        self.assertEqual(llm._headers["Authorization"], "Bearer abc")
        self.assertNotIn("Authorization", Llama.from_config({})._headers)

    def test_health(self):
        urlopen, _ = respond({"status": "ok"}, OSError("down"))
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertTrue(self.llm.health())
            self.assertFalse(self.llm.health())

    def test_tokenize_truncate_and_auth_header(self):
        urlopen, requests = respond(
            {"tokens": [1, 2, 3]}, {"tokens": [1, 2, 3]}, {"content": "ab"}, {"tokens": [1]}
        )
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(self.llm.tokenize("abc"), [1, 2, 3])
            self.assertEqual(self.llm.truncate("abc", 2), "ab")
            self.assertEqual(self.llm.truncate("a", 2), "a")
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer secret")
        self.assertEqual(requests[0].full_url, "http://srv/tokenize")

    def test_chat_drops_reasoning(self):
        urlopen, requests = respond(
            {"content": "<think>hmm</think>\nVERDICT: no"}, {"content": " yes "}
        )
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(self.llm.chat("s", "u", 10, think=True), "VERDICT: no")
            self.assertEqual(self.llm.chat("s", "u", 10, json_schema={}), "yes")
        first = json.loads(requests[0].data)
        self.assertFalse(first["prompt"].endswith("</think>\n\n"))
        self.assertIn("json_schema", json.loads(requests[1].data))

    def test_p_yes(self):
        top = [
            {"token": "Yes", "logprob": -0.1},
            {"token": "no", "logprob": -2.4},
            {"token": "x", "logprob": -1},
        ]
        urlopen, _ = respond(
            {"completion_probabilities": [{"top_logprobs": top}]},
            {"completion_probabilities": [{"top_logprobs": [{"token": "x", "logprob": 0}]}]},
        )
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertAlmostEqual(self.llm.p_yes("s", "u"), 0.909, places=3)
            self.assertEqual(self.llm.p_yes("s", "u"), 0.5)

    def test_final_errors_are_not_retried(self):
        urlopen, requests = respond(http_error(401))
        with mock.patch("urllib.request.urlopen", urlopen), self.assertRaises(ModelError):
            self.llm.tokenize("a")
        self.assertEqual(len(requests), 1)

    def test_transient_errors_are_retried_then_raise(self):
        urlopen, requests = respond(http_error(503), OSError("reset"))
        with (
            mock.patch("urllib.request.urlopen", urlopen),
            mock.patch("time.sleep"),
            self.assertRaises(ModelError),
        ):
            self.llm.tokenize("a")
        self.assertEqual(len(requests), 2)
