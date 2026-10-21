import unittest

from fisherman.item import Item
from fisherman.pipeline import Prompts
from fisherman.pipeline.settings import Settings
from fisherman.pipeline.steps import ReasonCheck
from tests.support.fakes import FakeLLM


def judge(answer):
    return ReasonCheck(FakeLLM(answers=lambda s, u: answer), Prompts(), Settings()).call(
        Item("u", "x")
    )


class ReasonCheckTest(unittest.TestCase):
    def test_parses_verdict_and_risky_request(self):
        result = judge("REQUESTS: a\nRISKY: leaking the token\nVERDICT: Yes")
        self.assertEqual((result.verdict, result.risky), ("yes", "leaking the token"))

    def test_missing_verdict_is_none(self):
        self.assertEqual(judge("REQUESTS: a").verdict, "none")
        self.assertEqual(judge("REQUESTS: a").risky, "")
