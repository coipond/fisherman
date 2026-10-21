import unittest

from fisherman.contracts import Contract, is_int_at_least, is_string
from fisherman.errors import InvalidConfigurationError

INNER = Contract().required("url", is_string, "must be a string")
OUTER = (
    Contract()
    .required("name", is_string, "must be a string")
    .optional("size", is_int_at_least(1), "must be an integer >= 1")
    .nested("model", INNER)
    .nested("must", INNER, required=True)
)


class ContractTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(OUTER.errors({"name": "a", "must": {"url": "u"}}), [])

    def test_every_problem_with_its_path(self):
        errors = OUTER.errors({"size": 0, "model": {"url": 1}}, "root")
        self.assertEqual(
            errors,
            [
                "root.name: is missing",
                "root.size: must be an integer >= 1",
                "root.model.url: must be a string",
                "root.must: is missing",
            ],
        )

    def test_non_mapping(self):
        self.assertEqual(OUTER.errors([]), ["config: must be an object"])

    def test_validate_raises_with_all_messages(self):
        with self.assertRaises(InvalidConfigurationError) as ctx:
            OUTER.validate({})
        self.assertIn("name: is missing\nmust: is missing", str(ctx.exception))
        OUTER.validate({"name": "a", "must": {"url": "u"}})

    def test_extend(self):
        combined = INNER.extend(Contract().required("key", is_string, "must be a string"))
        self.assertEqual(combined.errors({}), ["url: is missing", "key: is missing"])
