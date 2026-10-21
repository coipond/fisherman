"""Redmine plug-ins for Fisherman: a source, a records plug-in and an alerts plug-in.

Installing this package registers the `redmine` type in the `fisherman.sources`,
`fisherman.records` and `fisherman.alerts` entry point groups. Connection settings (`url`,
`key_file` or `key_files`, `timeout`) can be given once in a top-level `"redmine"` section of the
Fisherman configuration and are shared by all three.
"""

from fisherman_redmine.version import VERSION

__version__ = VERSION
__all__ = ["VERSION", "__version__"]
