import asyncio
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode
from infrastructure.database.models import VoiceProviderConfigORM
from modules.llmprovider.model.llm_provider_dto import (
    AsrConfigDTO,
    AsrConfigRequest,
    ProviderTestResultDTO,
    TtsConfigDTO,
    TtsConfigRequest,
)
from modules.llmprovider.repository.llm_provider_repository import VoiceProviderConfigRepository
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.voiceinterview.speech.dashscope import (
    DashScopeAsrConfig,
    DashScopeAsrProvider,
    DashScopeTtsConfig,
    DashScopeTtsProvider,
)

logger = logging.getLogger(__name__)


class VoiceProviderConfigService:
    def __init__(
        self,
        repository: VoiceProviderConfigRepository,
        encryption: ApiKeyEncryptionService,
        asr_provider: DashScopeAsrProvider,
        tts_provider: DashScopeTtsProvider,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        connection_opener=None,
    ) -> None:
        self.repository = repository
        self.encryption = encryption
        self.asr_provider = asr_provider
        self.tts_provider = tts_provider
        self.session_factory = session_factory
        self.connection_opener = connection_opener or asyncio.open_connection
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        session_factory = self.session_factory
        if session_factory is None:
            from infrastructure.database.connection import async_session_factory

            session_factory = async_session_factory
        async with self._write_lock:
            async with session_factory() as db:
                async with db.begin():
                    config = await self.repository.get(db)
                    if config is None:
                        config = self._bootstrap_config()
                        await self.repository.save(db, config)
                self._apply_runtime_config(config)

    async def get_asr(self, db: AsyncSession) -> AsrConfigDTO:
        config = await self._required(db)
        return AsrConfigDTO(
            url=config.asr_url,
            model=config.asr_model,
            masked_api_key=self._masked_api_key(config),
            language=config.asr_language,
            format=config.asr_format,
            sample_rate=config.asr_sample_rate,
            enable_turn_detection=config.asr_enable_turn_detection,
            turn_detection_type=config.asr_turn_detection_type,
            turn_detection_threshold=config.asr_turn_detection_threshold,
            turn_detection_silence_duration_ms=config.asr_turn_detection_silence_duration_ms,
        )

    async def get_tts(self, db: AsyncSession) -> TtsConfigDTO:
        config = await self._required(db)
        return TtsConfigDTO(
            model=config.tts_model,
            masked_api_key=self._masked_api_key(config),
            voice=config.tts_voice,
            format=config.tts_format,
            sample_rate=config.tts_sample_rate,
            mode=config.tts_mode,
            language_type=config.tts_language_type,
            speech_rate=config.tts_speech_rate,
            volume=config.tts_volume,
        )

    async def update_asr(self, db: AsyncSession, request: AsrConfigRequest) -> None:
        field_map = {
            "url": "asr_url",
            "model": "asr_model",
            "language": "asr_language",
            "format": "asr_format",
            "sample_rate": "asr_sample_rate",
            "enable_turn_detection": "asr_enable_turn_detection",
            "turn_detection_type": "asr_turn_detection_type",
            "turn_detection_threshold": "asr_turn_detection_threshold",
            "turn_detection_silence_duration_ms": "asr_turn_detection_silence_duration_ms",
        }
        await self._update(db, request, field_map)

    async def update_tts(self, db: AsyncSession, request: TtsConfigRequest) -> None:
        field_map = {
            "model": "tts_model",
            "voice": "tts_voice",
            "format": "tts_format",
            "sample_rate": "tts_sample_rate",
            "mode": "tts_mode",
            "language_type": "tts_language_type",
            "speech_rate": "tts_speech_rate",
            "volume": "tts_volume",
        }
        await self._update(db, request, field_map)

    async def test_asr(self, db: AsyncSession) -> ProviderTestResultDTO:
        config = await self._required(db)
        writer = None
        try:
            parsed = urlparse(config.asr_url)
            host = parsed.hostname
            if not host:
                raise ValueError("ASR WebSocket URL does not contain a host")
            port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            _reader, writer = await asyncio.wait_for(
                self.connection_opener(host, port),
                timeout=app_config.voice_external_connect_timeout_seconds,
            )
            return ProviderTestResultDTO(
                success=True,
                message=f"ASR WebSocket 连接成功: {host}",
                model=config.asr_model,
            )
        except Exception as error:
            secret = self._decrypt_api_key(config) or ""
            return ProviderTestResultDTO(
                success=False,
                message=f"ASR 连接失败: {self._safe_error(str(error), secret)}",
                model=config.asr_model,
            )
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    async def _update(self, db: AsyncSession, request, field_map: dict[str, str]) -> None:
        async with self._write_lock:
            config = await self._required(db)
            fields = request.model_fields_set
            for request_name, column_name in field_map.items():
                if request_name in fields:
                    setattr(config, column_name, getattr(request, request_name))
            if "api_key" in fields and request.api_key is not None:
                config.api_key_ciphertext, config.api_key_nonce = self.encryption.encrypt(
                    request.api_key.get_secret_value()
                )
            config.updated_at = datetime.now()
            await db.flush()
            await db.commit()
            self._apply_runtime_config(config)
            logger.info("Updated voice provider configuration")

    async def _required(self, db: AsyncSession) -> VoiceProviderConfigORM:
        config = await self.repository.get(db)
        if config is None:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CONFIG_ERROR,
                "语音 Provider 配置尚未初始化",
            )
        return config

    def _bootstrap_config(self) -> VoiceProviderConfigORM:
        ciphertext = nonce = None
        if app_config.voice_dashscope_api_key and app_config.voice_dashscope_api_key.strip():
            ciphertext, nonce = self.encryption.encrypt(app_config.voice_dashscope_api_key.strip())
        return VoiceProviderConfigORM(
            id=1,
            api_key_ciphertext=ciphertext,
            api_key_nonce=nonce,
            asr_url=app_config.voice_dashscope_realtime_url,
            asr_model=app_config.voice_asr_model,
            asr_language=app_config.voice_asr_language,
            asr_format=app_config.voice_asr_format,
            asr_sample_rate=app_config.voice_asr_sample_rate,
            asr_enable_turn_detection=app_config.voice_asr_enable_turn_detection,
            asr_turn_detection_type=app_config.voice_asr_turn_detection_type,
            asr_turn_detection_threshold=app_config.voice_asr_turn_detection_threshold,
            asr_turn_detection_silence_duration_ms=(
                app_config.voice_asr_turn_detection_silence_duration_ms
            ),
            tts_model=app_config.voice_tts_model,
            tts_voice=app_config.voice_tts_voice,
            tts_format=app_config.voice_tts_format,
            tts_sample_rate=app_config.voice_tts_sample_rate,
            tts_mode=app_config.voice_tts_mode,
            tts_language_type=app_config.voice_tts_language_type,
            tts_speech_rate=app_config.voice_tts_speech_rate,
            tts_volume=app_config.voice_tts_volume,
        )

    def _apply_runtime_config(self, config: VoiceProviderConfigORM) -> None:
        api_key = self._decrypt_api_key(config)
        asr_receive_timeout = self.asr_provider.config.receive_timeout_seconds
        self.asr_provider.config = DashScopeAsrConfig(
            api_key=api_key,
            url=config.asr_url,
            model=config.asr_model,
            language=config.asr_language,
            format=config.asr_format,
            sample_rate=config.asr_sample_rate,
            enable_turn_detection=config.asr_enable_turn_detection,
            turn_detection_type=config.asr_turn_detection_type,
            turn_detection_threshold=config.asr_turn_detection_threshold,
            turn_detection_silence_duration_ms=config.asr_turn_detection_silence_duration_ms,
            connect_timeout_seconds=app_config.voice_external_connect_timeout_seconds,
            receive_timeout_seconds=asr_receive_timeout,
        )
        self.tts_provider.config = DashScopeTtsConfig(
            api_key=api_key,
            url=config.asr_url,
            model=config.tts_model,
            voice=config.tts_voice,
            format=config.tts_format,
            sample_rate=config.tts_sample_rate,
            mode=config.tts_mode,
            language_type=config.tts_language_type,
            speech_rate=config.tts_speech_rate,
            volume=config.tts_volume,
            connect_timeout_seconds=app_config.voice_external_connect_timeout_seconds,
            response_timeout_seconds=app_config.voice_tts_timeout_seconds,
        )

    def _masked_api_key(self, config: VoiceProviderConfigORM) -> str:
        secret = self._decrypt_api_key(config)
        return self.encryption.mask(secret) if secret else "***"

    def _decrypt_api_key(self, config: VoiceProviderConfigORM) -> str | None:
        if config.api_key_ciphertext is None and config.api_key_nonce is None:
            return None
        if not config.api_key_ciphertext or not config.api_key_nonce:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CRYPTO_ERROR,
                "语音 Provider API Key 密文不完整",
            )
        return self.encryption.decrypt(config.api_key_ciphertext, config.api_key_nonce)

    @staticmethod
    def _safe_error(message: str, secret: str) -> str:
        if secret:
            message = message.replace(secret, "***")
        message = re.sub(r"(?i)(api[-_ ]?key[=: ]+)[^\s,;]+", r"\1***", message)
        return re.sub(r"\s+", " ", message).strip()[:300] or "连接失败"
