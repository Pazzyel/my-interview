from __future__ import annotations

from typing import Any, Protocol


class ConversationServiceProtocol(Protocol):
    async def generate_reply(self, db: Any, session: Any, user_text: str) -> str: ...


class OpeningConversationServiceProtocol(Protocol):
    async def generate_opening(self, db: Any, session: Any) -> str: ...


class SessionServiceProtocol(Protocol):
    async def get_session(self, db: Any, session_id: int) -> Any: ...

    async def start_phase(self, db: Any, session_id: int, phase: str) -> Any: ...

    async def end_session(self, db: Any, session_id: int) -> Any: ...
