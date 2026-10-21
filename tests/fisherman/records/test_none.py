import unittest

from fisherman.item import Item
from fisherman.records.none import NoRecords


class NoRecordsTest(unittest.TestCase):
    def test_empty_record(self):
        self.assertEqual(NoRecords({}).records(Item("u", "t"), ["1"]), [])
