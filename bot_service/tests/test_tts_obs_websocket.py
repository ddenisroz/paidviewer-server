from auth.auth import create_jwt_token
from api import websocket_endpoints


def _override_get_db(db):
    def _get_db():
        yield db

    return _get_db


def test_tts_obs_dock_relays_control_commands_to_source(client, db, test_user, monkeypatch):
    dock_token = create_jwt_token(test_user.id, token_type="tts_dock")
    source_token = create_jwt_token(test_user.id, token_type="tts_source")

    test_user.tts_dock_token = dock_token
    test_user.tts_source_token = source_token
    db.add(test_user)
    db.commit()

    monkeypatch.setattr(websocket_endpoints, "get_db", _override_get_db(db))

    with client.websocket_connect(f"/ws/tts/{source_token}") as source_socket:
        with client.websocket_connect(f"/ws/tts-dock/{dock_token}") as dock_socket:
            assert dock_socket.receive_json() == {
                "type": "tts_dock_state",
                "data": {"user_id": test_user.id},
            }

            dock_socket.send_json({"type": "tts_control", "command": "skip"})

            assert dock_socket.receive_json() == {
                "type": "tts_control_ack",
                "command": "skip",
                "relayed": True,
            }
            assert source_socket.receive_json() == {
                "type": "tts_control",
                "command": "skip",
            }
