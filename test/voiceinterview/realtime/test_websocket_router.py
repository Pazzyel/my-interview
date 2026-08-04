from modules.voiceinterview.router.websocket_router import create_websocket_router


def test_router_factory_exposes_java_compatible_path() -> None:
    router = create_websocket_router(object())
    assert [route.path for route in router.routes] == ["/ws/voice-interview/{session_id}"]
