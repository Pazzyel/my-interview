import asyncio
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessageChunk

from modules.knowledgebase.service.knowledgebase_query_service import (
    KnowledgeBaseQueryService,
)
from modules.knowledgebase.service.rag_chat_session_service import RagChatSessionService


class FakeGraph:
    def __init__(self, events):
        self.events = events
        self.stream_kwargs = None

    async def astream(self, *_args, **kwargs):
        self.stream_kwargs = kwargs
        for event in self.events:
            yield event


def test_answer_question_stream_emits_model_chunks_and_ignores_other_nodes() -> None:
    async def scenario() -> None:
        service = KnowledgeBaseQueryService(AsyncMock(), AsyncMock(), AsyncMock())
        graph = FakeGraph([
            {
                "type": "messages",
                "ns": (),
                "data": (
                    AIMessageChunk(content="rewritten question"),
                    {"langgraph_node": "pre_retrieve"},
                ),
            },
            {
                "type": "messages",
                "ns": (),
                "data": (
                    AIMessageChunk(content="Hello\n"),
                    {"langgraph_node": "generate_answer"},
                ),
            },
            {
                "type": "messages",
                "ns": (),
                "data": (
                    AIMessageChunk(content="Python"),
                    {"langgraph_node": "generate_answer"},
                ),
            },
            {
                "type": "updates",
                "ns": (),
                "data": {"generate_answer": {"response": "Hello\nPython"}},
            },
        ])
        service.app = graph

        chunks = [
            chunk
            async for chunk in service.answer_question_stream("question", [1])
        ]

        assert "".join(chunk[5:-2] for chunk in chunks) == "Hello\nPython"
        assert all(
            chunk.startswith("data:") and chunk.endswith("\n\n")
            for chunk in chunks
        )
        assert all("[DONE]" not in chunk and "response" not in chunk for chunk in chunks)
        assert graph.stream_kwargs == {
            "config": None,
            "stream_mode": ["messages", "updates"],
            "version": "v2",
        }

    asyncio.run(scenario())


def test_answer_question_stream_falls_back_to_static_update() -> None:
    async def scenario() -> None:
        service = KnowledgeBaseQueryService(AsyncMock(), AsyncMock(), AsyncMock())
        service.app = FakeGraph([
            {
                "type": "updates",
                "ns": (),
                "data": {"no_result_response": {"response": "No result"}},
            },
        ])

        chunks = [
            chunk
            async for chunk in service.answer_question_stream("question", [1])
        ]

        assert "".join(chunk[5:-2] for chunk in chunks) == "No result"

    asyncio.run(scenario())


def test_rag_chat_extracts_plain_text_without_trimming_whitespace() -> None:
    service = RagChatSessionService(AsyncMock(), AsyncMock())

    assert service._extract_response_content("data:A\n\n") == "A"
    assert service._extract_response_content("data: \n\n") == " "
    assert service._extract_response_content("data:\n\n\n") == "\n"
    assert service._extract_response_content("data:legacy") == ""
