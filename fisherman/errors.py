"""All the errors Fisherman raises.

Everything Fisherman raises on purpose inherits from `BaseError`, so callers can catch
Fisherman failures without catching unrelated ones.
"""


class BaseError(Exception):
    """Base class for all the Fisherman errors."""


class InvalidConfigurationError(BaseError):
    """Raised when the configuration does not match its contract.

    The message lists every problem found, one per line, each prefixed with the key path
    (for example `pipeline.threshold: must be a number between 0 and 1`).
    """


class UnknownPluginError(BaseError):
    """Raised when a configured plug-in type is neither built in, nor registered, nor importable."""


class ModelError(BaseError):
    """Raised when the model server rejects a request or cannot be reached after retries."""


class ModelUnavailableError(ModelError):
    """Raised before a scan when the model server does not answer its health check.

    Nothing is read from the sources in that case, so no item is skipped.
    """


class RedmineError(BaseError):
    """Raised when Redmine rejects a request or cannot be reached after retries."""
