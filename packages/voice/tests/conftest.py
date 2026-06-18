"""Shared fixtures for the persona-voice test suite.

Spec 33: the voice service is edition-selected — ``community`` (the product
default) is no-auth/no-credits, ``cloud`` is the Clerk-JWT + ownership + credits
behavior the existing suite asserts. Default every test to the cloud edition so
the pre-Spec-33 token-endpoint tests exercise the cloud behavior unchanged;
community-specific tests pass ``edition="cloud"``/``"community"`` explicitly (an
explicit ``VoiceConfig`` kwarg wins over the env var).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _default_cloud_edition() -> Iterator[None]:
    prior = os.environ.get("PERSONA_EDITION")
    os.environ["PERSONA_EDITION"] = "cloud"
    yield
    if prior is None:
        os.environ.pop("PERSONA_EDITION", None)
    else:
        os.environ["PERSONA_EDITION"] = prior
