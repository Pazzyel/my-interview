import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, AsyncIterator, Annotated

import regex
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import app_config
from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from infrastructure.database.connection import async_session_factory
from infrastructure.prompt.prompt_service import Role, get_prompt_hash, has_short_memory, load_prompt
from infrastructure.vector.scored_document import ScoredDocument
from modules.knowledgebase.model.query_request import QueryRequest
from modules.knowledgebase.model.query_response import QueryResponse
from modules.knowledgebase.model.rag_trace import (
    RagExecutionEvent,
    RagExecutionRequest,
    RagModelCall,
    RagRetrievalAttempt,
    RagRetrievalHit,
    RagRunResult,
    RagTrace,
    RagTraceStatus,
)
from modules.knowledgebase.service.knowledgebase_count_service import KnowledgeBaseCountService
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.knowledgebase.service.rag_trace_recorder import RagTraceRecorder


logger = logging.getLogger(__name__)
SHORT_TOKEN_PATTERN = r"^[\p{L}\p{N}_-]{2,20}$"
NO_RESULT_RESPONSE = "抱歉，在选定的知识库中未检索到相关信息。请换一个更具体的关键词或补充上下文后再试。"
SERVER_ERROR_RESPONSE = "抱歉，AI知识库问答服务暂时不可用。请您稍后再试。"


def collect_response_text(value: Any) -> list[str]:
    response_texts: list[str] = []
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key == "response" and isinstance(nested_value, str):
                response_texts.append(nested_value)
            else:
                response_texts.extend(collect_response_text(nested_value))
    elif isinstance(value, (list, tuple)):
        for nested_value in value:
            response_texts.extend(collect_response_text(nested_value))
    return response_texts


class KnowledgeQueryState(BaseModel):
    trace_id: str
    origin_query: str
    knowledgebase_ids: list[int]
    record_usage: bool = True
    candidate_queries: list[str] = Field(default_factory=list)
    selected_query: str | None = None
    search_params: dict[str, Any] = Field(default_factory=dict)
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)
    query_documents: list[Document] = Field(default_factory=list)
    response: str = ""
    status: str = RagTraceStatus.RUNNING.value
    error_stage: str | None = None
    error: str | None = None


def trim_question(question: str | None) -> str:
    return "" if question is None else question.strip()


def has_effective_hit(query: str, docs: list[Document]) -> bool:
    if not docs:
        return False
    if not regex.match(SHORT_TOKEN_PATTERN, trim_question(query)):
        return True
    return True


def check_answer(answer: str | None) -> str:
    return NO_RESULT_RESPONSE if not answer else answer.strip()


def _model_name(model: Any) -> str | None:
    return getattr(model, "model_name", None) or getattr(model, "model", None)


def _token_usage(message: Any) -> dict[str, int] | None:
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    values = {
        str(key): int(value)
        for key, value in usage.items()
        if isinstance(value, (int, float))
    }
    return values or None


class KnowledgeBaseQueryService:
    def __init__(
        self,
        knowledgebase_list_service: KnowledgeBaseListService,
        knowledgebase_vector_service: KnowledgeBaseVectorService,
        knowledgebase_count_service: KnowledgeBaseCountService,
        llm_provider_resolver: LlmProviderResolver | None = None,
        trace_recorder: RagTraceRecorder | None = None,
    ) -> None:
        self.app: CompiledStateGraph | Any | None = None
        self.session_app: CompiledStateGraph | None = None
        self.knowledgebase_list_service = knowledgebase_list_service
        self.knowledgebase_vector_service = knowledgebase_vector_service
        self.knowledgebase_count_service = knowledgebase_count_service
        self.llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self.trace_recorder = trace_recorder or RagTraceRecorder()
        self._chat_model = None

    async def build_graph(self, checkpointer: Checkpointer | None) -> None:
        self.app = await self.build_workflow(None)
        self.session_app = await self.build_workflow(checkpointer)

    async def execute(self, request: RagExecutionRequest) -> RagRunResult:
        completed: RagRunResult | None = None
        async for event in self.execute_stream(request):
            if event.type == "completed":
                completed = event.data
        if completed is None:
            raise RuntimeError("RAG execution ended without a result")
        return completed

    async def execute_stream(self, request: RagExecutionRequest) -> AsyncIterator[RagExecutionEvent]:
        graph = self.session_app if request.session_id is not None else self.app
        if graph is None:
            raise RuntimeError("Knowledge base graph has not been initialized")
        trace_id = str(uuid.uuid4())
        trace = RagTrace(
            trace_id=trace_id,
            original_query=request.question,
            knowledge_base_ids=request.knowledge_base_ids,
            session_id=request.session_id,
            run_mode=request.run_mode,
            started_at=datetime.now(),
        )
        await self.trace_recorder.start(trace, request.trace_required)
        config: RunnableConfig | None = None
        if request.session_id is not None:
            config = {"configurable": {"thread_id": request.session_id}}

        initial_state = KnowledgeQueryState(
            trace_id=trace_id,
            origin_query=request.question,
            knowledgebase_ids=request.knowledge_base_ids,
            record_usage=request.record_usage,
        )
        streamed_answer = False
        final_response = ""
        final_status = RagTraceStatus.COMPLETED
        try:
            async for part in graph.astream(
                initial_state,
                config=config,
                stream_mode=["messages", "updates"],
                version="v2",
            ):
                if part["type"] == "messages":
                    message_chunk, metadata = part["data"]
                    if metadata.get("langgraph_node") != "generate_answer":
                        continue
                    content = message_chunk.text
                    if content:
                        streamed_answer = True
                        yield RagExecutionEvent(type="answer_token", data=content)
                    continue
                if part["type"] != "updates":
                    continue
                update = part["data"]
                final_response = self._find_update_value(update, "response") or final_response
                status_value = self._find_update_value(update, "status")
                if status_value in {item.value for item in RagTraceStatus}:
                    final_status = RagTraceStatus(status_value)
                if not streamed_answer:
                    response_texts = collect_response_text(update)
                    if response_texts:
                        final_response = max(response_texts, key=len)
                        streamed_answer = True
                        yield RagExecutionEvent(type="answer_token", data=final_response)

            finished_trace = await self.trace_recorder.finish(trace_id, final_status, final_response)
            yield RagExecutionEvent(
                type="completed",
                data=RagRunResult(answer=final_response, trace=finished_trace),
            )
        except Exception as error:
            try:
                failed_trace = await self.trace_recorder.finish(
                    trace_id,
                    RagTraceStatus.FAILED,
                    final_response or SERVER_ERROR_RESPONSE,
                    error_stage="workflow",
                    error=str(error),
                )
                yield RagExecutionEvent(type="failed", data=failed_trace)
            finally:
                await self.trace_recorder.discard(trace_id)
            raise
        finally:
            await self.trace_recorder.discard(trace_id)

    @staticmethod
    def _find_update_value(value: Any, key: str) -> Any:
        if isinstance(value, dict):
            if key in value:
                return value[key]
            for nested in value.values():
                found = KnowledgeBaseQueryService._find_update_value(nested, key)
                if found is not None:
                    return found
        return None

    async def answer_question(self, question: str, ids: list[int], session_id: int | None = None) -> str:
        result = await self.execute(RagExecutionRequest(
            question=question,
            knowledge_base_ids=ids,
            session_id=session_id,
        ))
        return result.answer

    async def answer_question_stream(
        self,
        question: str,
        ids: list[int],
        session_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        request = RagExecutionRequest(
            question=question,
            knowledge_base_ids=ids,
            session_id=session_id,
        )
        async for event in self.execute_stream(request):
            if event.type == "answer_token":
                yield f"data:{event.data}\n\n"

    async def query_knowledge_base(self, db: AsyncSession, request: QueryRequest) -> QueryResponse:
        answer = await self.answer_question(request.question, request.knowledge_base_ids)
        names = await self.knowledgebase_list_service.get_knowledge_base_names(db, request.knowledge_base_ids)
        return QueryResponse(
            answer=answer,
            knowledge_base_id=request.knowledge_base_ids[0],
            knowledge_base_name=",".join(names),
        )

    async def build_workflow(self, checkpointer: Checkpointer | None = None) -> CompiledStateGraph:
        workflow = StateGraph(KnowledgeQueryState)
        workflow.add_node("pre_retrieve", self.pre_retrieve)
        workflow.add_node("vector_retrieve", self.vector_retrieve)
        workflow.add_node("generate_answer", self.generate_answer)
        workflow.add_node("no_result_response", self.no_result_response)
        workflow.add_edge(START, "pre_retrieve")
        return workflow.compile(checkpointer=checkpointer)

    async def pre_retrieve(self, state: KnowledgeQueryState, config: RunnableConfig) -> Command:
        if not state.knowledgebase_ids or not trim_question(state.origin_query):
            return Command(goto="no_result_response")
        if state.record_usage:
            async with async_session_factory() as db:
                try:
                    await self.knowledgebase_count_service.update_question_counts(db, state.knowledgebase_ids)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        original_query = trim_question(state.origin_query)
        prompt_name = "knowledgebase-query-rewrite"
        with_memory = has_short_memory(config)
        prompt_template = await load_prompt(prompt_name, with_memory)
        model = self._chat_model or await self.llm_provider_resolver.resolve(None)
        started = time.perf_counter()
        try:
            values: dict[str, Any] = {"question": original_query}
            if with_memory:
                values["messages"] = state.messages
            response = await (prompt_template | model).ainvoke(values)
            rewritten_query = response.text or original_query
            candidate_queries = list(dict.fromkeys([rewritten_query, original_query]))
            model_call = RagModelCall(
                purpose="query_rewrite",
                provider="default",
                model=_model_name(model),
                prompt_name=prompt_name,
                prompt_hash=await get_prompt_hash(prompt_name),
                token_usage=_token_usage(response),
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            await self.trace_recorder.event(state.trace_id, "query_rewritten", "pre_retrieve", {
                "rewritten_query": rewritten_query,
                "candidate_queries": candidate_queries,
                "model_call": model_call.model_dump(mode="json"),
            })
        except Exception as error:
            candidate_queries = [original_query]
            model_call = RagModelCall(
                purpose="query_rewrite",
                provider="default",
                model=_model_name(model),
                prompt_name=prompt_name,
                prompt_hash=await get_prompt_hash(prompt_name),
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(error),
            )
            await self.trace_recorder.event(state.trace_id, "query_rewrite_failed", "pre_retrieve", {
                "error": str(error),
                "model_call": model_call.model_dump(mode="json"),
            })
            logger.warning("Query rewrite failed; using original query: %s", error)

        compact_length = len(re.sub(r"\s+", "", original_query))
        if compact_length <= app_config.kb_short_query_length:
            search_params = {"top_k": app_config.kb_top_k_short, "min_score": app_config.kb_min_score_short}
        elif compact_length <= app_config.kb_mid_query_length:
            search_params = {"top_k": app_config.kb_top_k_medium, "min_score": app_config.kb_min_score_default}
        else:
            search_params = {"top_k": app_config.kb_top_k_long, "min_score": app_config.kb_min_score_default}
        return Command(
            update={"candidate_queries": candidate_queries, "search_params": search_params},
            goto="vector_retrieve",
        )

    async def vector_retrieve(self, state: KnowledgeQueryState) -> Command:
        for query in state.candidate_queries:
            if not query:
                continue
            started = time.perf_counter()
            scored = await self.knowledgebase_vector_service.similar_search_with_scores(
                query=query,
                knowledgebase_ids=state.knowledgebase_ids,
                top_k=state.search_params["top_k"],
                min_score=state.search_params["min_score"],
            )
            hits = [self._to_hit(item) for item in scored]
            attempt = RagRetrievalAttempt(
                query=query,
                top_k=state.search_params["top_k"],
                min_score=state.search_params["min_score"],
                hits=hits,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            await self.trace_recorder.event(
                state.trace_id, "retrieval_completed", "vector_retrieve", attempt.model_dump(mode="json")
            )
            docs = [item.document for item in scored]
            if has_effective_hit(query, docs):
                await self.trace_recorder.event(state.trace_id, "context_selected", "vector_retrieve", {
                    "selected_query": query,
                    "chunk_ids": [hit.chunk_id for hit in hits],
                })
                return Command(
                    update={"query_documents": docs, "selected_query": query},
                    goto="generate_answer",
                )
        return Command(
            update={"query_documents": [], "status": RagTraceStatus.NO_RESULT.value},
            goto="no_result_response",
        )

    @staticmethod
    def _to_hit(item: ScoredDocument) -> RagRetrievalHit:
        metadata = dict(item.document.metadata)
        return RagRetrievalHit(
            chunk_id=str(metadata.get("chunk_id") or f"legacy:{item.rank}"),
            content=item.document.page_content,
            score=item.score,
            rank=item.rank,
            metadata=metadata,
        )

    async def generate_answer(self, state: KnowledgeQueryState, config: RunnableConfig) -> Command:
        context = "\n\n---\n\n".join(doc.page_content for doc in state.query_documents)
        with_memory = has_short_memory(config)
        system_name = "knowledgebase-query-system"
        user_name = "knowledgebase-query-user"
        system_prompt: ChatPromptTemplate = await load_prompt(system_name, with_memory)
        user_prompt: ChatPromptTemplate = await load_prompt(user_name, with_memory)
        model = self._chat_model or await self.llm_provider_resolver.resolve(None)
        started = time.perf_counter()
        prompt_hash = f"{await get_prompt_hash(system_name)}:{await get_prompt_hash(user_name)}"
        try:
            values: dict[str, Any] = {
                "question": state.selected_query or state.origin_query,
                "context": context,
            }
            if with_memory:
                values["messages"] = state.messages
            answer = await ((system_prompt + user_prompt) | model).ainvoke(values)
            answer_text = check_answer(answer.text)
            model_call = RagModelCall(
                purpose="answer_generation",
                provider="default",
                model=_model_name(model),
                prompt_name=f"{system_name}+{user_name}",
                prompt_hash=prompt_hash,
                token_usage=_token_usage(answer),
                latency_ms=(time.perf_counter() - started) * 1000,
            )
            await self.trace_recorder.event(state.trace_id, "generation_completed", "generate_answer", {
                "response": answer_text,
                "model_call": model_call.model_dump(mode="json"),
            })
            return Command(
                update={
                    "response": answer_text,
                    "query_documents": [],
                    "status": RagTraceStatus.COMPLETED.value,
                    "messages": [(Role.USER.value, state.origin_query), (Role.ASSISTANT.value, answer_text)],
                },
                goto=END,
            )
        except Exception as error:
            model_call = RagModelCall(
                purpose="answer_generation",
                provider="default",
                model=_model_name(model),
                prompt_name=f"{system_name}+{user_name}",
                prompt_hash=prompt_hash,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=str(error),
            )
            await self.trace_recorder.event(state.trace_id, "generation_failed", "generate_answer", {
                "error": str(error),
                "response": SERVER_ERROR_RESPONSE,
                "model_call": model_call.model_dump(mode="json"),
            })
            logger.error("Knowledge base answer generation failed: %s", error)
            return Command(
                update={
                    "response": SERVER_ERROR_RESPONSE,
                    "query_documents": [],
                    "status": RagTraceStatus.FAILED.value,
                    "error_stage": "answer_generation",
                    "error": str(error),
                    "messages": [(Role.USER.value, state.origin_query), (Role.ASSISTANT.value, SERVER_ERROR_RESPONSE)],
                },
                goto=END,
            )

    async def no_result_response(self, state: KnowledgeQueryState) -> Command:
        await self.trace_recorder.event(state.trace_id, "context_selected", "no_result_response", {
            "selected_query": None,
            "chunk_ids": [],
        })
        return Command(
            update={
                "response": NO_RESULT_RESPONSE,
                "query_documents": [],
                "status": RagTraceStatus.NO_RESULT.value,
                "messages": [(Role.USER.value, state.origin_query), (Role.ASSISTANT.value, NO_RESULT_RESPONSE)],
            },
            goto=END,
        )
