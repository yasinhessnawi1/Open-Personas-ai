"""Default-lane durable guard for the credits balance floor (Spec R2, T2 / F-04).

The adversarial proof of the double-spend fix lives in the integration lane
(``test_credits_double_spend.py``, real Postgres concurrency). This file is the
**always-on** guard: cheap, no-DB assertions that the two structural pieces of
the fix cannot silently regress out —

  1. the canonical ``credits`` model declares ``CHECK (balance >= 0)`` (the
     durable DB-level floor, migration 024 / R2-D-3);
  2. the ``deduct`` decrement is **conditional** — its compiled UPDATE carries a
     ``balance >= :amount`` predicate, so an overdraw matches no row and is
     rejected rather than driving the balance negative.

If either is removed, this test fails in the default lane (no DB required).
"""

from __future__ import annotations

from persona_api.db.models import credits as credits_t
from sqlalchemy import CheckConstraint
from sqlalchemy.schema import CreateTable


def test_credits_model_declares_a_nonnegative_balance_check() -> None:
    """The named ``balance >= 0`` CHECK is on the canonical credits table, so a
    fresh-DB ``create_all`` builds it (split-home with migration 024)."""
    checks = [c for c in credits_t.constraints if isinstance(c, CheckConstraint)]
    names = {c.name for c in checks}
    assert "credits_balance_nonneg_check" in names, (
        "the credits table lost its balance>=0 CHECK constraint (F-04 durable guard)"
    )
    # The compiled DDL must mention the floor predicate.
    ddl = str(CreateTable(credits_t).compile()).lower()
    assert "balance >= 0" in ddl.replace("(", " ").replace(")", " ")


def test_deduct_uses_a_conditional_decrement() -> None:
    """The ``deduct`` path must gate the UPDATE on ``balance >= :amount`` (the
    atomic floor that closes the double-spend race). Asserted at the source level
    so the predicate cannot be dropped without this failing in the default lane."""
    import inspect

    from persona.credits import service

    src = inspect.getsource(service.deduct)
    # The conditional predicate (``_credits_t.c.balance >= amount``) + the
    # None-branch raise are the load-bearing lines of the R2-D-3 fix.
    assert "balance >= amount" in src.replace("_credits_t.c.", ""), (
        "deduct must carry a `balance >= amount` WHERE predicate (the atomic floor)"
    )
    assert "scalar_one_or_none" in src, (
        "deduct must use scalar_one_or_none so an overdraw (no row) is detected"
    )
    assert "CreditsExhaustedError" in src, "an overdraw must raise CreditsExhaustedError"
