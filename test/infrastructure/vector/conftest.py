import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
TEST_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))
