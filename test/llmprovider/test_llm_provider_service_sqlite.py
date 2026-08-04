import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.config import app_config
from infrastructure.database.models import Base, LlmGlobalSettingORM, LlmProviderConfigORM
from modules.llmprovider.model.llm_provider_dto import (
    LlmProviderCreateRequest,
    LlmProviderUpdateRequest,
)
from modules.llmprovider.repository.llm_provider_repository import LlmProviderRepository
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service.llm_provider_registry import LlmProviderRegistry
from modules.llmprovider.service.llm_provider_service import LlmProviderService


async def build_service(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'provider.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[LlmProviderConfigORM.__table__, LlmGlobalSettingORM.__table__],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = LlmProviderRepository()
    encryption = ApiKeyEncryptionService("sqlite-test-key")
    registry = LlmProviderRegistry(repository, encryption, factory)
    service = LlmProviderService(repository, encryption, registry, factory)
    return engine, factory, repository, service


def bootstrap_payload(api_key="bootstrap-secret"):
    return json.dumps({
        "chat": {
            "baseUrl": "https://example.com", "apiKey": api_key, "model": "chat-model"
        },
        "embed": {
            "baseUrl": "https://example.com", "apiKey": "embed-secret", "model": "chat-model",
            "embeddingModel": "embed-model", "embeddingDimensions": 768,
            "supportsEmbedding": True,
        },
    })


def configure_bootstrap(monkeypatch):
    monkeypatch.setattr(app_config, "llm_provider_bootstrap_json", bootstrap_payload(), raising=False)
    monkeypatch.setattr(app_config, "llm_default_chat_provider", "chat", raising=False)
    monkeypatch.setattr(app_config, "llm_default_embedding_provider", "embed", raising=False)


def test_bootstrap_is_atomic_and_second_start_does_not_overwrite(tmp_path, monkeypatch):
    async def scenario():
        configure_bootstrap(monkeypatch)
        engine, factory, repository, service = await build_service(tmp_path)
        await service.initialize()
        async with factory() as db:
            assert await repository.count(db) == 2
            assert (await repository.get(db, "chat")).builtin is True
            settings = await repository.get_settings(db)
            assert settings.default_chat_provider_id == "chat"
            assert settings.default_embedding_provider_id == "embed"

        monkeypatch.setattr(app_config, "llm_provider_bootstrap_json", bootstrap_payload("changed"), raising=False)
        await service.initialize()
        async with factory() as db:
            provider = await repository.get(db, "chat")
            assert service.encryption.decrypt(provider.api_key_ciphertext, provider.api_key_nonce) == "bootstrap-secret"
        await engine.dispose()
    asyncio.run(scenario())


def test_crud_mask_partial_update_defaults_and_delete_protection(tmp_path, monkeypatch):
    async def scenario():
        configure_bootstrap(monkeypatch)
        engine, factory, repository, service = await build_service(tmp_path)
        await service.initialize()
        async with factory() as db:
            created = await service.create(db, LlmProviderCreateRequest(
                id="extra", baseUrl="https://provider.example/", apiKey="abcdefghi",
                model="old-model",
            ))
            assert created.masked_api_key == "abc***ghi"
            updated = await service.update(db, "extra", LlmProviderUpdateRequest(model="new-model"))
            assert updated.model == "new-model"
            row = await repository.get(db, "extra")
            assert service.encryption.decrypt(row.api_key_ciphertext, row.api_key_nonce) == "abcdefghi"

            await service.set_default_chat(db, "extra")
            with pytest.raises(Exception, match="默认 Provider"):
                await service.delete(db, "extra")
            await service.set_default_chat(db, "chat")
            await service.delete(db, "extra")
            assert await repository.get(db, "extra") is None
        await engine.dispose()
    asyncio.run(scenario())


def test_invalid_bootstrap_rolls_back_everything(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(app_config, "llm_provider_bootstrap_json", "{bad-json", raising=False)
        monkeypatch.setattr(app_config, "llm_default_chat_provider", "chat", raising=False)
        monkeypatch.setattr(app_config, "llm_default_embedding_provider", "chat", raising=False)
        engine, factory, repository, service = await build_service(tmp_path)
        with pytest.raises(Exception, match="格式无效"):
            await service.initialize()
        async with factory() as db:
            assert await repository.count(db) == 0
        await engine.dispose()
    asyncio.run(scenario())
