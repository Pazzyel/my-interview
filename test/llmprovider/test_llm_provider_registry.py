from datetime import datetime, timedelta
import asyncio

import pytest

from infrastructure.database.models import LlmGlobalSettingORM, LlmProviderConfigORM
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service.llm_provider_registry import LlmProviderRegistry


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeFactory:
    def __call__(self):
        return FakeSession()


class FakeRepository:
    def __init__(self, provider, settings):
        self.provider = provider
        self.settings = settings

    async def get_settings(self, _db):
        return self.settings

    async def get(self, _db, provider_id):
        return self.provider if provider_id == self.provider.id else None


def make_registry(enabled=True, embedding=True):
    crypto = ApiKeyEncryptionService("registry-key")
    ciphertext, nonce = crypto.encrypt("secret")
    provider = LlmProviderConfigORM(
        id="demo", base_url="https://example.com/api", api_key_ciphertext=ciphertext,
        api_key_nonce=nonce, model="chat-model", embedding_model="embed-model",
        embedding_dimensions=1024, supports_embedding=embedding,
        temperature=0, enabled=enabled, builtin=False, created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    settings = LlmGlobalSettingORM(
        id=1, default_chat_provider_id="demo", default_embedding_provider_id="demo"
    )
    return LlmProviderRegistry(FakeRepository(provider, settings), crypto, FakeFactory()), provider


def test_default_aliases_and_cache_reuse():
    async def scenario():
        registry, _ = make_registry()
        first = await registry.get_chat_model(None)
        assert await registry.get_chat_model("") is first
        assert await registry.get_chat_model("default") is first
        assert await registry.get_chat_model("demo") is first
    asyncio.run(scenario())


def test_configuration_version_change_rebuilds_model():
    async def scenario():
        registry, provider = make_registry()
        first = await registry.get_chat_model("demo")
        provider.model = "new-model"
        provider.updated_at += timedelta(seconds=1)
        second = await registry.get_chat_model("demo")
        assert second is not first
        assert second.model_name == "new-model"
    asyncio.run(scenario())


def test_reload_clears_models():
    async def scenario():
        registry, _ = make_registry()
        first = await registry.get_chat_model("demo")
        await registry.reload()
        assert await registry.get_chat_model("demo") is not first
    asyncio.run(scenario())


def test_unknown_disabled_and_missing_embedding_fail_clearly():
    async def scenario():
        registry, _ = make_registry()
        with pytest.raises(Exception, match="不存在"):
            await registry.get_chat_model("missing")

        disabled, _ = make_registry(enabled=False)
        with pytest.raises(Exception, match="禁用"):
            await disabled.get_chat_model("demo")

        chat_only, _ = make_registry(embedding=False)
        with pytest.raises(Exception, match="Embedding"):
            await chat_only.get_default_embedding_model()
    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.com/", "https://example.com/v1"),
        ("https://example.com/api", "https://example.com/api/v1"),
        ("https://example.com/api/v3/", "https://example.com/api/v3"),
    ],
)
def test_base_url_normalization(raw, expected):
    assert LlmProviderRegistry.normalize_base_url(raw) == expected
