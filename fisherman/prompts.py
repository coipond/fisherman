"""Prompt loading. Built-in prompts are generic examples; a private directory can override any of them.

Every prompt is a text file. Placeholders in {braces} are filled from the config's "prompt_vars"
(for example {principal}, the person whose authority agents may claim). Unknown placeholders stay as is.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

BUILTIN = Path(__file__).parent / "prompts"
NAMES = ("quick", "quick_examples", "reason", "extract", "verify")


class Prompts:
    def __init__(self, override_dir: Optional[str] = None, variables: Optional[Dict[str, str]] = None):
        self.override = Path(override_dir).expanduser() if override_dir else None
        self.variables = {"principal": "the maintainer", **(variables or {})}

    def get(self, name: str) -> str:
        if name not in NAMES:
            raise KeyError(name)
        path = BUILTIN / f"{name}.txt"
        if self.override and (self.override / f"{name}.txt").exists():
            path = self.override / f"{name}.txt"
        text = path.read_text().strip()
        return re.sub(r"\{(\w+)\}", lambda m: self.variables.get(m.group(1), m.group(0)), text)
