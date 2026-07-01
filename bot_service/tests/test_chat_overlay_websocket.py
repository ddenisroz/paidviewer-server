import pytest
from starlette.websockets import WebSocketDisconnect

from api import websocket_endpoints
from models import ChatBoxSettings
from services.memory_websocket_manager import get_memory_websocket_manager


def _override_get_db(db):
    def _get_db():
        yield db

    return _get_db


def test_chat_overlay_websocket_accepts_widget_token_without_session(client, db, test_user, monkeypatch):
    user_id = test_user.id
    db.add(ChatBoxSettings(user_id=user_id, widget_token="overlay-token"))
    db.commit()
    monkeypatch.setattr(websocket_endpoints, "get_db", _override_get_db(db))

    manager = get_memory_websocket_manager()
    with client.websocket_connect("/ws/chat-overlay/overlay-token") as websocket:
        assert manager.has_user_connection_for_role(user_id, "overlay")
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}


def test_chat_overlay_websocket_rejects_invalid_token(client, db, monkeypatch):
    monkeypatch.setattr(websocket_endpoints, "get_db", _override_get_db(db))

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/chat-overlay/not-found"):
            pass

    assert exc_info.value.code == 4401


def test_legacy_widgets_api_is_disabled(client):
    response = client.get("/api/widgets/chat/config/legacy")

    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "legacy_widgets_disabled"
