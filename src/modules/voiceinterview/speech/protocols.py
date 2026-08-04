from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


TextCallback = Callable[[str], Awaitable[None]]
ReadyCallback = Callable[[], Awaitable[None]]
ErrorCallback = Callable[[Exception], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AsrCallbacks:
    on_partial: TextCallback
    on_final: TextCallback
    on_ready: ReadyCallback
    on_error: ErrorCallback


class AsrStream(Protocol):
    async def send_audio(self, pcm: bytes) -> None: ...

    async def close(self) -> None: ...


class AsrProvider(Protocol):
    async def open(self, session_id: str, callbacks: AsrCallbacks) -> AsrStream: ...


class TtsProvider(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Return raw signed PCM16 little-endian, 24 kHz, mono."""
        ...
