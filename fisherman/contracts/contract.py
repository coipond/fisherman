"""A small declarative validator for configuration sections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fisherman.errors import InvalidConfigurationError

Check = Callable[[Any], bool]


@dataclass(frozen=True)
class _Rule:
    """One key's rule: whether it must be present and what its value must satisfy."""

    key: str
    required: bool
    check: Check | None
    message: str
    nested: Contract | None = None


class Contract:
    """Collects rules for a configuration section and validates data against them.

    Example:
        contract = Contract()
        contract.required("url", is_url, "must be an http(s) URL")
        contract.optional("timeout", is_int_at_least(1), "must be an integer >= 1")
        contract.validate(cfg, scope="model")

    """

    def __init__(self) -> None:
        """Create an empty contract."""
        self._rules: list[_Rule] = []

    def required(self, key: str, check: Check, message: str) -> Contract:
        """Add a key that must be present and pass `check`.

        Args:
            key: Key in the validated mapping.
            check: Predicate the value must satisfy.
            message: What is wrong when the predicate fails.

        Returns:
            The contract, for chaining.

        """
        self._rules.append(_Rule(key, required=True, check=check, message=message))
        return self

    def optional(self, key: str, check: Check, message: str) -> Contract:
        """Add a key that may be absent but, when present, must pass `check`.

        Args:
            key: Key in the validated mapping.
            check: Predicate the value must satisfy.
            message: What is wrong when the predicate fails.

        Returns:
            The contract, for chaining.

        """
        self._rules.append(_Rule(key, required=False, check=check, message=message))
        return self

    def nested(self, key: str, contract: Contract, *, required: bool = False) -> Contract:
        """Validate a nested mapping with its own contract.

        Args:
            key: Key of the nested mapping.
            contract: Contract for the nested mapping.
            required: Whether the nested mapping must be present.

        Returns:
            The contract, for chaining.

        """
        self._rules.append(_Rule(key, required=required, check=None, message="", nested=contract))
        return self

    def extend(self, other: Contract) -> Contract:
        """Combine two contracts.

        Args:
            other: Contract whose rules are added after this one's.

        Returns:
            A new contract with the rules of both.

        """
        combined = Contract()
        combined._rules = [*self._rules, *other._rules]
        return combined

    def errors(self, data: Any, scope: str = "") -> list[str]:
        """List every problem in `data`.

        Args:
            data: The mapping to validate.
            scope: Key path prefix for the messages (for example "sources[0]").

        Returns:
            Messages like "pipeline.threshold: must be a number between 0 and 1".
            Empty when `data` is valid.

        """
        prefix = f"{scope}." if scope else ""
        if not isinstance(data, dict):
            return [f"{scope or 'config'}: must be an object"]
        found: list[str] = []
        for rule in self._rules:
            if rule.key not in data:
                if rule.required:
                    found.append(f"{prefix}{rule.key}: is missing")
                continue
            value = data[rule.key]
            if rule.nested is not None:
                found.extend(rule.nested.errors(value, f"{prefix}{rule.key}"))
            elif rule.check is not None and not rule.check(value):
                found.append(f"{prefix}{rule.key}: {rule.message}")
        return found

    def validate(self, data: Any, scope: str = "") -> None:
        """Raise when `data` breaks the contract.

        Args:
            data: The mapping to validate.
            scope: Key path prefix for the messages.

        Raises:
            InvalidConfigurationError: With every problem found, one per line.

        """
        found = self.errors(data, scope)
        if found:
            raise InvalidConfigurationError("\n".join(found))
