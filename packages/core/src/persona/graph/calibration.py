"""Threshold sweep harness for entity-resolution / merge tuning (Spec K0, D-K0-1/9).

The thresholds (alias-merge, merge-extend, semantic-link) can only be truly tuned
against real accumulation, so they ship config-driven and are flagged for a
post-launch re-tune. This is the tool that re-derives the operating point: given
labelled ``(score, is_match)`` pairs, sweep candidate thresholds and report
precision / recall / F-beta so the operator picks the point.

**F0.5 by default** (``beta=0.5``) — precision weighted 2× recall — because a
wrong merge is catastrophic and transitive while a too-shy split is recoverable
(research §2.4). Pure compute, no I/O; reusable from a notebook or a test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["ThresholdResult", "best_threshold", "sweep_thresholds"]


class ThresholdResult(BaseModel):
    """Precision/recall/F-beta for "merge iff score >= threshold" at one threshold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float
    precision: float
    recall: float
    f_beta: float
    beta: float


def _f_beta(precision: float, recall: float, beta: float) -> float:
    if precision == 0.0 and recall == 0.0:
        return 0.0
    b2 = beta * beta
    denom = b2 * precision + recall
    if denom == 0.0:
        return 0.0
    return (1.0 + b2) * precision * recall / denom


def sweep_thresholds(
    scored_labels: Sequence[tuple[float, bool]],
    *,
    thresholds: Sequence[float],
    beta: float = 0.5,
) -> list[ThresholdResult]:
    """Sweep ``thresholds``, computing P/R/F-beta for a merge-iff-``score>=t`` rule.

    Args:
        scored_labels: ``(resolution_score, is_truly_same_entity)`` pairs.
        thresholds: candidate cut points (e.g. ``[0.50, 0.51, …, 0.95]``).
        beta: F-beta weight; ``0.5`` (default) favours precision 2:1 (D-K0-9).

    Returns:
        One :class:`ThresholdResult` per threshold, in input order.
    """
    positives = sum(1 for _, is_match in scored_labels if is_match)
    results: list[ThresholdResult] = []
    for t in thresholds:
        tp = sum(1 for score, is_match in scored_labels if score >= t and is_match)
        predicted = sum(1 for score, _ in scored_labels if score >= t)
        precision = tp / predicted if predicted else 0.0
        recall = tp / positives if positives else 0.0
        results.append(
            ThresholdResult(
                threshold=t,
                precision=precision,
                recall=recall,
                f_beta=_f_beta(precision, recall, beta),
                beta=beta,
            )
        )
    return results


def best_threshold(results: Sequence[ThresholdResult]) -> ThresholdResult:
    """The result with the highest F-beta (ties → the higher threshold, precision-safe)."""
    if not results:
        msg = "no threshold results to choose from"
        raise ValueError(msg)
    return max(results, key=lambda r: (r.f_beta, r.threshold))
