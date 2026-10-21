"""Configuration: one JSON file, validated before anything runs.

See `examples/config.example.json` for every option. Plug-in sections may leave out connection
settings (`url`, `key_file`, `key_files`, `timeout`) and share them through a top-level section
named after their type, so for example three `"type": "redmine"` sections can share one
`"redmine": {"url": ..., "key_file": ...}`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fisherman.contracts import Contract, is_string
from fisherman.errors import InvalidConfigurationError, UnknownPluginError
from fisherman.llm import Llama
from fisherman.pipeline import Destinations
from fisherman.pipeline.settings import Settings
from fisherman.plugins import resolve

#: Default location of the scanner's state
DEFAULT_STATE_FILE = "~/.local/state/fisherman/state.json"

# Connection settings a plug-in section inherits from the integration's shared section
_SHARED_KEYS = ("url", "key_file", "key_files", "timeout")


def _is_section(value: Any) -> bool:
    return isinstance(value, dict) and is_string(value.get("type"))


def _is_section_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_section(v) for v in value)


def _is_string_map(value: Any) -> bool:
    return isinstance(value, dict) and all(isinstance(v, str) for v in value.values())


#: Contract for the whole configuration (plug-in sections are checked by their own contracts)
CONTRACT = (
    Contract()
    .nested("model", Llama.CONTRACT)
    .nested("pipeline", Settings.CONTRACT)
    .nested("destinations", Destinations.CONTRACT)
    .optional("prompts_dir", is_string, "must be a directory path")
    .optional("prompt_vars", _is_string_map, "must map names to strings")
    .optional("sources", _is_section_list, 'must be a list of objects with a "type"')
    .optional("records", _is_section, 'must be an object with a "type"')
    .optional("alerts", _is_section, 'must be an object with a "type"')
    .optional("state_file", is_string, "must be a file path")
)


def load(path: str) -> dict[str, Any]:
    """Read, complete and validate a configuration file.

    Args:
        path: Path of the JSON file.

    Returns:
        The configuration with defaults filled in.

    Raises:
        InvalidConfigurationError: When the file is not valid JSON or breaks a contract. The
            message lists every problem with its key path.

    """
    try:
        cfg = json.loads(Path(path).expanduser().read_text())
    except (OSError, ValueError) as e:
        msg = f"{path}: {e}"
        raise InvalidConfigurationError(msg) from e
    return prepare(cfg)


def prepare(cfg: dict[str, Any]) -> dict[str, Any]:
    """Complete and validate an already parsed configuration.

    Args:
        cfg: The parsed configuration.

    Returns:
        The configuration with defaults filled in.

    Raises:
        InvalidConfigurationError: When it breaks a contract.

    """
    errors = CONTRACT.errors(cfg)
    if not isinstance(cfg, dict):
        raise InvalidConfigurationError("\n".join(errors))
    cfg.setdefault("model", {})
    cfg.setdefault("pipeline", {})
    cfg.setdefault("records", {"type": "none"})
    cfg.setdefault("alerts", {"type": "stdout"})
    cfg.setdefault("state_file", DEFAULT_STATE_FILE)
    sources = cfg.setdefault("sources", [])
    sections = [
        *(
            ("sources", f"sources[{n}]", s)
            for n, s in enumerate(sources if isinstance(sources, list) else [])
        ),
        ("records", "records", cfg["records"]),
        ("alerts", "alerts", cfg["alerts"]),
    ]
    for kind, scope, section in sections:
        if _is_section(section):
            errors.extend(_section_errors(cfg, kind, scope, section))
    if errors:
        raise InvalidConfigurationError("\n".join(errors))
    return cfg


def _section_errors(
    cfg: dict[str, Any], kind: str, scope: str, section: dict[str, Any]
) -> list[str]:
    shared = cfg.get(section["type"])
    if isinstance(shared, dict):
        for key in _SHARED_KEYS:
            if key in shared and key not in section:
                section[key] = shared[key]
    try:
        contract = getattr(resolve(kind, section["type"]), "CONTRACT", None)
    except UnknownPluginError as e:
        return [f"{scope}.type: {e}"]
    return contract.errors(section, scope) if isinstance(contract, Contract) else []
