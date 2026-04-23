"""Pytest configuration for local test execution.

Allows running tests from either project root or the tests folder by ensuring
the src package directory is importable.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
