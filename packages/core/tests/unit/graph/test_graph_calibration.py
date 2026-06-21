"""Unit tests for the threshold sweep harness (Spec K0, D-K0-1/9)."""

from __future__ import annotations

from persona.graph.calibration import best_threshold, sweep_thresholds

# Labelled (score, is_same_entity) pairs: matches score high, non-matches low,
# with one near-spelling false-positive at 0.93 to make precision the deciding axis.
_LABELLED = [
    (0.98, True),
    (0.95, True),
    (0.93, False),  # near-spelling of a different entity — the precision trap
    (0.91, True),
    (0.84, False),
    (0.70, False),
    (0.55, False),
]
_GRID = [round(0.50 + 0.01 * i, 2) for i in range(46)]  # 0.50 .. 0.95


def test_sweep_returns_a_result_per_threshold() -> None:
    results = sweep_thresholds(_LABELLED, thresholds=_GRID)
    assert len(results) == len(_GRID)
    assert all(0.0 <= r.precision <= 1.0 and 0.0 <= r.recall <= 1.0 for r in results)


def test_high_threshold_trades_recall_for_precision() -> None:
    r94 = sweep_thresholds(_LABELLED, thresholds=[0.94])[0]
    # At 0.94 only the two 0.95/0.98 matches survive → precision 1.0, recall 2/3.
    assert r94.precision == 1.0
    assert r94.recall == 2 / 3


def test_f_beta_default_is_precision_biased() -> None:
    # F0.5 (default) must reward the precision-1.0 cut over a higher-recall but
    # lower-precision cut that admits the 0.93 false-positive.
    by_t = {r.threshold: r for r in sweep_thresholds(_LABELLED, thresholds=[0.92, 0.94])}
    assert by_t[0.94].f_beta > by_t[0.92].f_beta  # 0.92 admits the FP → lower F0.5


def test_best_threshold_picks_highest_f_beta() -> None:
    results = sweep_thresholds(_LABELLED, thresholds=_GRID)
    chosen = best_threshold(results)
    assert chosen.f_beta == max(r.f_beta for r in results)
    # Precision-safe operating point sits at/above the lone FP (0.93).
    assert chosen.threshold > 0.93


def test_beta_is_configurable() -> None:
    f1 = sweep_thresholds(_LABELLED, thresholds=[0.90], beta=1.0)[0]
    f05 = sweep_thresholds(_LABELLED, thresholds=[0.90], beta=0.5)[0]
    assert f1.beta == 1.0
    assert f05.beta == 0.5
    assert f1.f_beta != f05.f_beta
