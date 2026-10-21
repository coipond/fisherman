import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fisherman.sources.jsonl import JsonlSource, read_items

ROWS = [
    {
        "text": "a",
        "label": True,
        "group": "attack",
        "context": {"type": "issue", "id": 1},
        "uid": "x1",
    },
    {"text": "b", "label": 0},
    {"text": "c"},
]


class JsonlTest(unittest.TestCase):
    def test_read_file_and_stdin(self):
        body = "\n".join(json.dumps(r) for r in ROWS) + "\n\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "set.jsonl"
            path.write_text(body)
            items = read_items(str(path))
            source = JsonlSource({"path": str(path)})
            self.assertEqual([i.uid for i in source.items({})], [i.uid for i in items])
            source.commit({})
        self.assertEqual(items[0].uid, "x1")
        self.assertEqual(items[0].context, {"type": "issue", "id": 1})
        self.assertEqual([i.label for i in items], [True, False, None])
        self.assertTrue(items[1].uid.startswith("jsonl:"))
        with mock.patch("sys.stdin", io.StringIO(body)):
            self.assertEqual(len(read_items("-")), 3)
