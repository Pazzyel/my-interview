"""
InterviewRepository 全方法 SQLite 内存数据库测试。

测试说明：
验证底层 SQL 查询逻辑：包括会话的增改、多表关联查询(Get Resume Text)、Upsert (有则更新，无则插入)。
涵盖所有 14 个数据库访问方法。
"""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = Path(__file__).resolve().parent

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from common.exceptions import BusinessException
from modules.interview.repository.interview_repository import InterviewRepository
from interview_repository_mocks import (
    InMemorySqliteSessionFactory,
    build_interview_session_orm,
    build_resume_orm,
    InterviewSessionStatus
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def sqlite_factory() -> InMemorySqliteSessionFactory:
    factory = InMemorySqliteSessionFactory()
    _run(factory.init())
    try:
        yield factory
    finally:
        _run(factory.dispose())


# 测试功能：create_session 测试插入的会话能够通过 find_by_session_id 查询到
def test_create_and_find_by_session_id(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            await repo.create_session(
                db=db,
                session_id="session-create-1",
                resume_id=101,
                total_questions=5,
                questions_json='[{"q":"1"}]',
            )
            await db.commit()

            session = await repo.find_by_session_id(db, "session-create-1")
            assert session is not None
            assert session.resumeId == 101
            assert session.totalQuestions == 5
            assert session.status.value == "CREATED"
            assert session.questionsJson == '[{"q":"1"}]'

    _run(_scenario())


# 测试功能：update_session_status 和 update_evaluate_status 可正确修改数据库记录
def test_update_status(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            # 准备基础数据
            await repo.create_session(db, "session-status-1", 1, 3, "[]")
            await db.commit()

            # 测试修改状态
            await repo.update_session_status(db, "session-status-1", "IN_PROGRESS")
            await repo.update_evaluate_status(db, "session-status-1", "PROCESSING", None)
            await db.commit()

            session = await repo.find_by_session_id(db, "session-status-1")
            assert session.status.value == "IN_PROGRESS"
            assert session.evaluateStatus == "PROCESSING"
            assert session.evaluateError is None

            # 测试失败转态带错误信息
            await repo.update_evaluate_status(db, "session-status-1", "FAILED", "Timeout")
            await db.commit()
            
            session = await repo.find_by_session_id(db, "session-status-1")
            assert session.evaluateStatus == "FAILED"
            assert session.evaluateError == "Timeout"

    _run(_scenario())


# 测试功能：update_session_progress 可以同时更新 index, status, questions_json
def test_update_session_progress(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            await repo.create_session(db, "session-prog-1", 1, 3, "[]")
            await db.commit()

            await repo.update_session_progress(
                db, "session-prog-1", 
                current_question_index=2, 
                status="COMPLETED", 
                questions_json='["q1", "q2"]'
            )
            await db.commit()

            session = await repo.find_by_session_id(db, "session-prog-1")
            assert session.currentQuestionIndex == 2
            assert session.status.value == "COMPLETED"
            assert session.questionsJson == '["q1", "q2"]'

    _run(_scenario())


# 测试功能：save_report 可以更新统计结果字段
def test_save_report(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            await repo.create_session(db, "session-report-1", 1, 3, "[]")
            await db.commit()

            await repo.save_report(
                db, "session-report-1",
                overall_score=85,
                overall_feedback="Good",
                strengths_json='["A"]',
                improvements_json='["B"]',
                reference_answers_json='["C"]'
            )
            await db.commit()

            session = await repo.find_by_session_id(db, "session-report-1")
            assert session.overallScore == 85
            assert session.overallFeedback == "Good"
            assert session.strengthsJson == '["A"]'
            assert session.improvementsJson == '["B"]'
            assert session.referenceAnswersJson == '["C"]'

    _run(_scenario())


# 测试功能：upsert_answer 应具备「不存在则插入」「存在则更新」防重控制
def test_upsert_answer(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            await repo.create_session(db, "session-upsert-1", 1, 3, "[]")
            await db.commit()

            # 1. 不存在则插入
            await repo.upsert_answer(
                db, "session-upsert-1", 1, 
                question="Q1", category="Tech", 
                user_answer=None, score=None, feedback=None, reference_answer=None, key_points_json=None
            )
            await db.commit()

            detail = await repo.find_detail_by_session_id(db, "session-upsert-1")
            assert len(detail.answers) == 1
            assert detail.answers[0].question == "Q1"
            assert detail.answers[0].userAnswer is None

            # 2. 存在则更新
            await repo.upsert_answer(
                db, "session-upsert-1", 1, 
                question="Q1", category="Tech", 
                user_answer="A1", score=100, feedback="Nice", reference_answer="RefA", key_points_json='["Key"]'
            )
            await db.commit()

            detail2 = await repo.find_detail_by_session_id(db, "session-upsert-1")
            assert len(detail2.answers) == 1
            assert detail2.answers[0].userAnswer == "A1"
            assert detail2.answers[0].score == 100

    _run(_scenario())


# 测试功能：对不存在的 session 调用 upsert_answer 报错
def test_upsert_answer_session_not_found(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            with pytest.raises(BusinessException, match="面试会话不存在"):
                await repo.upsert_answer(
                    db, "not_exist_session", 1, 
                    question="Q", category="Tech", 
                    user_answer="A", score=100, feedback=None, reference_answer=None, key_points_json=None
                )

    _run(_scenario())


# 测试功能：get_resume_text_by_session_id (测试关联查询 resumeORM)
def test_get_resume_text_by_session_id(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            # 准备外键依赖: Resume
            resume = build_resume_orm(id=200, resumeText="Hello Resume")
            db.add(resume)
            await db.flush()

            await repo.create_session(db, "session-resume-1", 200, 3, "[]")
            await db.commit()

            # 执行查询
            text = await repo.get_resume_text_by_session_id(db, "session-resume-1")
            assert text == "Hello Resume"

    _run(_scenario())


# 测试功能：list_historical_questions_by_resume_id 提取去重的前面会话的题目
def test_list_historical_questions(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            # 会话1问题
            q1 = '[{"question": "Q1", "isFollowUp": false}, {"question": "Q2", "isFollowUp": true}]'
            # 会话2问题 (包含与会话1重复的 Q1，和新主问题 Q3)
            q2 = '[{"question": "Q1", "isFollowUp": false}, {"question": "Q3", "isFollowUp": false}]'

            s1 = build_interview_session_orm(id=1, session_id="s1", resume_id=50, questions_json=q1, created_at=datetime.now())
            s2 = build_interview_session_orm(id=2, session_id="s2", resume_id=50, questions_json=q2, created_at=datetime.now() + timedelta(seconds=1))
            
            db.add_all([s1, s2])
            await db.commit()

            questions = await repo.list_historical_questions_by_resume_id(db, 50)
            
            # 因为 s2 是最新(倒序排序)，所以先处理 s2，再处理 s1
            # s2 包含: Q1, Q3 (均非 FollowUp)
            # s1 包含: Q1(遇到过忽略), Q2 (FollowUp 忽略)
            assert questions == ["Q1", "Q3"]

    _run(_scenario())


# 测试功能：find_unfinished_by_resume_id 和 list_history_by_resume_id
def test_find_by_resume_id_queries(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            s1 = build_interview_session_orm(id=10, session_id="sess-fin", resume_id=60, status=InterviewSessionStatus.COMPLETED, created_at=datetime(2026,1,1))
            s2 = build_interview_session_orm(id=11, session_id="sess-prog", resume_id=60, status=InterviewSessionStatus.IN_PROGRESS, created_at=datetime(2026,1,2))
            
            db.add_all([s1, s2])
            await db.commit()

            # 未完成的会话，且应当取最新的一条（按创建时间倒序）
            unfinished = await repo.find_unfinished_by_resume_id(db, 60)
            assert unfinished is not None
            assert unfinished.sessionId == "sess-prog"

            # 历史会话数量应该有两个
            history = await repo.list_history_by_resume_id(db, 60)
            assert len(history) == 2
            assert history[0].sessionId == "sess-prog" # 最新在前面
            assert history[1].sessionId == "sess-fin"

            # 会话数量等于2
            count = await repo.count_by_resume_id(db, 60)
            assert count == 2

    _run(_scenario())


# 测试功能：delete_by_session_id 和 delete_by_resume_id
def test_deletions(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            s1 = build_interview_session_orm(id=20, session_id="sess-del-1", resume_id=70)
            s2 = build_interview_session_orm(id=21, session_id="sess-del-2", resume_id=70)
            db.add_all([s1, s2])
            await db.commit()

            await repo.delete_by_session_id(db, "sess-del-1")
            await db.commit()
            
            assert await repo.find_by_session_id(db, "sess-del-1") is None
            assert await repo.find_by_session_id(db, "sess-del-2") is not None

            await repo.delete_by_resume_id(db, 70)
            await db.commit()
            assert await repo.find_by_session_id(db, "sess-del-2") is None

    _run(_scenario())


# 测试功能：find_detail_by_session_id 可正确融合 questions_json 与 answers表数据
def test_find_detail_by_session_id(sqlite_factory: InMemorySqliteSessionFactory) -> None:
    repo = InterviewRepository()

    async def _scenario() -> None:
        async with sqlite_factory.session() as db:
            await repo.create_session(
                db, "sess-detail-1", 80, 2, 
                questions_json='[{"questionIndex": 1, "question": "Q1"}, {"questionIndex": 2, "question": "Q2"}]'
            )
            await db.commit()

            # 插入对 第一题 的回答
            await repo.upsert_answer(
                db, "sess-detail-1", 1, 
                question="Q1", category="T", user_answer="A1", score=100, feedback="OK", reference_answer=None, key_points_json=None
            )
            await db.commit()

            detail = await repo.find_detail_by_session_id(db, "sess-detail-1")
            
            assert detail is not None
            assert detail.sessionId == "sess-detail-1"
            assert len(detail.answers) == 2  

            # Q1 回答有了数据库记录，分数 100
            assert detail.answers[0].questionIndex == 1
            assert detail.answers[0].score == 100

            # Q2 回答只有题目的空壳（尚未回答），分数为 0
            assert detail.answers[1].questionIndex == 2
            assert detail.answers[1].score == 0

    _run(_scenario())
