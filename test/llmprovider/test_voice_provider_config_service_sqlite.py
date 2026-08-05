import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.config import app_config
from infrastructure.database.models import Base, VoiceProviderConfigORM
from modules.llmprovider.model.llm_provider_dto import AsrConfigRequest, TtsConfigRequest
from modules.llmprovider.repository.llm_provider_repository import VoiceProviderConfigRepository
from modules.llmprovider.service.api_key_encryption_service import ApiKeyEncryptionService
from modules.llmprovider.service.voice_provider_config_service import VoiceProviderConfigService
from modules.voiceinterview.speech.dashscope import (
    DashScopeAsrConfig,
    DashScopeAsrProvider,
    DashScopeTtsConfig,
    DashScopeTtsProvider,
)


class FakeWriter:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


async def build_service(tmp_path, connection_opener=None):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'voice-provider.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection, tables=[VoiceProviderConfigORM.__table__]
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    asr = DashScopeAsrProvider(DashScopeAsrConfig())
    tts = DashScopeTtsProvider(DashScopeTtsConfig())
    service = VoiceProviderConfigService(
        VoiceProviderConfigRepository(),
        ApiKeyEncryptionService("voice-test-key"),
        asr,
        tts,
        factory,
        connection_opener=connection_opener,
    )
    return engine, factory, service, asr, tts


def test_bootstrap_persistence_partial_updates_and_runtime_reload(tmp_path, monkeypatch):
    async def scenario():
        monkeypatch.setattr(app_config, "voice_dashscope_api_key", "bootstrap-secret")
        monkeypatch.setattr(app_config, "voice_asr_model", "env-asr")
        engine, factory, service, asr, tts = await build_service(tmp_path)
        await service.initialize()
        assert asr.config.model == "env-asr"
        assert asr.config.api_key == "bootstrap-secret"

        async with factory() as db:
            await service.update_asr(db, AsrConfigRequest(
                model="db-asr", apiKey="changed-secret", turnDetectionThreshold=0.4
            ))
        assert asr.config.model == "db-asr"
        assert asr.config.turn_detection_threshold == 0.4
        assert tts.config.api_key == "changed-secret"

        async with factory() as db:
            await service.update_tts(db, TtsConfigRequest(voice="Serena", volume=72))
            asr_dto = await service.get_asr(db)
            tts_dto = await service.get_tts(db)
        assert asr_dto.masked_api_key == "cha***ret"
        assert tts_dto.masked_api_key == "cha***ret"
        assert asr_dto.model == "db-asr"
        assert tts_dto.voice == "Serena"
        assert tts.config.volume == 72

        monkeypatch.setattr(app_config, "voice_asr_model", "ignored-env-change")
        restarted_asr = DashScopeAsrProvider(DashScopeAsrConfig())
        restarted_tts = DashScopeTtsProvider(DashScopeTtsConfig())
        restarted = VoiceProviderConfigService(
            VoiceProviderConfigRepository(), ApiKeyEncryptionService("voice-test-key"),
            restarted_asr, restarted_tts, factory,
        )
        await restarted.initialize()
        assert restarted_asr.config.model == "db-asr"
        assert restarted_tts.config.voice == "Serena"
        assert restarted_tts.config.api_key == "changed-secret"
        await engine.dispose()

    asyncio.run(scenario())


def test_asr_connectivity_test_returns_result_for_success_and_failure(tmp_path, monkeypatch):
    async def scenario():
        writer = FakeWriter()

        async def success_opener(host, port):
            assert host == "dashscope.aliyuncs.com"
            assert port == 443
            return object(), writer

        monkeypatch.setattr(app_config, "voice_dashscope_api_key", None)
        engine, factory, service, _asr, _tts = await build_service(tmp_path, success_opener)
        await service.initialize()
        async with factory() as db:
            success = await service.test_asr(db)
        assert success.success is True
        assert writer.closed is True

        async def failed_opener(_host, _port):
            raise TimeoutError("api_key=should-not-leak")

        service.connection_opener = failed_opener
        async with factory() as db:
            failed = await service.test_asr(db)
        assert failed.success is False
        assert "should-not-leak" not in failed.message
        assert "api_key=***" in failed.message
        await engine.dispose()

    asyncio.run(scenario())
