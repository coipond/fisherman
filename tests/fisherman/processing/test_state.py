import tempfile
import time
import unittest
from pathlib import Path

from fisherman.processing.state import State


class StateTest(unittest.TestCase):
    def test_roundtrip_and_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "nested" / "state.json")
            state = State(path)
            state.source("redmine")["since"] = "x"
            state.mark("a")
            state.data["seen"]["old"] = int(time.time()) - 40 * 86400
            state.save()
            loaded = State(path)
            self.assertTrue(loaded.seen("a"))
            self.assertFalse(loaded.seen("old"))
            self.assertEqual(loaded.source("redmine"), {"since": "x"})
            loaded.replace_source("redmine", {})
            self.assertEqual(loaded.source("redmine"), {})
