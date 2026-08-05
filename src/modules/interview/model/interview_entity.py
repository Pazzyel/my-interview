from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from common.models import AsyncTaskStatus


class SessionStatus(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    EVALUATED = "EVALUATED"


class InterviewAnswerEntity(BaseModel):
    id: int | None = None
    session_pk_id: int
    questionIndex: int
    question: str | None = None
    category: str | None = None
    userAnswer: str | None = None
    score: int | None = None
    feedback: str | None = None
    referenceAnswer: str | None = None
    keyPointsJson: str | None = None
    answeredAt: datetime = Field(default_factory=datetime.now)


class InterviewSessionEntity(BaseModel):
    id: int | None = None
    sessionId: str
    requestId: str | None = None
    resumeId: int | None = None
    skillId: str = "java-backend"
    difficulty: str = "mid"
    llmProvider: str = "default"
    totalQuestions: int
    currentQuestionIndex: int = 0
    status: SessionStatus = SessionStatus.CREATED
    questionsJson: str | None = None
    overallScore: int | None = None
    overallFeedback: str | None = None
    strengthsJson: str | None = None
    improvementsJson: str | None = None
    referenceAnswersJson: str | None = None
    createdAt: datetime = Field(default_factory=datetime.now)
    completedAt: datetime | None = None
    evaluateStatus: AsyncTaskStatus = AsyncTaskStatus.PENDING
    evaluateError: str | None = None
    sourceType: str = "NORMAL"
    knowledgeBaseId: int | None = None
    interviewCategory: str | None = None
