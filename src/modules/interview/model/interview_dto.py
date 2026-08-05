from datetime import datetime
from typing import Any

from pydantic import BaseModel

from common.models import AsyncTaskStatus


class InterviewAnswerDetailDTO(BaseModel):
    questionIndex: int
    question: str | None = None
    category: str | None = None
    userAnswer: str | None = None
    score: int | None = None
    feedback: str | None = None
    referenceAnswer: str | None = None
    keyPoints: list[str] | None = None
    answeredAt: datetime | None = None


class InterviewDetailDTO(BaseModel):
    id: int
    sessionId: str
    resumeId: int | None = None
    skillId: str = "java-backend"
    difficulty: str = "mid"
    llmProvider: str = "default"
    totalQuestions: int
    status: str
    evaluateStatus: AsyncTaskStatus | None = None
    evaluateError: str | None = None
    overallScore: int | None = None
    sourceType: str | None = None
    knowledgeBaseId: int | None = None
    interviewCategory: str | None = None
    overallFeedback: str | None = None
    createdAt: datetime
    completedAt: datetime | None = None
    questions: list[Any]
    strengths: list[str]
    improvements: list[str]
    referenceAnswers: list[Any]
    answers: list[InterviewAnswerDetailDTO]


class InterviewHistoryItemDTO(BaseModel):
    sessionId: str
    resumeId: int | None = None
    skillId: str = "java-backend"
    difficulty: str = "mid"
    llmProvider: str = "default"
    status: str
    overallScore: int | None = None
    sourceType: str | None = None
    knowledgeBaseId: int | None = None
    interviewCategory: str | None = None
    createdAt: datetime
    completedAt: datetime | None = None
