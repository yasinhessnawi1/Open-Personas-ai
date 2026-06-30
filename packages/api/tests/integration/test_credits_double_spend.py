"""Adversarial concurrency test for the credits decrement (Spec R2, T2 / F-04).

The audit's F-04: the decrement was atomic *as a write* but had no balance
floor (``deduct`` did ``UPDATE … SET balance = balance - :amount`` with no
``WHERE balance >= :amount``), and the pre-flight ``require_credits`` gate ran
in a *separate* transaction. Two concurrent turns could each pass the pre-flight
at balance=1, then both deduct → balance goes negative (double-spend).

R2-D-3 fixes this with a **conditional atomic decrement**
(``UPDATE … WHERE balance >= :amount RETURNING``) so a decrement that would
overdraw is rejected (raises :class:`CreditsExhaustedError`, writes no ledger
row), plus a DB-level ``CHECK (balance >= 0)`` constraint as the durable guard.

This test demonstrates the race: N threads each try to deduct from a balance
that only covers some of them. Pre-fix, every thread "succeeds" and the balance
goes negative with N ledger rows (double-spend). Post-fix, exactly
``balance // amount`` deducts succeed, the rest raise ``CreditsExhaustedError``,
the balance floors at >= 0, and only the successful deducts wrote ledger rows.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from persona.errors import CreditsExhaustedError
from persona_api.db.models import credit_transactions as credit_tx_t
from persona_api.db.models import credits as credits_t
from persona_api.services import credits_service
from sqlalchemy import func, select, text

if TYPE_CHECKING:
    from sqlalchemy import Engine

pytestmark = pytest.mark.integration


_USER = "u_double_spend"


@pytest.fixture
def seeded_engine(pg_engine: Engine) -> Engine:
    """Insert the FK target user row so credits writes satisfy the constraint."""
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:i, :e) ON CONFLICT DO NOTHING"),
            {"i": _USER, "e": f"{_USER}@x.test"},
        )
    return pg_engine


def _set_balance(engine: Engine, user_id: str, balance: int) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    with engine.begin() as conn:
        conn.execute(
            pg_insert(credits_t)
            .values(user_id=user_id, balance=balance)
            .on_conflict_do_update(index_elements=[credits_t.c.user_id], set_={"balance": balance})
        )


def _balance(engine: Engine, user_id: str) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            select(credits_t.c.balance).where(credits_t.c.user_id == user_id)
        ).first()
    assert row is not None
    return int(row[0])


def _ledger_count(engine: Engine, user_id: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                select(func.count())
                .select_from(credit_tx_t)
                .where(credit_tx_t.c.user_id == user_id)
            ).scalar_one()
        )


def test_concurrent_decrements_cannot_double_spend(seeded_engine: Engine) -> None:
    """The headline adversarial case: 8 threads, balance only covers 5 → exactly
    5 succeed, 3 are rejected, balance floors at >= 0, ledger == successes."""
    engine = seeded_engine
    n_threads = 8
    affordable = 5
    _set_balance(engine, _USER, affordable)

    def _attempt(_: int) -> bool:
        try:
            credits_service.deduct(
                rls_engine=engine, user_id=_USER, amount=1, reason="double_spend_probe"
            )
        except CreditsExhaustedError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        results = list(pool.map(_attempt, range(n_threads)))

    successes = sum(results)
    assert successes == affordable, f"expected exactly {affordable} successes, got {successes}"
    assert _balance(engine, _USER) == 0, "balance must floor at 0, never negative"
    assert _balance(engine, _USER) >= 0
    assert _ledger_count(engine, _USER) == affordable, "only successful deducts write a ledger row"


def test_single_deduct_at_insufficient_balance_raises_and_writes_no_ledger_row(
    seeded_engine: Engine,
) -> None:
    """CQS: a rejected decrement records nothing (no ledger row, balance unchanged)."""
    engine = seeded_engine
    _set_balance(engine, _USER, 2)
    before = _ledger_count(engine, _USER)

    with pytest.raises(CreditsExhaustedError):
        credits_service.deduct(rls_engine=engine, user_id=_USER, amount=5, reason="overdraw")

    assert _balance(engine, _USER) == 2, "an insufficient deduct must not change the balance"
    assert _ledger_count(engine, _USER) == before, "an insufficient deduct writes no ledger row"


def test_check_constraint_blocks_a_negative_balance(seeded_engine: Engine) -> None:
    """Defense-in-depth: even a direct UPDATE cannot drive the balance negative
    (the CHECK (balance >= 0) constraint, the durable DB-level guard)."""
    from sqlalchemy.exc import IntegrityError

    engine = seeded_engine
    _set_balance(engine, _USER, 1)
    with pytest.raises(IntegrityError), engine.begin() as conn:  # noqa: PT012
        conn.execute(credits_t.update().where(credits_t.c.user_id == _USER).values(balance=-1))
