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
| records | `trusted_user_ids` (required), `review_note_pattern` (regex for comments an integration posted to record a trusted person's code review) |
| alerts | `project` (required; keep it private, with no agent members), `assigned_to_id`, `tracker_id`, `max_text_chars` (default 4000) |
| shared | `url` (required), `key_file` or `key_files` (several read keys, tried in turn), `timeout` |

## Accounts

Give Fisherman its own Redmine user: read-only in every watched project (view issues, private notes, wiki and wiki history), and allowed to add issues only in the alerts project. Keep its key on the detector machine.

## Development

From the repository root:

```bash
pip install -r requirements-lint.txt -e . -e plugins/fisherman-redmine
bin/lint
```
