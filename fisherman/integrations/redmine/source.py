"""Redmine source: new or edited issue descriptions, comments, and wiki page changes.

Wiki changes come first: agents read rule and lessons pages on every run, so they matter most.
For wiki pages only the lines each version added or changed are checked, version by version, so
content that was added and later removed is still seen.
"""

from __future__ import annotations

import difflib
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from fisherman.contracts import (
    Contract,
    is_list_of_ints,
    is_list_of_strings,
    is_number_between,
    is_string,
)
from fisherman.integrations.redmine.client import Client
from fisherman.item import Item

if TYPE_CHECKING:
    from collections.abc import Iterator

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def added_lines(old: str, new: str) -> str:
    """Return the lines of `new` that are not in `old`, in order.

    Args:
        old: Previous text.
        new: Current text.

    Returns:
        The added or changed lines, blank lines dropped.

    """
    a, b = old.splitlines(), new.splitlines()
    out: list[str] = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(b[j1:j2])
    return "\n".join(line for line in out if line.strip())


def _projects_setting(value: Any) -> bool:
    return value == "all" or is_list_of_strings(value)


class RedmineSource:
    """Yields Redmine content changed since the last scan."""

    #: Contract for this source's configuration section (connection settings included)
    CONTRACT = Client.CONTRACT.extend(
        Contract()
        .optional("name", is_string, "must be a string")
        .optional("projects", _projects_setting, 'must be "all" or a list of identifiers')
        .optional("exclude_projects", is_list_of_strings, "must be a list of identifiers")
        .optional("skip_author_ids", is_list_of_ints, "must be a list of user ids")
        .optional("lookback_hours", is_number_between(0, 24 * 365), "must be a number of hours")
        .optional("overlap_minutes", is_number_between(0, 24 * 60), "must be a number of minutes")
    )

    def __init__(self, cfg: dict[str, Any], client: Client | None = None) -> None:
        """Create the source.

        Args:
            cfg: The section: projects ("all" or identifiers), exclude_projects (always add the
                alerts project), skip_author_ids (trusted people, the detector itself),
                lookback_hours (first scan, default 24), overlap_minutes (re-read window on
                every scan, default 10), plus the connection settings.
            client: Client to use instead of building one from `cfg`.

        """
        self.name = str(cfg.get("name", "redmine"))
        self._rm = client or Client.from_config(cfg)
        self._projects = cfg.get("projects", "all")
        self._exclude = set(cfg.get("exclude_projects", []))
        self._skip = {int(i) for i in cfg.get("skip_author_ids", [])}
        self._lookback = timedelta(hours=float(cfg.get("lookback_hours", 24)))
        self._overlap = timedelta(minutes=float(cfg.get("overlap_minutes", 10)))
        self._pending: str | None = None

    def items(self, state: dict[str, Any]) -> Iterator[Item]:
        """Yield wiki changes, then issue descriptions and comments, changed since the checkpoint.

        Args:
            state: This source's state: `since` (last scan time) and `wiki_versions` (last
                checked version per page).

        Yields:
            The changed content.

        """
        now = datetime.now(timezone.utc)
        since = (
            _parse(state["since"]) - self._overlap if state.get("since") else now - self._lookback
        )
        self._pending = now.strftime(_TIME_FORMAT)
        projects = self._project_map()
        versions = state.setdefault("wiki_versions", {})
        for project in projects.values():
            yield from self._wiki(project, since, versions)
        yield from self._issues(projects, since)

    def commit(self, state: dict[str, Any]) -> None:
        """Move the checkpoint to the time the scan started.

        Args:
            state: This source's state.

        """
        if self._pending:
            state["since"] = self._pending

    def _project_map(self) -> dict[int, dict[str, Any]]:
        return {
            p["id"]: p
            for p in self._rm.paged("/projects.json", "projects")
            if p["identifier"] not in self._exclude
            and (self._projects == "all" or p["identifier"] in self._projects)
        }

    def _wiki(
        self, project: dict[str, Any], since: datetime, versions: dict[str, int]
    ) -> Iterator[Item]:
        ident = project["identifier"]
        index = self._rm.get(f"/projects/{ident}/wiki/index.json")
        for page in (index or {}).get("wiki_pages", []):
            if _parse(page["updated_on"]) < since:
                continue
            title, current = page["title"], int(page["version"])
            key = f"{ident}:{title}"
            yield from self._page_versions(
                project, title, versions.get(key, current - 1) + 1, current
            )
            versions[key] = current

    def _page_versions(
        self, project: dict[str, Any], title: str, first: int, last: int
    ) -> Iterator[Item]:
        ident = project["identifier"]
        path = f"/projects/{ident}/wiki/{urllib.parse.quote(title)}"
        previous: str | None = None
        for version in range(max(first, 1), last + 1):
            page = (self._rm.get(f"{path}/{version}.json") or {}).get("wiki_page")
            if not page:
                continue
            if previous is None:
                older = (
                    (self._rm.get(f"{path}/{version - 1}.json") or {}).get("wiki_page")
                    if version > 1
                    else None
                )
                previous = (older or {}).get("text", "")
            text = added_lines(previous, page.get("text", ""))
            previous = page.get("text", "")
            author = page.get("author") or {}
            if text and author.get("id") not in self._skip:
                yield Item(
                    uid=f"redmine:wiki:{ident}:{title}:v{version}",
                    text=text,
                    author=author.get("name", ""),
                    author_id=author.get("id"),
                    source=f"Redmine wiki page {ident}:{title}, lines added in version {version} "
                    f"(project {project['name']})",
                    link=self._rm.wiki_url(ident, title, version),
                    context={"type": "wiki", "project": ident, "title": title, "version": version},
                )

    def _issues(self, projects: dict[int, dict[str, Any]], since: datetime) -> Iterator[Item]:
        rows = self._rm.paged(
            "/issues.json",
            "issues",
            status_id="*",
            sort="updated_on",
            updated_on=">=" + since.strftime(_TIME_FORMAT),
        )
        for row in rows:
            project = projects.get(row["project"]["id"])
            if not project:
                continue
            issue = (self._rm.get(f"/issues/{row['id']}.json", include="journals") or {}).get(
                "issue"
            )
            if issue:
                yield from self._issue_items(issue, project, since)

    def _issue_items(
        self, issue: dict[str, Any], project: dict[str, Any], since: datetime
    ) -> Iterator[Item]:
        iid = issue["id"]
        ctx = {"type": "issue", "id": iid, "project": project["identifier"]}
        where = f"issue #{iid} (project {project['name']})"
        author = issue.get("author") or {}
        desc = issue.get("description") or ""
        if (
            desc.strip()
            and _parse(issue["created_on"]) >= since
            and author.get("id") not in self._skip
        ):
            yield Item(
                f"redmine:issue:{iid}:description:{_digest(desc)}",
                desc,
                author.get("name", ""),
                author.get("id"),
                f"Redmine description of {where}",
                self._rm.issue_url(iid),
                ctx,
            )
        for journal in issue.get("journals", []):
            yield from self._journal_items(journal, iid, where, ctx, since)

    def _journal_items(
        self, journal: dict[str, Any], iid: int, where: str, ctx: dict[str, Any], since: datetime
    ) -> Iterator[Item]:
        user = journal.get("user") or {}
        if (
            _parse(journal.get("updated_on") or journal["created_on"]) < since
            or user.get("id") in self._skip
        ):
            return
        name, uid = user.get("name", ""), user.get("id")
        notes = (journal.get("notes") or "").strip()
        if notes:
            yield Item(
                f"redmine:journal:{journal['id']}:{_digest(notes)}",
                notes,
                name,
                uid,
                f"Redmine comment on {where}",
                f"{self._rm.issue_url(iid)}#note-{journal['id']}",
                ctx,
            )
        for detail in journal.get("details", []):
            if detail.get("property") != "attr" or detail.get("name") != "description":
                continue
            new = added_lines(detail.get("old_value") or "", detail.get("new_value") or "")
            if new:
                yield Item(
                    f"redmine:journal:{journal['id']}:description:{_digest(new)}",
                    new,
                    name,
                    uid,
                    f"Redmine description edit on {where} (lines added)",
                    self._rm.issue_url(iid),
                    ctx,
                )


def _parse(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, _TIME_FORMAT).replace(tzinfo=timezone.utc)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]  # noqa: S324 - an id, not security
