"""Settings of the detection pipeline (the "pipeline" configuration section)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from fisherman.contracts import (
    Contract,
    is_bool,
    is_int_at_least,
    is_list_of_strings,
    is_number_between,
    is_regex,
    one_of,
)

#: Every step, in the order they run
STEPS = ("quick", "reason", "claims")


@dataclass
class Settings:
    """Pipeline tuning. The defaults are the values validated on the reference test set.

    Attributes:
        steps: Which steps run. Without "quick", every item goes to the later steps.
        threshold: Quick-check score from which an item goes to the later steps.
        quick_examples: Append the few-shot examples to the quick-check prompt.
        window_tokens: Quick-check window size.
        stride_tokens: Quick-check window stride.
        max_quick_tokens: Tokens of each item the quick check reads.
        max_reason_tokens: Tokens of each item the reasoning check reads.
        reason_budget: Tokens the reasoning check may generate, reasoning included.
        extract_budget: Tokens the claim extraction may generate.
        alert_on_extract_error: Alert when the claim extraction is not valid JSON.
        max_item_chars: Longer items are split into parts of about this size.
        principal_aliases: Other names of the principal, for spotting requests addressed to them.
        to_principal_pattern: Regex for sentences addressed to the principal; replaces the
            default built from the principal's names.
        rule_page_pattern: Regex for names of rule pages. A claim that cites a matching page
            which really appears in the text points at the rules instead of inventing one.
        context_ref_pattern: Regex whose first group finds other contexts a claim points at
            (for example issue numbers), so their records are checked too.

    """

    steps: list[str] = field(default_factory=lambda: list(STEPS))
    threshold: float = 0.5
    quick_examples: bool = True
    window_tokens: int = 250
    stride_tokens: int = 200
    max_quick_tokens: int = 800
    max_reason_tokens: int = 1200
    reason_budget: int = 1400
    extract_budget: int = 1000
    alert_on_extract_error: bool = False
    max_item_chars: int = 4000
    principal_aliases: list[str] = field(default_factory=list)
    to_principal_pattern: str = ""
    rule_page_pattern: str = ""
    context_ref_pattern: str = r"#(\d{3,6})\b"

    #: Contract for the "pipeline" configuration section
    CONTRACT = (
        Contract()
        .optional("steps", one_of(*STEPS), f"must be a list from {list(STEPS)}")
        .optional("threshold", is_number_between(0, 1), "must be a number between 0 and 1")
        .optional("quick_examples", is_bool, "must be true or false")
        .optional("window_tokens", is_int_at_least(16), "must be an integer >= 16")
        .optional("stride_tokens", is_int_at_least(1), "must be an integer >= 1")
        .optional("max_quick_tokens", is_int_at_least(16), "must be an integer >= 16")
        .optional("max_reason_tokens", is_int_at_least(16), "must be an integer >= 16")
        .optional("reason_budget", is_int_at_least(64), "must be an integer >= 64")
        .optional("extract_budget", is_int_at_least(64), "must be an integer >= 64")
        .optional("alert_on_extract_error", is_bool, "must be true or false")
        .optional("max_item_chars", is_int_at_least(200), "must be an integer >= 200")
        .optional("principal_aliases", is_list_of_strings, "must be a list of strings")
        .optional("to_principal_pattern", is_regex, "must be a valid regular expression")
        .optional("rule_page_pattern", is_regex, "must be a valid regular expression")
        .optional("context_ref_pattern", is_regex, "must be a valid regular expression")
    )

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Settings:
        """Build settings from the "pipeline" configuration section.

        Args:
            cfg: The section. Unknown keys are ignored; missing keys keep their defaults.

        Returns:
            The settings.

        """
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in cfg.items() if k in known}
        if isinstance(values.get("steps"), str):
            values["steps"] = [values["steps"]]
        return cls(**values)
