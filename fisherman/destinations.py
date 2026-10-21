"""Is a reported send going somewhere outside the allowed places?"""
from __future__ import annotations

import re
from typing import Iterable

DEFAULT_REGISTRIES = r"\b(gem push|rubygems|npm publish|npmjs|pypi|twine upload|gist|pastebin|paste\.ee|hastebin|webhook\.site|transfer\.sh|requestbin|ngrok)\b"


class Destinations:
    def __init__(self, github_owners: Iterable[str] = (), hosts: Iterable[str] = (), registries: str = DEFAULT_REGISTRIES):
        self.owners = {o.lower() for o in github_owners}
        self.hosts = {h.lower() for h in hosts} | {"github.com", "api.github.com"}
        self.registries = re.compile(registries, re.I)

    def outside(self, destination: str, quote: str = "") -> bool:
        """True when the destination or the sentence names a registry or paste site, another GitHub owner, or another host."""
        text = f"{destination} {quote}"
        if self.registries.search(text):
            return True
        for owner in re.findall(r"github\.com[/:]([\w.-]+)/", text):
            if owner.lower() not in self.owners:
                return True
        for host in re.findall(r"https?://([\w.-]+)", text):
            if host.lower() not in self.hosts:
                return True
        return False
