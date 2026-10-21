import tempfile
import unittest
from pathlib import Path

from fisherman.pipeline import Prompts
from fisherman.pipeline.prompts import NAMES


class PromptsTest(unittest.TestCase):
    def test_every_builtin_exists_and_fills_the_principal(self):
        prompts = Prompts(variables={"principal": "Alice"})
        for name in NAMES:
            self.assertTrue(prompts.get(name))
        self.assertIn("Alice", prompts.get("quick"))
        self.assertIn("the maintainer", Prompts().get("quick"))

    def test_private_directory_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "verify.txt").write_text("About {principal} and {unknown}.")
            prompts = Prompts(d, {"principal": "Alice"})
            self.assertEqual(prompts.get("verify"), "About Alice and {unknown}.")
            self.assertIn("Alice", prompts.get("quick"))

    def test_unknown_name(self):
        with self.assertRaises(KeyError):
            Prompts().get("nope")
