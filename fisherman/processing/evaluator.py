"""Scores a labelled set: caught attacks and false alarms per group."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fisherman.item import Item, Verdict

if TYPE_CHECKING:
    from fisherman.pipeline import Pipeline

log = logging.getLogger("fisherman")


@dataclass
class Report:
    """Evaluation results.

    Attributes:
        caught: Attacks that alerted.
        attacks: Attacks in the set.
        false_alarms: Benign items that alerted.
        benign: Benign items in the set.
        groups: Per group: flagged and total.
        results: Per item: uid, group, label, alert, reasons, scores.

    """

    caught: int = 0
    attacks: int = 0
    false_alarms: int = 0
    benign: int = 0
    groups: dict[str, dict[str, int]] = field(default_factory=dict)
    results: list[dict[str, Any]] = field(default_factory=list)


class Evaluator:
    """Runs labelled items through a pipeline."""

    def __init__(self, pipeline: Pipeline) -> None:
        """Create an evaluator.

        Args:
            pipeline: The pipeline to evaluate.

        """
        self._pipeline = pipeline

    def call(self, items: list[Item]) -> Report:
        """Evaluate items.

        An item whose check fails counts as not flagged and is reported with an "error" reason.

        Args:
            items: Labelled items.

        Returns:
            The report.

        """
        report = Report()
        for n, item in enumerate(items, 1):
            try:
                verdict = self._pipeline.run(item)
            except Exception as e:
                log.exception("%s: check failed", item.uid)
                verdict = Verdict(alert=False, reasons=[f"error: {e}"], scores={"error": True})
            self._count(report, item, verdict)
            log.info(
                "%d/%d %s label=%s alert=%s", n, len(items), item.uid, item.label, verdict.alert
            )
        return report

    @staticmethod
    def _count(report: Report, item: Item, verdict: Verdict) -> None:
        group = report.groups.setdefault(
            item.group or ("attack" if item.label else "benign"), {"flagged": 0, "total": 0}
        )
        group["flagged"] += verdict.alert
        group["total"] += 1
        if item.label:
            report.attacks += 1
            report.caught += verdict.alert
        elif item.label is False:
            report.benign += 1
            report.false_alarms += verdict.alert
        report.results.append(
            {
                "uid": item.uid,
                "group": item.group,
                "label": item.label,
                "alert": verdict.alert,
                "reasons": verdict.reasons,
                "scores": verdict.scores,
            }
        )
