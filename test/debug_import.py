import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "test" / "interview" / "service"

sys.path.insert(0, str(SRC_ROOT))
sys.path.insert(0, str(TEST_ROOT))

try:
    from modules.interview.service.interview_persistence_service import InterviewPersistenceService
    print("SUCCESS")
except Exception as e:
    print("FAILED TO IMPORT:")
    traceback.print_exc()
