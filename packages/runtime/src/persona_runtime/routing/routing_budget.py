"""Spec 23 per-persona budget enforcement (T8; D-23-7).

A **pure evaluator** — no state. The running per-session / per-day spend tally is
owned by the turn loop (caller state), mirroring D-25-X-t12-window-location ("the
window lives in the runtime turn loop, not the backend instance; one instance
serves many conversations; core stays stateless"). This module is given the caps
+ the spend-so-far and returns a decision; it never accumulates.

Three caps, each opt-in (``None`` = no cap):

* **Per-turn (HARD)** — :func:`enforce_turn_cap` drops candidates whose estimated
  per-turn cost exceeds the cap; if none fit it raises
  :class:`~persona.backends.errors.BudgetExceededError` (fail-loud, criterion 7).
* **Per-session (SOFT)** — :func:`effective_weights` re-weights scoring toward
  cost as session spend approaches the cap (graceful, criterion 8); it never
  fails the turn.
* **Per-day (SOFT cooldown)** — same graceful cost-bias ramp as per-session; an
  exceeded daily cap drives the weights fully to cost (cheapest capable model).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.backends.errors import BudgetExceededError

from persona_runtime.routing.scoring import ProfileWeights

if TYPE_CHECKING:
    from persona_runtime.routing.model_scorer import ModelScore

__all__ = ["effective_weights", "enforce_turn_cap"]

# Soft caps begin biasing toward cost at 80% of the cap and reach full cost-bias
# at 100% (and beyond). A graceful linear ramp, not a cliff.
_SOFT_THRESHOLD = 0.8

# The fully cost-biased target the soft ramp interpolates toward.
_COST_MAX = ProfileWeights(cost=1.0, quality=0.0, latency=0.0)


def _ramp(spent_cents: float, cap_cents: float | None) -> float:
    """Return a cost-bias blend factor in ``[0.0, 1.0]`` for one soft cap.

    ``0.0`` below 80% of the cap; ramps linearly to ``1.0`` at/above the cap.
    ``cap_cents`` of ``None`` (no cap) → ``0.0`` (no bias).
    """
    if cap_cents is None or cap_cents <= 0.0:
        return 0.0
    usage = spent_cents / cap_cents
    if usage <= _SOFT_THRESHOLD:
        return 0.0
    return min(1.0, (usage - _SOFT_THRESHOLD) / (1.0 - _SOFT_THRESHOLD))


def effective_weights(
    base: ProfileWeights,
    *,
    session_spent_cents: float = 0.0,
    max_cents_per_session: float | None = None,
    day_spent_cents: float = 0.0,
    max_cents_per_day: float | None = None,
) -> ProfileWeights:
    """Apply the soft per-session / per-day cost-bias ramps to ``base`` (D-23-7).

    The blend factor is the MAX of the per-session and per-day ramps (whichever
    is under more pressure dominates); the result linearly interpolates each axis
    from ``base`` toward the all-cost vector. Returns ``base`` unchanged when both
    caps are unset or below their soft thresholds (the common case).

    Pure + deterministic: a function of the inputs only (criterion 4).
    """
    blend = max(
        _ramp(session_spent_cents, max_cents_per_session),
        _ramp(day_spent_cents, max_cents_per_day),
    )
    if blend == 0.0:
        return base

    def lerp(a: float, b: float) -> float:
        return a + (b - a) * blend

    return ProfileWeights(
        cost=lerp(base.cost, _COST_MAX.cost),
        quality=lerp(base.quality, _COST_MAX.quality),
        latency=lerp(base.latency, _COST_MAX.latency),
    )


def enforce_turn_cap(
    scored: list[ModelScore],
    *,
    max_cents_per_turn: float | None,
    tier: str,
) -> list[ModelScore]:
    """Drop candidates over the per-turn HARD cap; fail loud if none fit (D-23-7).

    Args:
        scored: Capability-passing, scored candidates (best-first).
        max_cents_per_turn: The hard cap in cents, or ``None`` (no cap → no-op).
        tier: The tier name, for the error context.

    Returns:
        The subset of ``scored`` whose estimated per-turn cost is within the cap
        (order preserved). Returns ``scored`` unchanged when the cap is ``None``.

    Raises:
        BudgetExceededError: A cap is set and no candidate fits (criterion 7).
    """
    if max_cents_per_turn is None:
        return scored
    within = [s for s in scored if s.cost_cents <= max_cents_per_turn]
    if not within:
        cheapest = min((s.cost_cents for s in scored), default=0.0)
        raise BudgetExceededError(
            "no candidate model fits the per-turn budget cap",
            context={
                "tier": tier,
                "scope": "per_turn",
                "cap_cents": str(max_cents_per_turn),
                "cheapest_candidate_cents": str(cheapest),
            },
        )
    return within
