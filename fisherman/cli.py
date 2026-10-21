"""Command line: fisherman <scan|run|eval|check> --config FILE"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import List, Optional

from . import __version__, config, runner
from .item import Item
from .sources.jsonl import read_items


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="fisherman", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_ in (("scan", "check new content once"), ("run", "check new content forever"),
                        ("eval", "score a labelled JSONL set"), ("check", "check text from stdin")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--config", required=True)
        p.add_argument("-v", "--verbose", action="store_true")
        if name == "run":
            p.add_argument("--interval", type=int, default=600, help="seconds between scans (default 600)")
        if name == "eval":
            p.add_argument("set", help="JSONL file with text, label, group (and optional source, author, context)")
            p.add_argument("--stages", help="comma-separated subset of quick,reason,claims")
            p.add_argument("--out", help="write per-item results here")
        if name == "check":
            p.add_argument("--author", default="")
            p.add_argument("--source", default="stdin")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose or args.command == "run" else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    cfg = config.load(args.config)

    if args.command == "scan":
        print(f"{runner.scan(cfg)} alerts")
    elif args.command == "run":
        runner.run_forever(cfg, args.interval)
    elif args.command == "eval":
        report = runner.evaluate(cfg, read_items(args.set), args.stages.split(",") if args.stages else None)
        if args.out:
            with open(args.out, "w") as f:
                json.dump(report["results"], f, indent=1)
        print(f"caught {report['caught']}/{report['attacks']} | false alarms {report['false_alarms']}/{report['benign']}")
        for group, g in sorted(report["groups"].items()):
            print(f"  {group}: flagged {g['flagged']}/{g['total']}")
    elif args.command == "check":
        item = Item("stdin", sys.stdin.read(), args.author, None, args.source)
        verdict = runner.build_pipeline(cfg).run(item)
        print(json.dumps({"alert": verdict.alert, "reasons": verdict.reasons, "scores": verdict.scores}, indent=1))
        return 1 if verdict.alert else 0
    return 0
