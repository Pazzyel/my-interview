import pytest
from pydantic import ValidationError

from modules.llmprovider.model.llm_provider_dto import LlmProviderCreateRequest, LlmProviderDTO


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
