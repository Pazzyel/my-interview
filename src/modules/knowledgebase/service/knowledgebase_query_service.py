import logging
import re
from typing import Any, Optional, List, AsyncGenerator, Annotated

import regex
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Checkpointer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.config import app_config
from common.llm_provider import LlmProviderRegistry, LlmProviderResolver
from infrastructure.database.connection import async_session_factory
from infrastructure.prompt.prompt_service import load_prompt, has_short_memory, Role
from modules.knowledgebase.model.query_request import QueryRequest
from modules.knowledgebase.model.query_response import QueryResponse
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService
from modules.knowledgebase.service.knowledgebase_vector_service import KnowledgeBaseVectorService
from modules.knowledgebase.service.knowledgebase_count_service import KnowledgeBaseCountService

logger = logging.getLogger(__name__)

# 匹配2-20个字符的字符串
SHOT_TOKEN_PATTERN = r"^[\p{L}\p{N}_-]{2,20}$"
NO_RESULT_RESPONSE = "抱歉，在选定的知识库中未检索到相关信息。请换一个更具体的关键词或补充上下文后再试。"
SERVER_ERROR_RESPONSE = "抱歉，AI知识库问答服务暂时不可用。请您稍后再试。"


def collect_response_text(value: Any) -> List[str]:
    """Collect response fields from a LangGraph update event."""
    response_texts: List[str] = []
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
    origin_query: str
    candidate_queries: List[str] = []
    search_params: dict = {}
    # search_params: {
    #   ”top_k": 10
    #   "min_score": 100
    # }
    messages: Annotated[list[AnyMessage], add_messages] = [] # 历史消息
    knowledgebase_ids: List[int] # 知识库ID列表
    query_documents: List[Document] = [] # 查询到的文档列表
    response: str = "" # 模型生成结果

def trim_question(question: str) -> str:
    """去除问题的首尾空格"""
    return "" if question is None else question.strip()

def has_effective_hit(query: str, docs: List[Document]) -> bool:
    """检查RAG检索命中是否有效"""
    if docs is None or len(docs) == 0:
        return False

    # 不是短token查询默认有效
    query = trim_question(query)
    if not regex.match(SHOT_TOKEN_PATTERN, query):
        return True

    # # 是短token查询，检查查询的结果有没有包含查询的问题，有就是成功
    # for doc in docs:
    #     text = doc.page_content
    #     if text is not None and query.lower() in text.lower():
    #         return True

    # # 否则就是失败
    # logger.info("短 query 命中确认失败，视为无有效结果: question='%s', docs=%d", query, len(docs))
    # return False


    # 这个短token查询校验过于严格，先放宽为只要有结果就算命中，后续根据实际情况再调整
    return True 

def check_answer(answer: str) -> str:
    if answer is None or len(answer) == 0:
        return NO_RESULT_RESPONSE
    return answer.strip()

class KnowledgeBaseQueryService:
    def __init__(self, knowledgebase_list_service: KnowledgeBaseListService, knowledgebase_vector_service: KnowledgeBaseVectorService, knowledgebase_count_service: KnowledgeBaseCountService, llm_provider_resolver: LlmProviderResolver | None = None):
        # self.app = build_workflow()
        self.app = None
        self.knowledgebase_list_service = knowledgebase_list_service
        self.knowledgebase_vector_service = knowledgebase_vector_service
        self.knowledgebase_count_service = knowledgebase_count_service
        self.llm_provider_resolver = llm_provider_resolver or LlmProviderRegistry()
        self._chat_model = None

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        self.app = await self.build_workflow(checkpointer)

    async def answer_question(self, question: str, ids: List[int], session_id: Optional[int] = None) -> str:
        """根据知识库回答问题"""
        config: Optional[RunnableConfig] = {
            "configurable": {
                "thread_id": session_id
            }
        } if session_id is not None else None
        initial_state: KnowledgeQueryState = KnowledgeQueryState(origin_query=question, knowledgebase_ids=ids)
        response_state: KnowledgeQueryState = await self.app.ainvoke(initial_state,config=config) # type: ignore
        return response_state.response

    async def answer_question_stream(self, question: str, ids: List[int], session_id: Optional[int] = None) -> AsyncGenerator[str, None]:
        """根据知识库回答问题，流式输出"""
        config: Optional[RunnableConfig] = {
            "configurable": {
                "thread_id": session_id
            }
        } if session_id is not None else None
        initial_state: KnowledgeQueryState = KnowledgeQueryState(origin_query=question, knowledgebase_ids=ids)
        streamed_answer = False
        async for part in self.app.astream(  # type: ignore
            initial_state,
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if part["type"] == "messages":
                message_chunk, metadata = part["data"]
                # pre_retrieve 也会调用 LLM 重写查询，只向客户端转发最终回答节点的 token。
                if metadata.get("langgraph_node") != "generate_answer":
                    continue

                content = message_chunk.text
                if not content:
                    continue

                streamed_answer = True
                # 保持现有纯文本 SSE 协议，并正确表达 token 内的换行。
                # 字符是在每个上游 token 到达时立即发送，不再等待完整回答。
                yield f"data:{content}\n\n"
                continue

            if part["type"] != "updates":
                continue

            # no_result_response 等静态回答不会产生 LLM token，从状态更新中兜底输出。
            # generate_answer 完成时还会返回完整 response，已流式输出时必须跳过以避免重复。
            response_texts = collect_response_text(part["data"])
            if len(response_texts) == 0 or streamed_answer:
                continue

            response_text = max(response_texts, key=len)
            yield f"data:{response_text}\n\n"


    async def query_knowledge_base(self, db: AsyncSession, request: QueryRequest) -> QueryResponse:
        """根据知识库查询请求执行查询并构建响应"""
        answer: str = await self.answer_question(request.question, request.knowledge_base_ids)

        # 获取知识库名称
        knowledgebase_names: List[str] = await self.knowledgebase_list_service.get_knowledge_base_names(db, request.knowledge_base_ids)
        knowledgebase_names_str: str = ",".join(knowledgebase_names)

        # 使用第一个知识库ID作为主要标识
        primary_knowledgebase_id: int = request.knowledge_base_ids[0]
        return QueryResponse(answer=answer,knowledge_base_id=primary_knowledgebase_id,knowledge_base_name=knowledgebase_names_str)




    async def build_workflow(self, checkpointer: Checkpointer = None) -> CompiledStateGraph:
        workflow = StateGraph(KnowledgeQueryState)
        workflow.add_node("pre_retrieve",self.pre_retrieve)
        workflow.add_node("vector_retrieve",self.vector_retrieve)
        workflow.add_node("generate_answer", self.generate_answer)
        workflow.add_node("no_result_response",self.no_result_response)

        workflow.add_edge(START,"pre_retrieve")
        return workflow.compile(checkpointer = checkpointer)

    async def pre_retrieve(self, state: KnowledgeQueryState, config: RunnableConfig) -> Command:
        """对用户查询进行预处理"""
        # 空查询直接返回
        ids: List[int] = state.knowledgebase_ids
        if ids is None or len(ids) == 0 or trim_question(state.origin_query) == "":
            return Command(goto="no_result_response")

        # 0. 增加文档元数据里的计数
        async with async_session_factory() as db:
            try:
                await self.knowledgebase_count_service.update_question_counts(db, state.knowledgebase_ids)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        # 1. 去掉空格
        origin_query: Optional[str] = state.origin_query
        original_query: str = trim_question(origin_query)

        # 2. LLM重写查询
        existing_short_memory: bool = has_short_memory(config)
        prompt_template: ChatPromptTemplate = await load_prompt("knowledgebase-query-rewrite",existing_short_memory)
        model = self._chat_model or await self.llm_provider_resolver.resolve(None)
        chain = prompt_template | model
        try:
            if existing_short_memory:
                response = await chain.ainvoke({
                    "question": original_query,
                    "messages": state.messages,
                })            
            else:
                response = await chain.ainvoke({"question": original_query})
            logger.info("LLM query rewrite response: %s", response.text)
            rewritten_query = response.text if response.text is not None and len(response.text) > 0 else original_query
            logger.info("Query rewrite: origin='%s', rewritten='%s'", origin_query, response.text)
        except Exception as e:
            logger.warning("Query rewrite 失败，使用原问题继续检索: %s", e)
            rewritten_query = original_query


        # 3. 构建状态
        candidate_queries = [rewritten_query, origin_query]
        compact_length = len(re.sub(r"\s+","",origin_query)) # 去除用户输入空格之后的字符串
        if compact_length <= app_config.kb_short_query_length:
            search_params = {
                "top_k": app_config.kb_top_k_short,
                "min_score": app_config.kb_min_score_short,
            }
        elif compact_length <= app_config.kb_mid_query_length:
            search_params = {
                "top_k": app_config.kb_top_k_medium,
                "min_score": app_config.kb_min_score_default,
            }
        else:
            search_params = {
                "top_k": app_config.kb_top_k_long,
                "min_score": app_config.kb_min_score_default,
            }

        return Command(
            update={
                "candidate_queries": candidate_queries,
                "search_params": search_params,
            },
            goto="vector_retrieve",
        )

    async def vector_retrieve(self, state: KnowledgeQueryState) -> Command:
        """检索RAG节点"""
        # 第一个是重写的查询，如果命中就不会再查询第二个
        for query in state.candidate_queries:
            if query is None or len(query) == 0:
                continue
            docs: List[Document] = await self.knowledgebase_vector_service.similar_search(
                query=query,
                knowledgebase_ids=state.knowledgebase_ids,
                top_k=state.search_params["top_k"],
                min_score=state.search_params["min_score"],
            )
            logger.info("检索候选 query='%s'，命中 %d 条", query, len(docs))
            # 命中有效就直接返回
            if has_effective_hit(query, docs):
                return Command(
                    update={
                        "query_documents": docs,
                    },
                    goto="generate_answer",
                )

        # 什么都没有命中
        return Command(
            update={
                "query_documents": [],
            },
            goto="no_result_response",
        )

    async def generate_answer(self, state: KnowledgeQueryState, config: RunnableConfig) -> Command:
        """根据用户提问的和RAG检索内容回答"""

        # 构建上下文，合并检索的文档
        docs: List[Document] = state.query_documents
        context: str = "\n\n---\n\n".join(doc.page_content for doc in docs)
        logger.info("检索到 %d 个相关文档片段，第一篇内容是: %s", len(docs), docs[0].page_content[0:100] + "..." if docs else "N/A")

        exists_short_memory: bool = has_short_memory(config)
        system_prompt: ChatPromptTemplate = await load_prompt("knowledgebase-query-system", exists_short_memory)
        user_prompt: ChatPromptTemplate = await load_prompt("knowledgebase-query-user", exists_short_memory)

        model = self._chat_model or await self.llm_provider_resolver.resolve(None)
        chain = (system_prompt + user_prompt) | model
        try:
            if exists_short_memory:
                answer = await chain.ainvoke({
                    "question": state.candidate_queries[0], # 一般是重写后的问题
                    "messages": state.messages,
                    "context": context,
                })
            else:
                answer = await chain.ainvoke({
                    "question": state.candidate_queries[0], # 一般是重写后的问题
                    "context": context,
                })
            logger.info("LLM generate answer response: %s", answer.text)
            answer_text = check_answer(answer.text)
            logger.info("知识库问答完成: kbIds=%s", state.knowledgebase_ids)
            return Command(
                update={
                    "response": answer_text,
                    "messages": [
                        (Role.USER.value, state.origin_query),
                        (Role.ASSISTANT.value, answer_text),
                    ],
                },
                goto=END,
            )
        except Exception as e:
            logger.error("知识库问答失败: %s", e)
            return Command(
                update={
                    "response": SERVER_ERROR_RESPONSE,
                    "messages": [
                        (Role.USER.value, state.origin_query),
                        (Role.ASSISTANT.value, SERVER_ERROR_RESPONSE),
                    ],
                },
                goto=END,
            )
        
    def no_result_response(self, state: KnowledgeQueryState) -> Command:
        """无内容的返回节点"""
        return Command(
            update={
                "response": NO_RESULT_RESPONSE,
                "messages": [
                    (Role.USER.value, state.origin_query),
                    (Role.ASSISTANT.value, NO_RESULT_RESPONSE),
                ],
            },
            goto=END,
        )
