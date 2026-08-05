import asyncio
from unittest.mock import AsyncMock

from modules.knowledgebase.service.knowledgebase_query_service import (
    KnowledgeBaseQueryService,
)
from modules.knowledgebase.service.rag_chat_session_service import RagChatSessionService


class FakeGraph:
    async def astream(self, *_args, **_kwargs):
        yield {"pre_retrieve": {"candidate_queries": ["python"]}}
        yield {"generate_answer": {"response": "Hello\nPython"}}


def test_answer_question_stream_emits_plain_text_sse_fragments() -> None:
    async def scenario() -> None:
        service = KnowledgeBaseQueryService(AsyncMock(), AsyncMock(), AsyncMock())
        service.app = FakeGraph()

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

    asyncio.run(scenario())


def test_rag_chat_extracts_plain_text_without_trimming_whitespace() -> None:
    service = RagChatSessionService(AsyncMock(), AsyncMock())

    assert service._extract_response_content("data:A\n\n") == "A"
    assert service._extract_response_content("data: \n\n") == " "
    assert service._extract_response_content("data:\n\n\n") == "\n"
    assert service._extract_response_content("data:legacy") == ""
