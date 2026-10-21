# Contributing

Thank you for considering a contribution. Bug reports, detection bypasses (please report those privately, see [SECURITY.md](SECURITY.md)), documentation and code are all welcome.

## Submitting code

Any change should come as a pull request against `master`. Describe what it does and how to try it, and include tests.

Every pull request must pass:

- `ruff check` with all rules and `ruff format --check`,
- `mypy` in strict mode,
- `pydoclint`: every public class, function and argument documented, docstrings matching signatures,
- the specs on Python 3.9 to 3.14, with at least 95% branch coverage.

Run all of it locally with:

```bash
pip install -r requirements-lint.txt
bin/lint
```

## Conventions

- Standard library only at runtime. Development tools are pinned in `requirements-lint.txt`.
- One class per file, in a namespace that says what it is for. Specs mirror the package layout under `tests/`.
- Errors raised on purpose inherit from `fisherman.errors.BaseError`.
- Configuration is checked by contracts before anything runs; a new setting comes with a contract rule.
- Add a line to `CHANGELOG.md` under the unreleased version, tagged `[Feature]`, `[Enhancement]`, `[Maintenance]` or `[Fix]`.
- Never commit tuned prompts, real workspace content or keys.

## Writing a plug-in

A plug-in is a class built with its configuration section as the only argument; see the interfaces in `fisherman/plugins.py`. Publish it in your own package under the `fisherman.sources`, `fisherman.records` or `fisherman.alerts` entry point group, or refer to it as `package.module:Class` in the configuration.
