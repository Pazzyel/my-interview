import base64
import logging

import pytest

from common.exceptions import BusinessException
from modules.llmprovider.model.llm_provider_dto import LlmProviderCreateRequest
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service import api_key_encryption_service as encryption_module


def test_encrypt_round_trip_uses_random_nonce():
    service = ApiKeyEncryptionService("stable-test-key")
    first = service.encrypt("sk-super-secret")
    second = service.encrypt("sk-super-secret")

    assert first != second
    assert service.decrypt(*first) == "sk-super-secret"
    assert service.decrypt(*second) == "sk-super-secret"


def test_accepts_base64_encoded_32_byte_key():
    key = base64.b64encode(b"x" * 32).decode()
    service = ApiKeyEncryptionService(key)
    encrypted = service.encrypt("secret")
    assert service.decrypt(*encrypted) == "secret"


def test_wrong_key_and_tampering_are_rejected():
    ciphertext, nonce = ApiKeyEncryptionService("one").encrypt("secret")
    with pytest.raises(BusinessException, match="解密失败"):
        ApiKeyEncryptionService("two").decrypt(ciphertext, nonce)

    tampered = base64.b64encode(base64.b64decode(ciphertext)[:-1] + b"x").decode()
    with pytest.raises(BusinessException, match="解密失败"):
        ApiKeyEncryptionService("one").decrypt(tampered, nonce)


def test_missing_master_key_is_rejected(monkeypatch):
    monkeypatch.setattr(encryption_module.app_config, "llm_provider_encryption_key", None, raising=False)
    with pytest.raises(BusinessException, match="LLM_PROVIDER_ENCRYPTION_KEY"):
        ApiKeyEncryptionService().validate_ready()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("123456", "***"), ("1234567", "123***567")],
)
def test_mask_only_exposes_three_characters_at_each_end(value, expected):
    assert ApiKeyEncryptionService.mask(value) == expected


def test_api_key_is_not_present_in_request_repr_or_logs(caplog):
    # Secret input is never placed in a response DTO or logged by crypto operations.
    request = LlmProviderCreateRequest(
        id="demo", baseUrl="https://example.com", apiKey="secret-value", model="chat"
    )
    service = ApiKeyEncryptionService("key")
    with caplog.at_level(logging.INFO):
        ciphertext, nonce = service.encrypt(request.api_key.get_secret_value())
        assert service.decrypt(ciphertext, nonce) == "secret-value"
    assert "secret-value" not in caplog.text
    assert "secret-value" not in repr(request)
