import unittest

from fisherman.item import Item
from fisherman.pipeline import Prompts
from fisherman.pipeline.settings import Settings
from fisherman.pipeline.steps import QuickCheck
from tests.support.fakes import FakeLLM


class QuickCheckTest(unittest.TestCase):
    def test_a_risky_sentence_late_in_a_long_text_is_found(self):
        llm = FakeLLM(risky="publish")
        text = " ".join(["word"] * 600 + ["publish"] + ["word"] * 100)
        self.assertEqual(QuickCheck(llm, Prompts(), Settings()).call(Item("u", text)), 0.9)
        self.assertGreater(len(llm.calls), 1)

    def test_windows_cover_every_token_and_end_aligned(self):
        check = QuickCheck(FakeLLM(), Prompts(), Settings(window_tokens=4, stride_tokens=3))
        windows = check.windows(list(range(10)))
        self.assertEqual(windows[0], [0, 1, 2, 3])
        self.assertEqual(windows[-1], [6, 7, 8, 9])
        self.assertEqual(check.windows([]), [[]])

    def test_examples_can_be_left_out(self):
        seen = []

        class Recording(FakeLLM):
            def p_yes(self, system, user):
                seen.append(system)
                return 0.0

        QuickCheck(Recording(), Prompts(), Settings(quick_examples=False)).call(Item("u", "x"))
        self.assertNotIn("Examples.", seen[0])
