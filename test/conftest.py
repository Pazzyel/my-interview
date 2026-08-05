"""Shared pytest import paths for the complete test suite."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SHARED_ROOT = Path(__file__).resolve().parent / "shared"

for path in (SRC_ROOT, SHARED_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
