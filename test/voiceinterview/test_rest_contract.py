import pytest
from starlette.requests import Request

from common.exceptions import BusinessException
from modules.voiceinterview.model.voice_interview_dto import (
    CreateVoiceInterviewRequest, VoiceEvaluationDetailDTO,
)
from modules.voiceinterview.router.rest_router import _web_socket_template, router


def test_create_request_normalizes_reserved_user_id():
    assert CreateVoiceInterviewRequest().user_id == "default"
    assert CreateVoiceInterviewRequest(userId=None).user_id == "default"
    assert CreateVoiceInterviewRequest(userId="   ").user_id == "default"
    assert CreateVoiceInterviewRequest(userId="future-user").user_id == "future-user"


def test_router_exposes_java_compatible_session_endpoints():
    route_keys = {(method, route.path) for route in router.routes for method in route.methods}
    expected = {
        ("POST", "/api/voice-interview/sessions"),
        ("GET", "/api/voice-interview/sessions"),
        ("GET", "/api/voice-interview/sessions/{session_id}"),
        ("PUT", "/api/voice-interview/sessions/{session_id}/pause"),
        ("PUT", "/api/voice-interview/sessions/{session_id}/resume"),
        ("POST", "/api/voice-interview/sessions/{session_id}/end"),
        ("DELETE", "/api/voice-interview/sessions/{session_id}"),
        ("GET", "/api/voice-interview/sessions/{session_id}/messages"),
        ("GET", "/api/voice-interview/sessions/{session_id}/evaluation"),
        ("POST", "/api/voice-interview/sessions/{session_id}/evaluation"),
    }
    assert expected <= route_keys


def test_evaluation_detail_keeps_frontend_answers_shape():
    detail = VoiceEvaluationDetailDTO(
        sessionId=7, totalQuestions=1, answers=[{"questionIndex": 0, "score": 90}]
    )
    dumped = detail.model_dump()
    assert dumped["sessionId"] == 7
    assert dumped["totalQuestions"] == 1
    assert dumped["answers"][0]["questionIndex"] == 0


def test_websocket_url_rejects_untrusted_host():
    request = Request({
        "type": "http", "method": "POST", "scheme": "http", "path": "/",
        "query_string": b"", "headers": [(b"host", b"evil.example.com")],
        "server": ("evil.example.com", 80),
    })
    with pytest.raises(BusinessException, match="Untrusted Host"):
        _web_socket_template(request)
