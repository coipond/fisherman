"""Configuration: one JSON file. See examples/config.example.json for every option.

Plug-in sections may leave out url/key_file; they then reuse the "redmine" section's values.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load(path: str) -> Dict[str, Any]:
    cfg = json.loads(Path(path).expanduser().read_text())
    shared = cfg.get("redmine", {})
    for section in [*cfg.get("sources", []), cfg.get("records") or {}, cfg.get("alerts") or {}]:
        if section.get("type") == "redmine":
            for k in ("url", "key", "key_file", "timeout"):
                if k in shared and k not in section:
                    section[k] = shared[k]
    cfg.setdefault("model", {})
    cfg.setdefault("pipeline", {})
    cfg.setdefault("alerts", {"type": "stdout"})
    cfg.setdefault("records", {"type": "none"})
    cfg.setdefault("sources", [])
    cfg.setdefault("state_file", "~/.local/state/fisherman/state.json")
    return cfg
