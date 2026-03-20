"""
该模块提供 interview Repository 测试所需的辅助工具。

- InMemorySqliteSessionFactory: 复用 resume 模块的 SQLite 内存数据库工厂
- build_interview_session: 构造测试用 InterviewSessionORM
- build_interview_answer: 构造测试用 InterviewAnswerORM
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
RESUME_REPO_TEST_ROOT = PROJECT_ROOT / "test" / "resume" / "repository"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(RESUME_REPO_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(RESUME_REPO_TEST_ROOT))

# 复用 resume 模块已有的 InMemorySqliteSessionFactory
from resume_repository_mocks import InMemorySqliteSessionFactory

from infrastructure.database.models import InterviewSessionORM, InterviewAnswerORM, ResumeORM, InterviewSessionStatus
from modules.interview.model.interview_entity import SessionStatus
from common.models import AsyncTaskStatus


def build_resume_orm(
    *,
    id: int = 1,
    fileHash: str = "test-resume-hash",
    originalFilename: str = "test.pdf",
    fileSize: int = 1024,
    contentType: str = "application/pdf",
    resumeText: str = "这是测试简历内容",
    analyzeStatus: AsyncTaskStatus = AsyncTaskStatus.COMPLETED,
) -> ResumeORM:
    """构造测试用 ResumeORM"""
    return ResumeORM(
        id=id,
        fileHash=fileHash,
        originalFilename=originalFilename,
        fileSize=fileSize,
        contentType=contentType,
        resumeText=resumeText,
        uploadedAt=datetime.now(),
        lastAccessedAt=datetime.now(),
        analyzeStatus=analyzeStatus,
    )


def build_interview_session_orm(
    *,
    id: int = 1,
    session_id: str = "test-session-123",
    resume_id: int = 1,
    total_questions: int = 5,
    current_question_index: int = 0,
    status: InterviewSessionStatus = InterviewSessionStatus.CREATED,
    questions_json: str = "[]",
    overall_score: int = 0,
    overall_feedback: str = "",
    strengths_json: str = "[]",
    improvements_json: str = "[]",
    reference_answers_json: str = "[]",
    evaluate_status: AsyncTaskStatus = AsyncTaskStatus.PENDING,
    evaluate_error: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> InterviewSessionORM:
    """构造测试用 InterviewSessionORM"""
    return InterviewSessionORM(
        id=id,
        session_id=session_id,
        resume_id=resume_id,
        total_questions=total_questions,
        current_question_index=current_question_index,
        status=status,
        questions_json=questions_json,
        overall_score=overall_score,
        overall_feedback=overall_feedback,
        strengths_json=strengths_json,
        improvements_json=improvements_json,
        reference_answers_json=reference_answers_json,
        evaluate_status=evaluate_status,
        evaluate_error=evaluate_error,
        created_at=created_at or datetime.now(),
    )


def build_interview_answer_orm(
    *,
    id: int = 1,
    session_pk_id: int = 1,
    question_index: int = 1,
    question: str = "问题内容",
    category: str = "技术",
    user_answer: Optional[str] = None,
    score: Optional[int] = None,
    feedback: Optional[str] = None,
    reference_answer: Optional[str] = None,
    key_points_json: Optional[str] = None,
) -> InterviewAnswerORM:
    """构造测试用 InterviewAnswerORM"""
    return InterviewAnswerORM(
        id=id,
        session_pk_id=session_pk_id,
        question_index=question_index,
        question=question,
        category=category,
        user_answer=user_answer,
        score=score,
        feedback=feedback,
        reference_answer=reference_answer,
        key_points_json=key_points_json,
        answered_at=datetime.now(),
    )
