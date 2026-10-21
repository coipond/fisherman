"""Checkpoints and handled item ids, kept in one JSON file written atomically."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict


class State:
    def __init__(self, path: str, keep_days: float = 30):
        self.path = Path(path).expanduser()
        self.keep = keep_days * 86400
        self.data: Dict[str, Any] = {"sources": {}, "seen": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            self.data.setdefault("sources", {})
            self.data.setdefault("seen", {})

    def source(self, name: str) -> Dict[str, Any]:
        return self.data["sources"].setdefault(name, {})

    def seen(self, uid: str) -> bool:
        return uid in self.data["seen"]

    def mark(self, uid: str) -> None:
        self.data["seen"][uid] = int(time.time())

    def save(self) -> None:
        cutoff = time.time() - self.keep
        self.data["seen"] = {k: v for k, v in self.data["seen"].items() if v >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)
