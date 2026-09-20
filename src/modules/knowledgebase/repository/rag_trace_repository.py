import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.database.connection import async_session_factory
from infrastructure.database.models import RagTraceEventORM, RagTraceRunORM
from modules.knowledgebase.model.rag_trace import (
    RagModelCall,
    RagRetrievalAttempt,
    RagRunMode,
    RagTrace,
    RagTraceStatus,
)


class RagTraceRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.session_factory = session_factory or async_session_factory

    async def create(self, trace: RagTrace) -> None:
        async with self.session_factory() as db:
            db.add(RagTraceRunORM(
                trace_id=trace.trace_id,
                session_id=trace.session_id,
                run_mode=trace.run_mode.value,
                knowledge_base_ids_json=json.dumps(trace.knowledge_base_ids),
                original_query=trace.original_query,
                pipeline_version=trace.pipeline_version,
                status=trace.status.value,
                started_at=trace.started_at,
            ))
            await db.commit()

    async def append_event(
        self,
        trace_id: str,
        event_type: str,
        node_name: str | None,
        payload: dict,
        occurred_at: datetime,
    ) -> None:
        async with self.session_factory() as db:
            db.add(RagTraceEventORM(
                trace_id=trace_id,
                event_type=event_type,
                node_name=node_name,
                payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                occurred_at=occurred_at,
            ))
            await db.commit()

    async def finish(self, trace: RagTrace) -> None:
        async with self.session_factory() as db:
            row = await db.get(RagTraceRunORM, trace.trace_id)
            if row is None:
                raise RuntimeError(f"RAG trace does not exist: {trace.trace_id}")
            row.selected_query = trace.selected_query
            row.response = trace.response
            row.status = trace.status.value
            row.completed_at = trace.finished_at
            row.total_latency_ms = trace.total_latency_ms
            row.error_stage = trace.error_stage
            row.error_message = trace.error
            await db.commit()

    async def get(self, trace_id: str) -> RagTrace | None:
        async with self.session_factory() as db:
            row = await db.get(RagTraceRunORM, trace_id)
            if row is None:
                return None
            events = list((await db.scalars(
                select(RagTraceEventORM)
                .where(RagTraceEventORM.trace_id == trace_id)
                .order_by(RagTraceEventORM.id)
            )).all())

        trace = RagTrace(
            trace_id=row.trace_id,
            session_id=row.session_id,
            run_mode=RagRunMode(row.run_mode),
            original_query=row.original_query,
            knowledge_base_ids=json.loads(row.knowledge_base_ids_json),
            selected_query=row.selected_query,
            response=row.response or "",
            pipeline_version=row.pipeline_version,
            status=RagTraceStatus(row.status),
            started_at=row.started_at,
            finished_at=row.completed_at,
            total_latency_ms=row.total_latency_ms,
            error_stage=row.error_stage,
            error=row.error_message,
        )
        for event in events:
            payload = json.loads(event.payload_json)
            if event.event_type == "query_rewritten":
                trace.rewritten_query = payload.get("rewritten_query")
                trace.candidate_queries = list(payload.get("candidate_queries", []))
            if event.event_type == "retrieval_completed":
                trace.retrieval_attempts.append(RagRetrievalAttempt.model_validate(payload))
            if event.event_type == "context_selected":
                selected_ids = set(payload.get("chunk_ids", []))
                trace.selected_contexts = [
                    hit
                    for attempt in trace.retrieval_attempts
                    for hit in attempt.hits
                    if hit.chunk_id in selected_ids
                ]
            model_call = payload.get("model_call")
            if model_call:
                trace.model_calls.append(RagModelCall.model_validate(model_call))
        return trace
