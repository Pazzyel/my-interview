import re
from dataclasses import dataclass
from typing import Protocol

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import LlmProviderConfigORM
from modules.llmprovider.repository.llm_provider_repository import LlmProviderRepository
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService


class LlmProviderResolver(Protocol):
    async def resolve(self, provider: str | None) -> ChatOpenAI: ...


@dataclass(frozen=True)
class _Resolved:
    provider: LlmProviderConfigORM
    api_key: str


class LlmProviderRegistry:
    def __init__(
        self,
        repository: LlmProviderRepository | None = None,
        encryption: ApiKeyEncryptionService | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.repository = repository or LlmProviderRepository()
        self.encryption = encryption or ApiKeyEncryptionService()
        self.session_factory = session_factory
        self._chat_cache: dict[tuple, ChatOpenAI] = {}
        self._embedding_cache: dict[tuple, OpenAIEmbeddings] = {}

    async def resolve(self, provider: str | None) -> ChatOpenAI:
        return await self.get_chat_model(provider)

    async def get_chat_model(self, provider_id: str | None = None) -> ChatOpenAI:
        resolved = await self._load(provider_id, embedding=False)
        row = resolved.provider
        key = (row.id, self._version(row), "chat")
        model = self._chat_cache.get(key)
        if model is None:
            model = ChatOpenAI(
                model=row.model,
                api_key=SecretStr(resolved.api_key),
                base_url=self.normalize_base_url(row.base_url),
                temperature=row.temperature,
            )
            self._chat_cache = {
                cached_key: cached_model
                for cached_key, cached_model in self._chat_cache.items()
                if cached_key[0] != row.id
            }
            self._chat_cache[key] = model
        return model

    async def get_default_chat_model(self) -> ChatOpenAI:
        return await self.get_chat_model(None)

    async def get_embedding_model(self, provider_id: str | None = None) -> OpenAIEmbeddings:
        resolved = await self._load(provider_id, embedding=True)
        row = resolved.provider
        key = (row.id, self._version(row), "embedding")
        model = self._embedding_cache.get(key)
        if model is None:
            model = OpenAIEmbeddings(
                model=row.embedding_model or "",
                dimensions=row.embedding_dimensions,
                api_key=SecretStr(resolved.api_key),
                base_url=self.normalize_base_url(row.base_url),
                check_embedding_ctx_length=False,
            )
            self._embedding_cache = {
                cached_key: cached_model
                for cached_key, cached_model in self._embedding_cache.items()
                if cached_key[0] != row.id
            }
            self._embedding_cache[key] = model
        return model

    async def get_default_embedding_model(self) -> OpenAIEmbeddings:
        return await self.get_embedding_model(None)

    async def reload(self) -> None:
        self._chat_cache.clear()
        self._embedding_cache.clear()

    async def _load(self, provider_id: str | None, embedding: bool) -> _Resolved:
        session_factory = self.session_factory
        if session_factory is None:
            from infrastructure.database.connection import async_session_factory
            session_factory = async_session_factory
        async with session_factory() as db:
            settings = await self.repository.get_settings(db)
            if settings is None:
                raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "尚未配置默认 Provider")
            normalized = (provider_id or "").strip()
            if embedding:
                target = settings.default_embedding_provider_id if normalized in {"", "default"} else normalized
            else:
                target = settings.default_chat_provider_id if normalized in {"", "default"} else normalized
            row = await self.repository.get(db, target)
            if row is None:
                raise BusinessException(ErrorCode.LLM_PROVIDER_NOT_FOUND, f"Provider 不存在: {target}")
            if not row.enabled:
                raise BusinessException(ErrorCode.LLM_PROVIDER_DISABLED, f"Provider 已禁用: {target}")
            if embedding and (
                not row.supports_embedding or not row.embedding_model or not row.embedding_dimensions
            ):
                raise BusinessException(
                    ErrorCode.LLM_PROVIDER_CONFIG_ERROR, f"Provider 未配置 Embedding: {target}"
                )
            return _Resolved(row, self.encryption.decrypt(row.api_key_ciphertext, row.api_key_nonce))

    @staticmethod
    def normalize_base_url(value: str) -> str:
        value = value.rstrip("/")
        return value if re.search(r"/v\d+$", value, re.IGNORECASE) else f"{value}/v1"

    @staticmethod
    def _version(row: LlmProviderConfigORM) -> tuple:
        return (
            row.updated_at.isoformat() if row.updated_at else "",
            row.base_url, row.model, row.embedding_model, row.embedding_dimensions,
            row.temperature, row.enabled, row.api_key_ciphertext, row.api_key_nonce,
        )
