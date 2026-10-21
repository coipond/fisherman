"""Reusable predicates for contracts."""

from __future__ import annotations

import re
from typing import Any, Callable

Check = Callable[[Any], bool]


def is_string(value: Any) -> bool:
    """Check for a non-empty string.

    Args:
        value: Value to check.

    Returns:
        True for a non-empty string.

    """
    return isinstance(value, str) and bool(value)


def is_bool(value: Any) -> bool:
    """Check for a boolean.

    Args:
        value: Value to check.

    Returns:
        True for True or False.

    """
    return isinstance(value, bool)


def is_url(value: Any) -> bool:
    """Check for an http or https URL.

    Args:
        value: Value to check.

    Returns:
        True for a string starting with http:// or https://.

    """
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def is_regex(value: Any) -> bool:
    """Check for a string that compiles as a regular expression.

    Args:
        value: Value to check.

    Returns:
        True for a valid regular expression.

    """
    if not isinstance(value, str):
        return False
    try:
        re.compile(value)
    except re.error:
        return False
    return True


def is_list_of_strings(value: Any) -> bool:
    """Check for a list of non-empty strings.

    Args:
        value: Value to check.

    Returns:
        True for a list whose items are all non-empty strings (an empty list passes).

    """
    return isinstance(value, list) and all(is_string(v) for v in value)


def is_list_of_ints(value: Any) -> bool:
    """Check for a list of integers.

    Args:
        value: Value to check.

    Returns:
        True for a list whose items are all integers (an empty list passes).

    """
    return isinstance(value, list) and all(
        isinstance(v, int) and not isinstance(v, bool) for v in value
    )


def is_number_between(low: float, high: float) -> Check:
    """Build a check for a number in a closed range.

    Args:
        low: Smallest allowed value.
        high: Largest allowed value.

    Returns:
        A predicate.

    """

    def check(value: Any) -> bool:
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
        )

    return check


def is_int_at_least(low: int) -> Check:
    """Build a check for an integer of at least `low`.

    Args:
        low: Smallest allowed value.

    Returns:
        A predicate.

    """

    def check(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= low

    return check


def one_of(*allowed: str) -> Check:
    """Build a check for a list whose items all come from `allowed`.

    Args:
        *allowed: The permitted values.

    Returns:
        A predicate that also accepts a single string from `allowed`.

    """

    def check(value: Any) -> bool:
        values = [value] if isinstance(value, str) else value
        return isinstance(values, list) and bool(values) and all(v in allowed for v in values)

    return check
