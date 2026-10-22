# fisherman-redmine Changelog

## 0.2.0 (Unreleased)
- **[Feature]** Confirm recorded code reviews with GitHub: comments matching `review_note_pattern` are only pointers to pull requests, and the reviews are read from the GitHub API and kept only when a trusted GitHub account (`review_verification.trusted_github_ids`) wrote them. A forged "approved" comment adds nothing to the record.
- [Enhancement] `review_note_pattern` now requires `review_verification`; the configuration check says so.

## 0.1.0
- **[Feature]** Redmine source: new or edited issue descriptions and comments, and the lines each wiki page version added (wiki first), with a checkpoint and per-page version tracking.
- **[Feature]** Redmine records: trusted users' descriptions and comments, plus integration-recorded reviews matched by `review_note_pattern`.
- **[Feature]** Redmine alerts: one issue per finding, content HTML-escaped inside `<pre>`.
- [Enhancement] Try several read keys in turn (`key_files`); reads no key may see return nothing instead of failing.
- [Maintenance] Extracted from the Fisherman core into its own package, registered through entry points.
