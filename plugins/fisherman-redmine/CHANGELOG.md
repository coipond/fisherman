# fisherman-redmine Changelog

## 0.1.0 (Unreleased)
- **[Feature]** Redmine source: new or edited issue descriptions and comments, and the lines each wiki page version added (wiki first), with a checkpoint and per-page version tracking.
- **[Feature]** Redmine records: trusted users' descriptions and comments, plus integration-recorded reviews matched by `review_note_pattern`.
- **[Feature]** Redmine alerts: one issue per finding, content HTML-escaped inside `<pre>`.
- [Enhancement] Try several read keys in turn (`key_files`); reads no key may see return nothing instead of failing.
- [Maintenance] Extracted from the Fisherman core into its own package, registered through entry points.
