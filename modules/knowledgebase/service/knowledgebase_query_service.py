import json
import logging
import re
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, AsyncGenerator, Annotated

import aiofile
import regex
import yaml
from langchain_community.chat_models import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.prompts.chat import MessageLikeRepresentation
from langchain_core.runnables import RunnableConfig
from langgraph.constants import START, END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Checkpointer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from common.ai_config import ai_config
from common.dependencies import knowledgebase_vector_service, knowledgebase_count_service
from infrastructure.database.connection import async_session_factory
from modules.knowledgebase.model.query_request import QueryRequest
from modules.knowledgebase.model.query_response import QueryResponse
from modules.knowledgebase.service.knowledgebase_list_service import KnowledgeBaseListService

llm = ChatOpenAI(
    model = ai_config.model,
    api_key = ai_config.api_key,
    base_url = ai_config.base_url,
)

# 匹配2-20个字符的字符串
SHOT_TOKEN_PATTERN = r"^[\p{L}\p{N}_-]{2,20}$"
NO_RESULT_RESPONSE = "抱歉，在选定的知识库中未检索到相关信息。请换一个更具体的关键词或补充上下文后再试。"
SERVER_ERROR_RESPONSE = "抱歉，AI知识库问答服务暂时不可用。请您稍后再试。"

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

current_dir = Path(__file__).parent
root_dir = current_dir.parents[2]
prompt_cache: Dict[str, ChatPromptTemplate] = {} # 全局prompt缓存

class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"

async def load_prompt(node_name: str):
    """
    加载对应名字的提示词文件

    从resources/prompts/{node_name}.yaml加载
    """
    # 有缓存就加载缓存
    if node_name in prompt_cache:
        return prompt_cache[node_name]

    prompt_path: Path = root_dir / "resources" / "prompts" / f"{node_name}.yaml"
    async with aiofile.async_open(prompt_path, "r", encoding="utf-8") as f:
        content = await f.read()
    config = yaml.safe_load(content)

    # 动态构建prompt
    node_config = config.get(node_name)
    messages: List[MessageLikeRepresentation] = []
    # 先加载系统提示词
    if Role.SYSTEM.value in node_config:
        messages.append((Role.SYSTEM.value, node_config[Role.SYSTEM.value]))
    # 再加载历史提示词
    messages.append(MessagesPlaceholder(variable_name="messages"))
    # 最后加载用户提问
    if Role.USER.value in node_config:
        messages.append((Role.USER.value, node_config[Role.USER.value]))

    prompt = ChatPromptTemplate.from_messages(messages)
    prompt_cache[node_name] = prompt
    return prompt

def trim_question(question: str) -> str:
    """去除问题的首尾空格"""
    return "" if question is None else question.strip()

def no_result_response(state: KnowledgeQueryState) -> Command:
    """无内容的返回节点"""
    return Command(
        update={
            "response": NO_RESULT_RESPONSE,
        }
    )


async def pre_retrieve(state: KnowledgeQueryState) -> Command:
    """对用户查询进行预处理"""
    # 空查询直接返回
    ids: List[int] = state.knowledgebase_ids
    if ids is None or len(ids) == 0 or trim_question(state.origin_query) == "":
        return Command(goto="no_result_response")

    # 0. 增加文档元数据里的计数
    async with async_session_factory() as db:
        await knowledgebase_count_service.update_question_counts(db, state.knowledgebase_ids)
        await db.commit()

    # 1. 去掉空格
    origin_query: Optional[str] = state.origin_query
    original_query: str = trim_question(origin_query)

    # 2. LLM重写查询
    prompt_template: ChatPromptTemplate = await load_prompt("knowledgebase-query-rewrite")
    chain = prompt_template | llm
    try:
        response = await chain.ainvoke({"question": original_query})
        rewritten_query = response.content if response.content is not None and len(response.content) > 0 else original_query
        logging.info("Query rewrite: origin='{}', rewritten='{}'", origin_query, response.content)
    except Exception as e:
        logging.warning("Query rewrite 失败，使用原问题继续检索: {}", e)
        rewritten_query = original_query


    # 3. 构建状态
    candidate_queries = [rewritten_query, origin_query]
    compact_length = len(re.sub(r"\s+","",origin_query)) # 去除用户输入空格之后的字符串
    if compact_length <= ai_config.short_query_length:
        search_params = {
            "top_k": ai_config.top_k_short,
            "min_score": ai_config.min_score_short,
        }
    elif compact_length <= ai_config.medium_query_length:
        search_params = {
            "top_k": ai_config.top_k_medium,
            "min_score": ai_config.min_score_default,
        }
    else:
        search_params = {
            "top_k": ai_config.top_k_long,
            "min_score": ai_config.min_score_default,
        }

    return Command(
        update={
            "candidate_queries": candidate_queries,
            "search_params": search_params,
        },
        goto="vector_retrieve",
    )

def has_effective_hit(query: str, docs: List[Document]) -> bool:
    """检查RAG检索命中是否有效"""
    if docs is None or len(docs) == 0:
        return False

    # 不是短token查询默认有效
    query = trim_question(query)
    if not regex.match(SHOT_TOKEN_PATTERN, query):
        return True

    # 是短token查询，检查查询的结果有没有包含查询的问题，有就是成功
    for doc in docs:
        text = doc.page_content
        if text is not None and query.lower() in text.lower():
            return True

    # 否则就是失败
    logging.info("短 query 命中确认失败，视为无有效结果: question='{}', docs={}", query, len(docs))
    return False


async def vector_retrieve(state: KnowledgeQueryState) -> Command:
    """检索RAG节点"""
    # 第一个是重写的查询，如果命中就不会再查询第二个
    for query in state.candidate_queries:
        if query is None or len(query) == 0:
            continue
        docs: List[Document] = await knowledgebase_vector_service.similar_search(
            query=query,
            knowledgebase_ids=state.knowledgebase_ids,
            top_k=state.search_params["top_k"],
            min_score=state.search_params["min_score"],
        )
        logging.info("检索候选 query='{}'，命中 {} 条", query, len(docs))
        # 命中有效就直接返回
        if has_effective_hit(query, docs):
            return Command(
                update={
                    "query_documents": docs,
                },
                goto="answer_question",
            )

    # 什么都没有命中
    return Command(
        update={
            "query_documents": [],
        },
        goto="no_result_response",
    )

def check_answer(answer: str) -> str:
    if answer is None or len(answer) == 0:
        return NO_RESULT_RESPONSE
    return answer.strip()

async def answer_question(state: KnowledgeQueryState) -> Command:
    """根据用户提问的和RAG检索内容回答"""

    # 构建上下文，合并检索的文档
    docs: List[Document] = state.query_documents
    context: str = "\n\n---\n\n".join(doc.page_content for doc in docs)
    logging.debug("检索到 {} 个相关文档片段", len(docs))

    system_prompt: ChatPromptTemplate = await load_prompt("knowledgebase-query-system")
    user_prompt: ChatPromptTemplate = await load_prompt("knowledgebase-query-user")

    chain = (system_prompt + user_prompt) | llm
    try:
        answer = await chain.ainvoke({
            "question": state.candidate_queries[0], # 一般是重写后的问题
            "context": context,
        })
        answer_text = check_answer(answer.content)
        logging.info("知识库问答完成: kbIds={}", state.knowledgebase_ids)
        return Command(
            update={"response": answer_text},
        )
    except Exception as e:
        logging.error("知识库问答失败: {}", e)
        return Command(
            update={"response": SERVER_ERROR_RESPONSE},
        )

async def build_workflow(checkpointer: Checkpointer = None) -> CompiledStateGraph:
    workflow = StateGraph(KnowledgeQueryState)
    workflow.add_node("pre_retrieve",pre_retrieve)
    workflow.add_node("vector_retrieve",vector_retrieve)
    workflow.add_node("answer_question",answer_question)
    workflow.add_node("no_result_response",no_result_response)

    workflow.add_edge(START,"pre_retrieve")
    workflow.add_edge("pre_retrieve","no_result_response")
    workflow.add_edge("pre_retrieve","vector_retrieve")
    workflow.add_edge("vector_retrieve","no_result_response")
    workflow.add_edge("vector_retrieve","answer_question")
    workflow.add_edge("no_result_response",END)
    workflow.add_edge("answer_question",END)

    return workflow.compile(checkpointer = checkpointer)

class KnowledgeBaseQueryService:
    def __init__(self, knowledgebase_list_service: KnowledgeBaseListService):
        # self.app = build_workflow()
        self.app = None
        self.knowledgebase_list_service = knowledgebase_list_service

    async def build_graph(self, checkpointer: Checkpointer) -> None:
        self.app = await build_workflow(checkpointer)

    async def answer_question(self, question: str, ids: List[int], session_id: Optional[int] = None) -> str:
        """根据知识库回答问题"""
        config: Optional[RunnableConfig] = {
            "configurable": {
                "thread_id": session_id
            }
        } if session_id is not None else None
        initial_state: KnowledgeQueryState = KnowledgeQueryState(origin_query=question, knowledgebase_ids=ids)
        response_state: KnowledgeQueryState = await self.app.ainvoke(initial_state,config=config)
        return response_state.response

    async def answer_question_stream(self, question: str, ids: List[int], session_id: Optional[int] = None) -> AsyncGenerator[str]:
        """根据知识库回答问题，流式输出"""
        config: Optional[RunnableConfig] = {
            "configurable": {
                "thread_id": session_id
            }
        } if session_id is not None else None
        initial_state: KnowledgeQueryState = KnowledgeQueryState(origin_query=question, knowledgebase_ids=ids)
        async for event in self.app.astream(
                initial_state,
                config=config,
                stream_mode="updates"
        ):
            # 3. 格式化为 SSE 协议格式
            # event 结构通常为: {"node_name": {"field": "value"}}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 4. 发送结束信号
        yield "data: [DONE]\n\n"


    async def query_knowledge_base(self, db: AsyncSession, request: QueryRequest) -> QueryResponse:
        """根据知识库查询请求执行查询并构建响应"""
        answer: str = await self.answer_question(request.question,request.knowledge_base_ids)

        # 获取知识库名称
        knowledgebase_names: List[str] = await self.knowledgebase_list_service.get_knowledge_base_names(db, request.knowledge_base_ids)
        knowledgebase_names_str: str = ",".join(knowledgebase_names)

        # 使用第一个知识库ID作为主要标识
        primary_knowledgebase_id: int = request.knowledge_base_ids[0]
        return QueryResponse(answer=answer,knowledge_base_id=primary_knowledgebase_id,knowledge_base_name=knowledgebase_names_str)

