import asyncio
import logging
from datetime import datetime
from typing import Protocol

from modules.knowledgebase.model.rag_trace import (
    RagModelCall,
    RagRetrievalAttempt,
    RagTrace,
    RagTraceStatus,
)
logger = logging.getLogger(__name__)


class TraceRepository(Protocol):
    async def create(self, trace: RagTrace) -> None: ...
    async def append_event(
        self,
        trace_id: str,
        event_type: str,
        node_name: str | None,
        payload: dict,
        occurred_at: datetime,
    ) -> None: ...
    async def finish(self, trace: RagTrace) -> None: ...


class RagTraceRecorder:
    def __init__(self, repository: TraceRepository | None = None) -> None:
        self.repository = repository
        self._traces: dict[str, RagTrace] = {}
        self._required: dict[str, bool] = {}
        self._persistence_disabled: set[str] = set()
        self._lock = asyncio.Lock()

    async def start(self, trace: RagTrace, required: bool) -> None:
        if required and self.repository is None:
            raise RuntimeError("Trace persistence is required but no repository is configured")
        async with self._lock:
            self._traces[trace.trace_id] = trace
            self._required[trace.trace_id] = required
        try:
            if self._should_persist(trace.trace_id):
                await self._persist(trace.trace_id, self.repository.create(trace))
            await self.event(trace.trace_id, "rag_started", "workflow", {})
        except Exception:
            await self.discard(trace.trace_id)
            raise

    async def event(
        self,
        trace_id: str,
        event_type: str,
        node_name: str | None,
        payload: dict,
    ) -> None:
        """在Trace触发时执行对应时机的保存"""
        occurred_at = datetime.now()
        async with self._lock:
            trace = self._traces[trace_id]
            if event_type == "query_rewritten":
                trace.rewritten_query = payload.get("rewritten_query")
                trace.candidate_queries = list(payload.get("candidate_queries", []))
                model_call = payload.get("model_call")
                if model_call:
                    trace.model_calls.append(RagModelCall.model_validate(model_call))
            elif event_type == "retrieval_completed":
                attempt = RagRetrievalAttempt.model_validate(payload)
                trace.retrieval_attempts.append(attempt)
            elif event_type == "context_selected":
                trace.selected_query = payload.get("selected_query")
                trace.selected_contexts = trace.retrieval_attempts[-1].hits if trace.retrieval_attempts else []
            elif event_type in {"generation_completed", "generation_failed", "query_rewrite_failed"}:
                model_call = payload.get("model_call")
                if model_call:
                    trace.model_calls.append(RagModelCall.model_validate(model_call))
                if event_type == "generation_completed":
                    trace.response = payload.get("response", "")
                elif event_type == "generation_failed":
                    trace.error_stage = "answer_generation"
                    trace.error = payload.get("error")
                elif event_type == "query_rewrite_failed":
                    trace.error_stage = trace.error_stage or "query_rewrite"
            elif event_type == "rag_failed":
                trace.error_stage = payload.get("stage")
                trace.error = payload.get("error")

        if self._should_persist(trace_id):
            await self._persist(
                trace_id,
                self.repository.append_event(trace_id, event_type, node_name, payload, occurred_at),
            )

    async def finish(
        self,
        trace_id: str,
        status: RagTraceStatus,
        response: str,
        error_stage: str | None = None,
        error: str | None = None,
    ) -> RagTrace:
        async with self._lock:
            trace = self._traces[trace_id]
            trace.status = status
            trace.response = response
            trace.error_stage = error_stage or trace.error_stage
            trace.error = error or trace.error
            trace.finished_at = datetime.now()
            trace.total_latency_ms = (trace.finished_at - trace.started_at).total_seconds() * 1000
        await self.event(trace_id, "rag_failed" if status == RagTraceStatus.FAILED else "rag_completed", "workflow", {
            "status": status.value,
            "response": response,
            "stage": trace.error_stage,
            "error": trace.error,
        })
        if self._should_persist(trace_id):
            await self._persist(trace_id, self.repository.finish(trace))
        return trace.model_copy(deep=True)

    async def discard(self, trace_id: str) -> None:
        async with self._lock:
            self._traces.pop(trace_id, None)
            self._required.pop(trace_id, None)
            self._persistence_disabled.discard(trace_id)

    def _should_persist(self, trace_id: str) -> bool:
        return self.repository is not None and trace_id not in self._persistence_disabled

    async def _persist(self, trace_id: str, awaitable) -> None:
        try:
            await awaitable
        except Exception:
            if self._required.get(trace_id, False):
                raise
            self._persistence_disabled.add(trace_id)
            logger.exception("RAG trace persistence failed: trace_id=%s", trace_id)
