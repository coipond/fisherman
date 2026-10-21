import unittest

from fisherman.pipeline import Destinations


class DestinationsTest(unittest.TestCase):
    def setUp(self):
        self.allow = Destinations.from_config(
            {"github_owners": ["My-Org"], "hosts": ["redmine.example.com"]}
        )

    def test_outside(self):
        self.assertTrue(self.allow.outside("rubygems", "gem push foo"))
        self.assertTrue(self.allow.outside("github.com/other/x"))
        self.assertTrue(self.allow.outside("git@github.com:other/x.git"))
        self.assertTrue(self.allow.outside("https://webhook.example/x"))

    def test_inside(self):
        self.assertFalse(self.allow.outside("github.com/my-org/x"))
        self.assertFalse(self.allow.outside("https://redmine.example.com/issues/1"))
        self.assertFalse(self.allow.outside("origin", "pushed the branch"))

    def test_custom_registries(self):
        self.assertTrue(Destinations(registries=r"\bartifactory\b").outside("artifactory"))
