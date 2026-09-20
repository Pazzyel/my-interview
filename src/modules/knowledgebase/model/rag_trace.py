from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RagRunMode(str, Enum):
    ONLINE = "online"
    EVALUATION = "evaluation"


class RagTraceStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    NO_RESULT = "no_result"
    FAILED = "failed"


class RagExecutionRequest(BaseModel):
    question: str
    knowledge_base_ids: list[int]
    session_id: int | None = None
    run_mode: RagRunMode = RagRunMode.ONLINE
    record_usage: bool = True
    trace_required: bool = False


class RagRetrievalHit(BaseModel):
    chunk_id: str
    content: str
    score: float | None = None
    rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagRetrievalAttempt(BaseModel):
    query: str
    top_k: int
    min_score: float
    hits: list[RagRetrievalHit] = Field(default_factory=list)
    latency_ms: float = 0


class RagModelCall(BaseModel):
    purpose: Literal["query_rewrite", "answer_generation"]
    provider: str | None = None
    model: str | None = None
    prompt_name: str
    prompt_hash: str | None = None
    token_usage: dict[str, int] | None = None
    latency_ms: float = 0
    error: str | None = None


class RagTrace(BaseModel):
    trace_id: str
    original_query: str
    knowledge_base_ids: list[int]
    session_id: int | None = None
    run_mode: RagRunMode
    rewritten_query: str | None = None
    candidate_queries: list[str] = Field(default_factory=list)
    retrieval_attempts: list[RagRetrievalAttempt] = Field(default_factory=list)
    selected_query: str | None = None
    selected_contexts: list[RagRetrievalHit] = Field(default_factory=list)
    model_calls: list[RagModelCall] = Field(default_factory=list)
    response: str = ""
    status: RagTraceStatus = RagTraceStatus.RUNNING
    pipeline_version: str = "rag-v2"
    started_at: datetime
    finished_at: datetime | None = None
    total_latency_ms: float | None = None
    error_stage: str | None = None
    error: str | None = None


class RagRunResult(BaseModel):
    answer: str
    trace: RagTrace


class RagExecutionEvent(BaseModel):
    type: Literal["answer_token", "completed", "failed"]
    data: Any

