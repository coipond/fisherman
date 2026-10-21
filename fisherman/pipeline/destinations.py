"""Decides whether a reported send goes somewhere outside the allowed places."""

from __future__ import annotations

import re
from typing import Any

from fisherman.contracts import Contract, is_list_of_strings, is_regex

#: Registries, paste sites and request catchers that always count as outside
DEFAULT_REGISTRIES = (
    r"\b(gem push|rubygems|npm publish|npmjs|pypi|twine upload|gist|pastebin|paste\.ee|"
    r"hastebin|webhook\.site|transfer\.sh|requestbin|ngrok)\b"
)


class Destinations:
    """An allowlist of GitHub owners and hosts."""

    #: Contract for the "destinations" configuration section
    CONTRACT = (
        Contract()
        .optional("github_owners", is_list_of_strings, "must be a list of strings")
        .optional("hosts", is_list_of_strings, "must be a list of strings")
        .optional("registries", is_regex, "must be a valid regular expression")
    )

    def __init__(
        self,
        github_owners: list[str] | None = None,
        hosts: list[str] | None = None,
        registries: str = DEFAULT_REGISTRIES,
    ) -> None:
        """Create an allowlist.

        Args:
            github_owners: GitHub users and organisations that are yours.
            hosts: Other hosts that are yours. github.com itself is always allowed.
            registries: Regex for destinations that always count as outside.

        """
        self._owners = {o.lower() for o in github_owners or []}
        self._hosts = {h.lower() for h in hosts or []} | {"github.com", "api.github.com"}
        self._registries = re.compile(registries, re.IGNORECASE)

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Destinations:
        """Build an allowlist from the "destinations" configuration section.

        Args:
            cfg: The section: github_owners, hosts, registries.

        Returns:
            The allowlist.

        """
        return cls(
            cfg.get("github_owners"), cfg.get("hosts"), cfg.get("registries", DEFAULT_REGISTRIES)
        )

    def outside(self, destination: str, quote: str = "") -> bool:
        """Check a reported send.

        Args:
            destination: The destination as the extraction step reported it.
            quote: The sentence that reported the send.

        Returns:
            True when the destination or the sentence names a registry or paste site, a GitHub
            owner that is not yours, or a host that is not yours.

        """
        text = f"{destination} {quote}"
        if self._registries.search(text):
            return True
        owners = re.findall(r"github\.com[/:]([\w.-]+)/", text)
        if any(owner.lower() not in self._owners for owner in owners):
            return True
        hosts = re.findall(r"https?://([\w.-]+)", text)
        return any(host.lower() not in self._hosts for host in hosts)
