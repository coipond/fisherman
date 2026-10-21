import unittest

from fisherman.contracts import (
    is_bool,
    is_int_at_least,
    is_list_of_ints,
    is_list_of_strings,
    is_number_between,
    is_regex,
    is_string,
    is_url,
    one_of,
)


class RulesTest(unittest.TestCase):
    def test_rules(self):
        cases = [
            (is_string, ["a"], ["", 1, None]),
            (is_bool, [True, False], [0, "true"]),
            (is_url, ["http://a", "https://b"], ["ftp://c", 1]),
            (is_regex, [r"\d+"], ["(", 1]),
            (is_list_of_strings, [[], ["a"]], [["a", ""], "a"]),
            (is_list_of_ints, [[], [1]], [[True], ["1"]]),
            (is_number_between(0, 1), [0, 0.5, 1], [2, True, "0"]),
            (is_int_at_least(2), [2, 3], [1, 2.5, True]),
            (one_of("a", "b"), ["a", ["a", "b"]], [[], ["c"], 1]),
        ]
        for check, good, bad in cases:
            for value in good:
                self.assertTrue(check(value), (check, value))
            for value in bad:
                self.assertFalse(check(value), (check, value))
