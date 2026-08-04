import asyncio

import pytest

from modules.voiceinterview.speech.dashscope import (
    DashScopeAsrConfig,
    DashScopeAsrProvider,
    DashScopeTtsConfig,
    DashScopeTtsProvider,
    SpeechConfigurationError,
    _asr_session_update,
    _event_text,
    _event_type,
    _tts_session_update,
)
from modules.voiceinterview.speech.protocols import AsrCallbacks


def test_dashscope_event_helpers_accept_realtime_variants() -> None:
    assert _event_type({"type": "response.audio.delta"}) == "response.audio.delta"
    assert _event_text({"transcript": "完成文本"}) == "完成文本"
    assert _event_text({"item": {"text": "嵌套文本"}}) == "嵌套文本"


def test_missing_api_key_is_checked_only_when_provider_is_used() -> None:
    asr = DashScopeAsrProvider(DashScopeAsrConfig(api_key=None))
    tts = DashScopeTtsProvider(DashScopeTtsConfig(api_key=""))
    callbacks = AsrCallbacks(
        on_partial=lambda _text: asyncio.sleep(0),
        on_final=lambda _text: asyncio.sleep(0),
        on_ready=lambda: asyncio.sleep(0),
        on_error=lambda _exc: asyncio.sleep(0),
    )

    with pytest.raises(SpeechConfigurationError):
        asyncio.run(asr.open("1", callbacks))
    with pytest.raises(SpeechConfigurationError):
        asyncio.run(tts.synthesize("问题"))


def test_realtime_session_events_match_dashscope_contract() -> None:
    asr = _asr_session_update(DashScopeAsrConfig(api_key="key"))
    assert asr["event_id"].startswith("event_")
    assert asr["session"]["input_audio_format"] == "pcm"
    assert asr["session"]["sample_rate"] == 16000
    assert asr["session"]["input_audio_transcription"] == {"language": "zh"}

    tts = _tts_session_update(DashScopeTtsConfig(api_key="key"))
    assert tts["event_id"].startswith("event_")
    assert tts["session"]["response_format"] == "pcm"
    assert tts["session"]["sample_rate"] == 24000
    assert tts["session"]["mode"] == "commit"
