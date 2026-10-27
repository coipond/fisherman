# fisherman-redmine

Redmine plug-ins for [Fisherman](../../README.md): a source, a records plug-in and an alerts plug-in.

## Install

The Fisherman image includes this plug-in. To install it elsewhere, from the repository root:

```bash
pip install . ./plugins/fisherman-redmine
```

Installing registers the `redmine` type for sources, records and alerts.

## Configure

See [`examples/config.redmine.json`](examples/config.redmine.json). Connection settings go once in a top-level `"redmine"` section and are shared by the three plug-ins.

| Plug-in | Settings |
|---|---|
| source | `projects` ("all" or identifiers), `exclude_projects` (always add the alerts project), `skip_author_ids` (trusted people and the detector's own account), `lookback_hours` (first scan, default 24), `overlap_minutes` (default 10) |
| records | `trusted_user_ids` (required); `review_note_pattern` (regex for comments that record a code review and name its pull request) together with `review_verification` (see below) |
| alerts | `project` (required; keep it private, with no agent members), `assigned_to_id`, `tracker_id`, `max_text_chars` (default 4000) |
| shared | `url` (required), `key_file` or `key_files` (several read keys, tried in turn), `timeout` |

## Reviews and merges are confirmed with GitHub

Comments that record a code review (for example `[github:review] Alice approved https://github.com/o/r/pull/9`, posted by a webhook pipeline) are written by whatever account runs that pipeline, often an agent. A compromised agent could post a fake approval and then cite it. So the text of such a comment is never trusted: it only points at pull requests (`github.com/<owner>/<repo>/pull/<n>` or `<owner>/<repo>#<n>`). For each one, the plug-in reads the reviews from the GitHub API and keeps those written by a trusted GitHub account, matched by numeric id, which survives renames. It also reads who merged the pull request, so a relayed "approved and merged" is confirmed only when a trusted account did both.

```json
"review_verification": {
  "trusted_github_ids": [1234567],
  "token_file": "/config/github.key"
}
```

Without `token_file` only public repositories can be read, and GitHub allows only 60 requests an hour, which a busy scan spends quickly. When the limit is spent, claims about reviews stay unverified until it resets; Fisherman logs a warning then, and at startup when `token_file` is missing. For private ones, use a fine-grained, read-only token with "Pull requests: read" on those repositories. A pull request the token cannot read has no confirmed reviews, so claims about it stay unverified and raise an alert. Look up an account's id with `gh api users/<login> --jq .id`.

## Accounts

Give Fisherman its own Redmine user: read-only in every watched project (view issues, private notes, wiki and wiki history), and allowed to add issues only in the alerts project. Keep its key on the detector machine.

## Development

From the repository root:

```bash
pip install -r requirements-lint.txt -e . -e plugins/fisherman-redmine
bin/lint
```
