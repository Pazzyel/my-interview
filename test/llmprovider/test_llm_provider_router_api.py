import importlib
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.llmprovider.model.llm_provider_dto import (
    AsrConfigDTO,
    DefaultProviderDTO,
    LlmProviderDTO,
    TtsConfigDTO,
)


class FakeProviderService:
    def __init__(self):
        self.provider = LlmProviderDTO(
            id="demo", baseUrl="https://example.com", maskedApiKey="sec***ret",
            model="chat", supportsEmbedding=True, embeddingModel="embed",
            embeddingDimensions=1024, temperature=0, enabled=True, builtin=False,
            defaultChatProvider=True, defaultEmbeddingProvider=True,
        )

    async def list(self, _db): return [self.provider]
    async def get(self, _db, _id): return self.provider
    async def create(self, _db, _request): return self.provider
    async def update(self, _db, _id, _request): return self.provider
    async def delete(self, _db, _id): return None
    async def test(self, _db, _id):
        return {"success": True, "message": "连接成功", "model": "chat"}
    async def reload(self): return None
    async def defaults(self, _db):
        return DefaultProviderDTO(defaultProvider="demo", defaultEmbeddingProvider="demo")
    async def set_default_chat(self, _db, provider_id):
        return DefaultProviderDTO(defaultProvider=provider_id, defaultEmbeddingProvider="demo")
    async def set_default_embedding(self, _db, provider_id):
        return DefaultProviderDTO(defaultProvider="demo", defaultEmbeddingProvider=provider_id)


fake_service = FakeProviderService()


class FakeVoiceProviderConfigService:
    def __init__(self):
        self.asr = AsrConfigDTO(
            url="wss://voice.example/realtime", model="asr-model", maskedApiKey="sec***ret",
            language="zh", format="pcm", sampleRate=16000, enableTurnDetection=True,
            turnDetectionType="server_vad", turnDetectionThreshold=0.2,
            turnDetectionSilenceDurationMs=800,
        )
        self.tts = TtsConfigDTO(
            model="tts-model", maskedApiKey="sec***ret", voice="Cherry", format="pcm",
            sampleRate=24000, mode="commit", languageType="Chinese", speechRate=1.0,
            volume=60,
        )

    async def get_asr(self, _db): return self.asr
    async def get_tts(self, _db): return self.tts
    async def update_asr(self, _db, request): self.asr.model = request.model or self.asr.model
    async def update_tts(self, _db, request): self.tts.voice = request.voice or self.tts.voice
    async def test_asr(self, _db):
        return {"success": True, "message": "连接成功", "model": self.asr.model}


fake_voice_service = FakeVoiceProviderConfigService()
previous_dependencies = sys.modules.get("common.dependencies")
sys.modules["common.dependencies"] = SimpleNamespace(
    llm_provider_service=fake_service,
    voice_provider_config_service=fake_voice_service,
)
router_module = importlib.import_module("modules.llmprovider.router.llm_provider_router")
if previous_dependencies is None:
    sys.modules.pop("common.dependencies", None)
else:
    sys.modules["common.dependencies"] = previous_dependencies

app = FastAPI()
app.include_router(router_module.router)


async def fake_db():
    yield object()


app.dependency_overrides[router_module.get_async_session] = fake_db
client = TestClient(app)


def test_static_routes_are_not_captured_by_provider_id():
    response = client.get("/api/llm-provider/default-provider")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "defaultProvider": "demo", "defaultEmbeddingProvider": "demo"
    }
    assert client.post("/api/llm-provider/reload").status_code == 200


def test_list_and_get_use_result_wrapper_and_camel_case():
    payload = client.get("/api/llm-provider/list").json()
    assert payload["code"] == 200
    assert payload["data"][0]["maskedApiKey"] == "sec***ret"
    assert "masked_api_key" not in payload["data"][0]
    assert client.get("/api/llm-provider/demo").status_code == 200


def test_crud_test_and_default_endpoints_have_no_auth_requirement():
    create = client.post("/api/llm-provider", json={
        "id": "new", "baseUrl": "https://example.com", "apiKey": "secret", "model": "chat"
    })
    assert create.status_code == 200
    assert client.put("/api/llm-provider/demo", json={"temperature": 0.2}).status_code == 200
    assert client.post("/api/llm-provider/demo/test").json()["data"]["success"] is True
    assert client.delete("/api/llm-provider/demo").status_code == 200
    defaults = {"defaultProvider": "demo", "defaultEmbeddingProvider": "demo"}
    assert client.put("/api/llm-provider/default-provider", json=defaults).status_code == 200
    assert client.put("/api/llm-provider/default-embedding-provider", json=defaults).status_code == 200


def test_voice_settings_endpoints_match_frontend_contract():
    asr = client.get("/api/llm-provider/voice/asr")
    assert asr.status_code == 200
    assert asr.json()["data"] == {
        "url": "wss://voice.example/realtime", "model": "asr-model",
        "maskedApiKey": "sec***ret", "language": "zh", "format": "pcm",
        "sampleRate": 16000, "enableTurnDetection": True,
        "turnDetectionType": "server_vad", "turnDetectionThreshold": 0.2,
        "turnDetectionSilenceDurationMs": 800,
    }
    tts = client.get("/api/llm-provider/voice/tts")
    assert tts.status_code == 200
    assert tts.json()["data"]["languageType"] == "Chinese"
    assert tts.json()["data"]["speechRate"] == 1.0
    assert client.put("/api/llm-provider/voice/asr", json={"model": "asr-new"}).json()["data"] is None
    assert client.put("/api/llm-provider/voice/tts", json={"voice": "Serena"}).json()["data"] is None
    tested = client.post("/api/llm-provider/voice/asr/test")
    assert tested.status_code == 200
    assert tested.json()["data"]["success"] is True
    assert client.get("/api/llm-provider/voice/asr").status_code == 200
