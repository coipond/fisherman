"""Command line: `fisherman <scan|run|eval|check> --config FILE`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from fisherman import config
from fisherman.errors import BaseError
from fisherman.item import Item
from fisherman.pipeline import Pipeline
from fisherman.processing import Evaluator, Scanner
from fisherman.sources.jsonl import read_items
from fisherman.version import VERSION

#: Exit codes
EXIT_OK = 0
EXIT_ALERT = 1
EXIT_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; defaults to `sys.argv[1:]`.

    Returns:
        EXIT_OK, EXIT_ALERT (`check` found something) or EXIT_ERROR.

    """
    args = _parser().parse_args(argv)
    verbose = args.verbose or args.command == "run"
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        cfg = config.load(args.config)
        if args.command == "scan":
            _out(f"{Scanner(cfg).scan()} alerts")
        elif args.command == "run":
            Scanner(cfg).run_forever(args.interval)
        elif args.command == "eval":
            _evaluate(cfg, args)
        elif args.command == "check":
            return _check(cfg, args)
    except BaseError as e:
        logging.getLogger("fisherman").error("%s", e)  # noqa: TRY400 - a known failure, no traceback
        return EXIT_ERROR
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fisherman", description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {
        "scan": "check new content once",
        "run": "check new content forever",
        "eval": "score a labelled JSONL set",
        "check": "check text from stdin",
    }
    for name, help_text in commands.items():
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--config", required=True)
        command.add_argument("-v", "--verbose", action="store_true")
    sub.choices["run"].add_argument(
        "--interval", type=int, default=600, help="seconds between scans"
    )
    sub.choices["eval"].add_argument(
        "set", help="JSONL with text, label, group (optional: source, author, context)"
    )
    sub.choices["eval"].add_argument(
        "--steps", help="comma-separated subset of quick,reason,claims"
    )
    sub.choices["eval"].add_argument("--out", help="write per-item results here")
    sub.choices["check"].add_argument("--author", default="")
    sub.choices["check"].add_argument("--source", default="stdin")
    return parser


def _evaluate(cfg: dict[str, object], args: argparse.Namespace) -> None:
    steps = args.steps.split(",") if args.steps else None
    report = Evaluator(Pipeline.from_config(cfg, steps)).call(read_items(args.set))
    if args.out:
        Path(args.out).write_text(json.dumps(asdict(report)["results"], indent=1))
    summary = f"caught {report.caught}/{report.attacks}"
    _out(f"{summary} | false alarms {report.false_alarms}/{report.benign}")
    for group, counts in sorted(report.groups.items()):
        _out(f"  {group}: flagged {counts['flagged']}/{counts['total']}")


def _check(cfg: dict[str, object], args: argparse.Namespace) -> int:
    item = Item("stdin", sys.stdin.read(), args.author, None, args.source)
    verdict = Pipeline.from_config(cfg).run(item)
    _out(
        json.dumps(
            {"alert": verdict.alert, "reasons": verdict.reasons, "scores": verdict.scores}, indent=1
        )
    )
    return EXIT_ALERT if verdict.alert else EXIT_OK


def _out(text: str) -> None:
    print(text)  # noqa: T201 - command output
