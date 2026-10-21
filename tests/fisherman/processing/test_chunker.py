import unittest

from fisherman.item import Item
from fisherman.processing.chunker import chunks


class ChunkerTest(unittest.TestCase):
    def test_splits_at_lines(self):
        item = Item("u", "\n".join(["x" * 30] * 10), "a", source="src")
        parts = list(chunks(item, 100))
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(p.text for p in parts), item.text)
        self.assertEqual((parts[0].uid, parts[0].source), ("u:part1", "src (part 1)"))

    def test_short_items_untouched(self):
        item = Item("u", "short")
        self.assertEqual(list(chunks(item, 100)), [item])
