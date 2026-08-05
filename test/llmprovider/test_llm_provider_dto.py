import pytest
from pydantic import ValidationError

from modules.llmprovider.model.llm_provider_dto import (
    AsrConfigRequest,
    LlmProviderCreateRequest,
    LlmProviderDTO,
    TtsConfigRequest,
)


def test_voice_requests_accept_camel_case_partial_updates() -> None:
    asr = AsrConfigRequest.model_validate({
        "sampleRate": 16000, "enableTurnDetection": False,
        "turnDetectionSilenceDurationMs": 0,
    })
    assert asr.sample_rate == 16000
    assert asr.enable_turn_detection is False
    assert asr.model_fields_set == {
        "sample_rate", "enable_turn_detection", "turn_detection_silence_duration_ms"
    }
    tts = TtsConfigRequest.model_validate({"speechRate": 1.2, "volume": 70})
    assert tts.model_dump(by_alias=True, exclude_none=True) == {"speechRate": 1.2, "volume": 70}


@pytest.mark.parametrize(
    "request_type,payload",
    [
        (AsrConfigRequest, {"url": "https://not-websocket.example"}),
        (AsrConfigRequest, {"model": " "}),
        (AsrConfigRequest, {"sampleRate": 0}),
        (AsrConfigRequest, {"turnDetectionThreshold": 1.1}),
        (TtsConfigRequest, {"apiKey": " "}),
        (TtsConfigRequest, {"speechRate": 0}),
        (TtsConfigRequest, {"volume": 101}),
    ],
)
def test_voice_requests_reject_invalid_values(request_type, payload) -> None:
    with pytest.raises(ValidationError):
        request_type.model_validate(payload)


def test_create_request_accepts_frontend_camel_case():
    request = LlmProviderCreateRequest.model_validate({
        "id": "openai-prod", "baseUrl": "https://example.com", "apiKey": "secret",
        "model": "chat", "embeddingModel": "embed", "embeddingDimensions": 1024,
        "supportsEmbedding": True,
    })
    assert request.embedding_dimensions == 1024


@pytest.mark.parametrize("provider_id", ["", "space id", "slash/id", "x" * 65])
def test_provider_id_validation(provider_id):
    with pytest.raises(ValidationError):
        LlmProviderCreateRequest(
            id=provider_id, baseUrl="https://example.com", apiKey="secret", model="chat"
        )


def test_embedding_configuration_is_required_when_supported():
    with pytest.raises(ValidationError, match="embeddingModel"):
        LlmProviderCreateRequest(
            id="demo", baseUrl="https://example.com", apiKey="secret",
            model="chat", supportsEmbedding=True,
        )


def test_provider_response_is_camel_case_and_contains_no_plain_key():
    dto = LlmProviderDTO(
        id="demo", baseUrl="https://example.com", maskedApiKey="sec***ret", model="chat",
        supportsEmbedding=False, temperature=0, enabled=True, builtin=False,
    )
    payload = dto.model_dump(by_alias=True)
    assert payload["maskedApiKey"] == "sec***ret"
    assert "apiKey" not in payload
