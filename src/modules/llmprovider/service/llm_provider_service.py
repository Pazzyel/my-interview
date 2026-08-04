import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import LlmGlobalSettingORM, LlmProviderConfigORM
from modules.llmprovider.model.llm_provider_dto import (
    DefaultProviderDTO,
    LlmProviderCreateRequest,
    LlmProviderDTO,
    LlmProviderUpdateRequest,
    ProviderTestResultDTO,
    PROVIDER_ID_PATTERN,
)
from modules.llmprovider.repository.llm_provider_repository import LlmProviderRepository
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service.llm_provider_registry import LlmProviderRegistry

logger = logging.getLogger(__name__)


class LlmProviderService:
    def __init__(
        self,
        repository: LlmProviderRepository,
        encryption: ApiKeyEncryptionService,
        registry: LlmProviderRegistry,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.repository = repository
        self.encryption = encryption
        self.registry = registry
        self.session_factory = session_factory

    async def initialize(self) -> None:
        """Validate crypto and bootstrap an empty provider database atomically."""
        self.encryption.validate_ready()
        session_factory = self.session_factory
        if session_factory is None:
            from infrastructure.database.connection import async_session_factory
            session_factory = async_session_factory
        async with session_factory() as db:
            async with db.begin():
                if await self.repository.count(db) == 0:
                    await self._bootstrap_empty_database(db)
                else:
                    await self._repair_missing_settings(db)
                await self._validate_global_settings(db)
                # Wrong or lost master keys must fail fast, before any worker starts.
                for provider in await self.repository.list(db):
                    self.encryption.decrypt(provider.api_key_ciphertext, provider.api_key_nonce)
        await self.registry.reload()

    async def list(self, db: AsyncSession) -> list[LlmProviderDTO]:
        settings = await self.repository.get_settings(db)
        return [self._to_dto(row, settings) for row in await self.repository.list(db)]

    async def get(self, db: AsyncSession, provider_id: str) -> LlmProviderDTO:
        row = await self._required(db, provider_id)
        return self._to_dto(row, await self.repository.get_settings(db))

    async def create(self, db: AsyncSession, request: LlmProviderCreateRequest) -> LlmProviderDTO:
        if await self.repository.get(db, request.id):
            raise BusinessException(ErrorCode.BAD_REQUEST, f"Provider 已存在: {request.id}")
        self._validate_url(request.base_url)
        ciphertext, nonce = self.encryption.encrypt(request.api_key.get_secret_value())
        row = LlmProviderConfigORM(
            id=request.id,
            base_url=request.base_url.rstrip("/"),
            api_key_ciphertext=ciphertext,
            api_key_nonce=nonce,
            model=request.model,
            embedding_model=request.embedding_model,
            embedding_dimensions=request.embedding_dimensions,
            supports_embedding=request.supports_embedding,
            temperature=request.temperature,
            enabled=request.enabled,
            builtin=False,
        )
        await self.repository.add(db, row)
        await db.commit()
        await self.registry.reload()
        return self._to_dto(row, await self.repository.get_settings(db))

    async def update(
        self, db: AsyncSession, provider_id: str, request: LlmProviderUpdateRequest
    ) -> LlmProviderDTO:
        row = await self._required(db, provider_id)
        fields = request.model_fields_set
        if "base_url" in fields:
            if not request.base_url or not request.base_url.strip():
                raise BusinessException(ErrorCode.BAD_REQUEST, "baseUrl 不能为空")
            self._validate_url(request.base_url)
            row.base_url = request.base_url.rstrip("/")
        if "model" in fields:
            if not request.model or not request.model.strip():
                raise BusinessException(ErrorCode.BAD_REQUEST, "model 不能为空")
            row.model = request.model.strip()
        if "api_key" in fields and request.api_key is not None:
            api_key = request.api_key.get_secret_value().strip()
            if not api_key:
                raise BusinessException(ErrorCode.BAD_REQUEST, "apiKey 不能为空")
            row.api_key_ciphertext, row.api_key_nonce = self.encryption.encrypt(api_key)
        for name in ("embedding_model", "embedding_dimensions", "supports_embedding", "temperature", "enabled"):
            if name in fields:
                setattr(row, name, getattr(request, name))
        self._validate_embedding(row.supports_embedding, row.embedding_model, row.embedding_dimensions)
        row.updated_at = datetime.now()
        await db.flush()
        await db.commit()
        await self.registry.reload()
        return self._to_dto(row, await self.repository.get_settings(db))

    async def delete(self, db: AsyncSession, provider_id: str) -> None:
        row = await self._required(db, provider_id)
        settings = await self._required_settings(db)
        if provider_id in {
            settings.default_chat_provider_id,
            settings.default_embedding_provider_id,
        }:
            raise BusinessException(ErrorCode.BAD_REQUEST, "默认 Provider 不允许删除，请先切换默认项")
        await self.repository.delete(db, row)
        await db.commit()
        await self.registry.reload()

    async def defaults(self, db: AsyncSession) -> DefaultProviderDTO:
        settings = await self._required_settings(db)
        return DefaultProviderDTO(
            default_provider=settings.default_chat_provider_id,
            default_embedding_provider=settings.default_embedding_provider_id,
        )

    async def set_default_chat(self, db: AsyncSession, provider_id: str) -> DefaultProviderDTO:
        row = await self._required(db, provider_id)
        if not row.enabled:
            raise BusinessException(ErrorCode.LLM_PROVIDER_DISABLED, f"Provider 已禁用: {provider_id}")
        settings = await self._required_settings(db)
        settings.default_chat_provider_id = provider_id
        settings.updated_at = datetime.now()
        await db.commit()
        await self.registry.reload()
        return await self.defaults(db)

    async def set_default_embedding(self, db: AsyncSession, provider_id: str) -> DefaultProviderDTO:
        row = await self._required(db, provider_id)
        if not row.enabled:
            raise BusinessException(ErrorCode.LLM_PROVIDER_DISABLED, f"Provider 已禁用: {provider_id}")
        self._validate_embedding(row.supports_embedding, row.embedding_model, row.embedding_dimensions)
        settings = await self._required_settings(db)
        settings.default_embedding_provider_id = provider_id
        settings.updated_at = datetime.now()
        await db.commit()
        await self.registry.reload()
        return await self.defaults(db)

    async def test(self, db: AsyncSession, provider_id: str) -> ProviderTestResultDTO:
        row = await self._required(db, provider_id)
        secret = self.encryption.decrypt(row.api_key_ciphertext, row.api_key_nonce)
        try:
            from langchain_openai import ChatOpenAI
            from pydantic import SecretStr

            model = ChatOpenAI(
                model=row.model,
                api_key=SecretStr(secret),
                base_url=self.registry.normalize_base_url(row.base_url),
                temperature=0,
                request_timeout=10,
                max_retries=0,
            )
            await model.ainvoke("Reply with OK only.")
            return ProviderTestResultDTO(success=True, message="连接成功", model=row.model)
        except Exception as error:
            message = self._safe_error(str(error), secret)
            return ProviderTestResultDTO(success=False, message=message, model=row.model)

    async def reload(self) -> None:
        await self.registry.reload()

    async def _bootstrap_empty_database(self, db: AsyncSession) -> None:
        raw = app_config.llm_provider_bootstrap_json
        if not raw:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CONFIG_ERROR,
                "Provider 表为空且未配置 LLM_PROVIDER_BOOTSTRAP_JSON",
            )
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not payload:
                raise ValueError("root must be a non-empty object")
            requests = [LlmProviderCreateRequest.model_validate({"id": key, **value}) for key, value in payload.items()]
        except Exception as error:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "LLM_PROVIDER_BOOTSTRAP_JSON 格式无效"
            ) from error
        chat_id = app_config.llm_default_chat_provider
        embedding_id = app_config.llm_default_embedding_provider
        ids = {item.id for item in requests}
        if not chat_id or not embedding_id or chat_id not in ids or embedding_id not in ids:
            raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "Bootstrap 默认 Provider ID 无效")
        embedding_request = next(item for item in requests if item.id == embedding_id)
        chat_request = next(item for item in requests if item.id == chat_id)
        if not chat_request.enabled or not embedding_request.enabled:
            raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "Bootstrap 默认 Provider 必须启用")
        self._validate_embedding(
            embedding_request.supports_embedding,
            embedding_request.embedding_model,
            embedding_request.embedding_dimensions,
        )
        for request in requests:
            ciphertext, nonce = self.encryption.encrypt(request.api_key.get_secret_value())
            await self.repository.add(db, LlmProviderConfigORM(
                id=request.id, base_url=request.base_url.rstrip("/"),
                api_key_ciphertext=ciphertext, api_key_nonce=nonce, model=request.model,
                embedding_model=request.embedding_model,
                embedding_dimensions=request.embedding_dimensions,
                supports_embedding=request.supports_embedding, temperature=request.temperature,
                enabled=request.enabled, builtin=True,
            ))
        await self.repository.save_settings(db, LlmGlobalSettingORM(
            id=1, default_chat_provider_id=chat_id,
            default_embedding_provider_id=embedding_id,
        ))

    async def _repair_missing_settings(self, db: AsyncSession) -> None:
        if await self.repository.get_settings(db):
            return
        chat_id = app_config.llm_default_chat_provider
        embedding_id = app_config.llm_default_embedding_provider
        chat = await self.repository.get(db, chat_id or "")
        embedding = await self.repository.get(db, embedding_id or "")
        if not chat or not embedding:
            raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "全局默认 Provider 配置缺失或无效")
        self._validate_embedding(embedding.supports_embedding, embedding.embedding_model, embedding.embedding_dimensions)
        await self.repository.save_settings(db, LlmGlobalSettingORM(
            id=1, default_chat_provider_id=chat.id,
            default_embedding_provider_id=embedding.id,
        ))

    async def _validate_global_settings(self, db: AsyncSession) -> None:
        settings = await self._required_settings(db)
        chat = await self.repository.get(db, settings.default_chat_provider_id)
        embedding = await self.repository.get(db, settings.default_embedding_provider_id)
        if not chat or not embedding or not chat.enabled or not embedding.enabled:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CONFIG_ERROR,
                "全局默认 Provider 必须存在且启用",
            )
        if (
            not embedding.supports_embedding
            or not embedding.embedding_model
            or not embedding.embedding_dimensions
            or embedding.embedding_dimensions <= 0
        ):
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CONFIG_ERROR,
                "默认 Embedding Provider 配置无效",
            )

    async def _required(self, db: AsyncSession, provider_id: str) -> LlmProviderConfigORM:
        if not PROVIDER_ID_PATTERN.fullmatch(provider_id):
            raise BusinessException(ErrorCode.BAD_REQUEST, "Provider ID 格式无效")
        row = await self.repository.get(db, provider_id)
        if row is None:
            raise BusinessException(ErrorCode.LLM_PROVIDER_NOT_FOUND, f"Provider 不存在: {provider_id}")
        return row

    async def _required_settings(self, db: AsyncSession) -> LlmGlobalSettingORM:
        settings = await self.repository.get_settings(db)
        if settings is None:
            raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "尚未配置默认 Provider")
        return settings

    def _to_dto(self, row: LlmProviderConfigORM, settings: LlmGlobalSettingORM | None) -> LlmProviderDTO:
        secret = self.encryption.decrypt(row.api_key_ciphertext, row.api_key_nonce)
        return LlmProviderDTO(
            id=row.id, base_url=row.base_url, masked_api_key=self.encryption.mask(secret),
            model=row.model, embedding_model=row.embedding_model,
            embedding_dimensions=row.embedding_dimensions,
            supports_embedding=row.supports_embedding, temperature=row.temperature,
            enabled=row.enabled, builtin=row.builtin,
            default_chat_provider=bool(settings and settings.default_chat_provider_id == row.id),
            default_embedding_provider=bool(settings and settings.default_embedding_provider_id == row.id),
        )

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise BusinessException(ErrorCode.BAD_REQUEST, "baseUrl 必须是有效的 HTTP(S) URL")

    @staticmethod
    def _validate_embedding(supported: bool, model: str | None, dimensions: int | None) -> None:
        if supported and (not model or not model.strip() or not dimensions or dimensions <= 0):
            raise BusinessException(
                ErrorCode.BAD_REQUEST,
                "supportsEmbedding=true 时必须配置 embeddingModel 和正整数 embeddingDimensions",
            )

    @staticmethod
    def _safe_error(message: str, secret: str) -> str:
        if secret:
            message = message.replace(secret, "***")
        message = re.sub(r"(?i)(api[-_ ]?key[=: ]+)[^\s,;]+", r"\1***", message)
        return re.sub(r"\s+", " ", message).strip()[:300] or "连接失败"
