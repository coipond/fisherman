"""Prompt templates: generic built-ins, any of which a private directory can replace."""

from __future__ import annotations

import re
from pathlib import Path

#: Built-in templates shipped with Fisherman
TEMPLATES_DIR = Path(__file__).parent / "templates"

#: Every template a pipeline uses
NAMES = ("quick", "quick_examples", "reason", "extract", "verify")


class Prompts:
    """Loads prompt templates and fills their `{placeholders}`.

    Note:
        Keep tuned prompts out of public repositories: anyone who knows the exact wording and
        examples can search for phrasing that slips past them.

    """

    def __init__(
        self, override_dir: str | None = None, variables: dict[str, str] | None = None
    ) -> None:
        """Create a loader.

        Args:
            override_dir: Directory whose `<name>.txt` files replace the built-in templates.
            variables: Values for `{placeholders}`. `principal` names the person whose authority
                agents may claim; it defaults to "the maintainer".

        """
        self._override = Path(override_dir).expanduser() if override_dir else None
        self.variables = {"principal": "the maintainer", **(variables or {})}

    def get(self, name: str) -> str:
        """Return a filled template.

        Args:
            name: One of `NAMES`.

        Returns:
            The template text with known placeholders filled. Unknown placeholders stay as is.

        Raises:
            KeyError: For an unknown template name.

        """
        if name not in NAMES:
            raise KeyError(name)
        path = TEMPLATES_DIR / f"{name}.txt"
        if self._override and (self._override / f"{name}.txt").exists():
            path = self._override / f"{name}.txt"
        text = path.read_text(encoding="utf-8").strip()
        return re.sub(r"\{(\w+)\}", lambda m: self.variables.get(m.group(1), m.group(0)), text)
