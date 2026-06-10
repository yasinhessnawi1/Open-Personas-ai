"""External-only tests for persona-core (Spec 20 T22).

``@pytest.mark.external`` — skipped by default per the workspace pyproject's
``addopts = "-v --tb=short -m 'not integration and not external'"``. Run
manually with::

    uv run pytest -m external [-k <selector>]

These tests call real third-party APIs (NVIDIA Build Catalog) so they are
paid (or rate-limit-gated on the trial tier) and non-deterministic. They
are intentionally outside CI per CSA-3 🟦 operator-pass disposition.
"""
