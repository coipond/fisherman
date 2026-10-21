"""Redmine source: new or edited issue descriptions, comments (journal notes) and wiki page changes.

Wiki changes are yielded first: agents read rule and lessons pages on every run, so they matter most.
For wiki pages only the lines a version added or changed are checked, version by version, so content
that was added and later removed is still seen.

Config:
  url, key_file              Redmine and an API key with read access to the projects to watch
  projects                   "all" (every project the key can see) or a list of identifiers
  exclude_projects           identifiers to skip (always put the alerts project here)
  skip_author_ids            Redmine user ids whose content is not checked (trusted people, the detector itself)
  lookback_hours             how far back the first run looks (default 24)
  overlap_minutes            re-read window on every run, for clock skew (default 10)
"""
from __future__ import annotations

import difflib
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

from ..item import Item
from ..redmine import Redmine


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def added_lines(old: str, new: str) -> str:
    """Lines present in new but not in old, in order (for wiki version diffs)."""
    a, b = old.splitlines(), new.splitlines()
    out: List[str] = []
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(b[j1:j2])
    return "\n".join(line for line in out if line.strip())


class RedmineSource:
    def __init__(self, cfg: Dict[str, Any], client: Optional[Redmine] = None):
        self.name = cfg.get("name", "redmine")
        self.rm = client or Redmine.from_config(cfg)
        self.projects = cfg.get("projects", "all")
        self.exclude = set(cfg.get("exclude_projects", []))
        self.skip_authors = {int(i) for i in cfg.get("skip_author_ids", [])}
        self.lookback = timedelta(hours=float(cfg.get("lookback_hours", 24)))
        self.overlap = timedelta(minutes=float(cfg.get("overlap_minutes", 10)))
        self._pending: Optional[str] = None

    # projects

    def _project_map(self) -> Dict[int, Dict[str, Any]]:
        out = {}
        for p in self.rm.paged("/projects.json", "projects"):
            if p["identifier"] in self.exclude:
                continue
            if self.projects != "all" and p["identifier"] not in self.projects:
                continue
            out[p["id"]] = p
        return out

    # the source interface

    def items(self, state: Dict[str, Any]) -> Iterator[Item]:
        now = datetime.now(timezone.utc)
        since = _parse(state["since"]) - self.overlap if state.get("since") else now - self.lookback
        self._pending = _iso(now)
        projects = self._project_map()
        versions = state.setdefault("wiki_versions", {})
        for p in projects.values():
            yield from self._wiki(p, since, versions)
        yield from self._issues(projects, since)

    def commit(self, state: Dict[str, Any]) -> None:
        if self._pending:
            state["since"] = self._pending

    # wiki

    def _wiki(self, project: Dict[str, Any], since: datetime, versions: Dict[str, int]) -> Iterator[Item]:
        ident = project["identifier"]
        index = self.rm.get(f"/projects/{ident}/wiki/index.json")
        if not index:
            return
        for page in index.get("wiki_pages", []):
            if _parse(page["updated_on"]) < since:
                continue
            title, current = page["title"], int(page["version"])
            key = f"{ident}:{title}"
            path = f"/projects/{ident}/wiki/{urllib.parse.quote(title)}"
            first = versions.get(key, current - 1) + 1
            prev_text = None
            for v in range(max(first, 1), current + 1):
                cur = (self.rm.get(f"{path}/{v}.json") or {}).get("wiki_page")
                if not cur:
                    continue
                if prev_text is None:
                    old = (self.rm.get(f"{path}/{v - 1}.json") or {}).get("wiki_page") if v > 1 else None
                    prev_text = (old or {}).get("text", "")
                text = added_lines(prev_text, cur.get("text", ""))
                prev_text = cur.get("text", "")
                author = cur.get("author") or {}
                if text and author.get("id") not in self.skip_authors:
                    yield Item(
                        uid=f"redmine:wiki:{ident}:{title}:v{v}",
                        text=text,
                        author=author.get("name", ""),
                        author_id=author.get("id"),
                        source=f"Redmine wiki page {ident}:{title}, lines added in version {v} (project {project['name']})",
                        link=self.rm.wiki_url(ident, title, v),
                        context={"type": "wiki", "project": ident, "title": title, "version": v},
                    )
            versions[key] = current

    # issues

    def _issues(self, projects: Dict[int, Dict[str, Any]], since: datetime) -> Iterator[Item]:
        for row in self.rm.paged("/issues.json", "issues", status_id="*", sort="updated_on",
                                 updated_on=">=" + _iso(since)):
            project = projects.get(row["project"]["id"])
            if not project:
                continue
            issue = (self.rm.get(f"/issues/{row['id']}.json", include="journals") or {}).get("issue")
            if issue:
                yield from self._issue_items(issue, project, since)

    def _issue_items(self, issue: Dict[str, Any], project: Dict[str, Any], since: datetime) -> Iterator[Item]:
        iid = issue["id"]
        ctx = {"type": "issue", "id": iid, "project": project["identifier"]}
        where = f"issue #{iid} (project {project['name']})"
        author = issue.get("author") or {}
        desc = issue.get("description") or ""
        if desc.strip() and _parse(issue["created_on"]) >= since and author.get("id") not in self.skip_authors:
            yield Item(f"redmine:issue:{iid}:description:{_digest(desc)}", desc, author.get("name", ""), author.get("id"),
                       f"Redmine description of {where}", self.rm.issue_url(iid), ctx)
        for j in issue.get("journals", []):
            changed = j.get("updated_on") or j["created_on"]
            if _parse(changed) < since:
                continue
            user = j.get("user") or {}
            if user.get("id") in self.skip_authors:
                continue
            notes = (j.get("notes") or "").strip()
            if notes:
                yield Item(f"redmine:journal:{j['id']}:{_digest(notes)}", notes, user.get("name", ""), user.get("id"),
                           f"Redmine comment on {where}", f"{self.rm.issue_url(iid)}#note-{j['id']}", ctx)
            for d in j.get("details", []):
                if d.get("property") == "attr" and d.get("name") == "description" and (d.get("new_value") or "").strip():
                    new = added_lines(d.get("old_value") or "", d["new_value"])
                    if new:
                        yield Item(f"redmine:journal:{j['id']}:description:{_digest(new)}", new, user.get("name", ""),
                                   user.get("id"), f"Redmine description edit on {where} (lines added)",
                                   self.rm.issue_url(iid), ctx)
