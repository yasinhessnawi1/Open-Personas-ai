"""Runtime test fixtures + shared-helper path setup.

The runtime test tree has NO ``__init__.py`` files (adding them collides
``tests.conftest`` / ``tests.unit`` with the core package's identically-named
test packages — ``ImportPathMismatchError``). Without packages, the shared
``_fakes`` helper at ``tests/_fakes.py`` is not importable from ``tests/unit/``
or ``tests/integration/`` via a dotted path. This conftest puts the ``tests/``
directory on ``sys.path`` so both can ``from _fakes import ...``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
