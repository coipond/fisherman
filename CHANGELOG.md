# Fisherman Changelog

## 0.2.0 (Unreleased)
- **[Feature]** Resolve plug-ins by built-in name, by `fisherman.sources` / `fisherman.records` / `fisherman.alerts` entry points, or by a `package.module:Class` path, so integrations can live outside this repository.
- **[Feature]** Validate the whole configuration before anything runs and report every problem with its key path (for example `sources[0].url: is missing`). Each plug-in declares a `CONTRACT` for its own section.
- [Enhancement] Move Redmine out of the core into its own package, `fisherman-redmine` (`plugins/fisherman-redmine`), registered through entry points. The core has no Redmine code or names; install both packages to use it.
- [Enhancement] Let plug-ins of one type share connection settings through a top-level section named after the type (for example `"redmine": {"url": ..., "key_file": ...}`).
- [Enhancement] Exit with code 2 and a one-line error on configuration, model or Redmine failures instead of a traceback.
- [Enhancement] Raise `ModelUnavailableError` before reading any source when the model server is down, so no item is skipped.
- [Maintenance] Rename the `pipeline.stages` setting to `pipeline.steps` and the `eval --stages` option to `--steps`.
- [Maintenance] Split the pipeline into one class per step (`QuickCheck`, `ReasonCheck`, `ClaimCheck`) and the runner into `Scanner`, `Evaluator`, `State` and `chunks`.
- [Maintenance] Add `fisherman.errors` with one documented error class per failure, all under `BaseError`.
- [Maintenance] Lint with Ruff (all rules), mypy (strict) and pydoclint (docstrings must match signatures); pin the tools in `requirements-lint.txt`; add `bin/lint`.
- [Maintenance] Mirror the package layout in `tests/` and require 95% branch coverage (currently 99%).
- [Maintenance] Pin GitHub Actions by commit SHA, verify the pins and run actionlint on workflow changes; run CI nightly and on Python 3.9 to 3.14; add Renovate with a 7-day release age.

## 0.1.0 (2026-10-21)
- **[Feature]** Three-step detection pipeline on one local llama.cpp server: windowed quick check, reasoning check, and claim check (authority claims verified against the trusted users' own record, sends checked against an allowlist).
- **[Feature]** Redmine source (new or edited descriptions, comments, and wiki lines added per version), Redmine records and Redmine alerts.
- **[Feature]** JSON Lines source, and JSON Lines and stdout alerts.
- **[Feature]** `scan`, `run`, `eval` and `check` commands.
- [Enhancement] Load tuned prompts from a private directory; ship generic built-in prompts.
- [Enhancement] Try several Redmine read keys in turn (`key_files`).
- [Fix] Keep scanning when Redmine forbids a read or one item fails; failed items are retried on the next scan.
- [Fix] Do not alert on a cut-off claim extraction; give the extraction 1,000 tokens.
