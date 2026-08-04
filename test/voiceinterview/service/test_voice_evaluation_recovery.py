import asyncio

from common.models import AsyncTaskStatus
from modules.voiceinterview.service.evaluation_recovery_service import VoiceEvaluationRecoveryService


class _Db:
    async def commit(self):
        return None


class _Context:
    async def __aenter__(self):
        return _Db()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Factory:
    def __call__(self):
        return _Context()


class _Sessions:
    def __init__(self):
        self.updated = []

    async def list_stale_evaluations(self, db, status, before):
        del db, before
        return [1] if status == AsyncTaskStatus.PENDING else [2]

    async def update_fields(self, db, session_id, **values):
        del db
        self.updated.append((session_id, values))


class _Producer:
    def __init__(self):
        self.sent = []

    async def send_evaluate_task_async(self, session_id):
        self.sent.append(session_id)


def test_recovery_requeues_stale_pending_and_processing():
    sessions = _Sessions()
    producer = _Producer()
    service = VoiceEvaluationRecoveryService(_Factory(), sessions, producer)
    asyncio.run(service.recover_once())
    assert [item[0] for item in sessions.updated] == [1, 2]
    assert all(item[1]["evaluate_status"] == AsyncTaskStatus.PENDING for item in sessions.updated)
    assert producer.sent == [1, 2]
