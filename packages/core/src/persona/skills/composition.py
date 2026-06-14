"""Skill-composition state: depth cap, cycle detection, shared budget (D-24-4).

Spec 24 lets a skill's instructions trigger a further ``use_skill`` call
(research → draft → format). This module is the single, runtime-agnostic helper
both intercepts (conversation ``loop.py`` + ``agentic/loop.py``) use, so the
discipline is defined once (DRY) and the loops stay surgical.

Discipline (D-24-4 + D-24-X-budget-exhaustion-policy):

* **Depth cap = 3** (``MAX_SKILL_COMPOSITION_DEPTH``), enforced by refusing the
  4th activation — the model never even gets the over-cap skill injected.
* **Cycle detection** via a visited-set of skill names along the active chain
  (a push/pop stack within the turn/run); checked **before** the depth check so
  A→B→A is reported as a cycle, not a depth overflow.
* **Shared token budget** accumulated across the chain (not multiplied per
  step). The first skill goes through the existing per-skill injector
  (Spec 04). A *composed* skill (depth ≥ 1) is admitted only if its content
  fits the **remaining** budget; if it does not, the whole skill is skipped
  (never truncated) and ``budget_exceeded`` is set — the turn still proceeds.

The state object is created once per turn (conversation) or per run (agentic)
and consulted at each ``use_skill`` activation.
"""

from __future__ import annotations

from enum import Enum

from persona.errors import SkillCompositionDepthError, SkillCycleError

__all__ = [
    "MAX_SKILL_COMPOSITION_DEPTH",
    "AdmissionResult",
    "SkillCompositionState",
]

#: Maximum skills in one composition chain (D-24-4). Centrally defined so the
#: cap is tunable in one place even though it is fixed for v0.2.
MAX_SKILL_COMPOSITION_DEPTH = 3


class AdmissionResult(Enum):
    """Outcome of :meth:`SkillCompositionState.admit` that does not raise."""

    ADMITTED = "admitted"
    """The skill joined the chain and should be injected."""
    SKIPPED_BUDGET = "skipped_budget"
    """A composed skill did not fit the remaining shared budget; skip it whole."""


class SkillCompositionState:
    """Per-turn / per-run skill-composition chain + shared budget accumulator.

    Args:
        budget: The shared token budget for the whole chain (the per-turn skill
            content budget; the injector's 2000-token cap by default).
        max_depth: The depth cap (defaults to ``MAX_SKILL_COMPOSITION_DEPTH``).
    """

    def __init__(
        self,
        *,
        budget: int,
        max_depth: int = MAX_SKILL_COMPOSITION_DEPTH,
    ) -> None:
        self._budget = budget
        self._max_depth = max_depth
        self._chain: list[str] = []
        self._used = 0
        self.budget_exceeded = False

    @property
    def chain(self) -> tuple[str, ...]:
        """The skills admitted so far, in activation order."""
        return tuple(self._chain)

    @property
    def depth(self) -> int:
        """Current chain depth (number of admitted skills)."""
        return len(self._chain)

    def remaining(self) -> int:
        """Tokens left in the shared budget."""
        return max(0, self._budget - self._used)

    def admit(self, name: str, *, content_tokens: int) -> AdmissionResult:
        """Decide whether ``name`` may be activated now; record it if so.

        The first skill (empty chain) is always admitted — its own budget is
        enforced downstream by the per-skill injector (Spec 04). A composed
        skill is admitted only if ``content_tokens`` fits :meth:`remaining`;
        otherwise it is skipped whole and ``budget_exceeded`` is set.

        Args:
            name: The skill being activated.
            content_tokens: The token cost of the skill's content. For the
                first skill this is advisory (the injector budgets it); for a
                composed skill it gates admission against the remaining budget.

        Returns:
            :attr:`AdmissionResult.ADMITTED` (caller should inject + then call
            :meth:`record_injected`) or :attr:`AdmissionResult.SKIPPED_BUDGET`.

        Raises:
            SkillCycleError: ``name`` is already in the active chain.
            SkillCompositionDepthError: the chain is already at ``max_depth``.
        """
        # D-24-4 check order: cycle → depth → budget.
        if name in self._chain:
            raise SkillCycleError(
                "skill composition cycle",
                context={"requested": name, "chain": "→".join(self._chain)},
            )
        if len(self._chain) >= self._max_depth:
            raise SkillCompositionDepthError(
                "skill composition depth exceeded",
                context={
                    "requested": name,
                    "chain": "→".join(self._chain),
                    "max_depth": str(self._max_depth),
                },
            )
        if self._chain and content_tokens > self.remaining():
            # Composed skill that won't fit the remaining shared budget: skip
            # whole, never truncate (D-24-X-budget-exhaustion-policy).
            self.budget_exceeded = True
            return AdmissionResult.SKIPPED_BUDGET
        self._chain.append(name)
        return AdmissionResult.ADMITTED

    def record_injected(self, tokens: int) -> None:
        """Debit the shared budget by the tokens actually injected for the
        most recently admitted skill."""
        self._used += tokens
