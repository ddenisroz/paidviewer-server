from auth.auth import verify_jwt_token


def test_tts_obs_links_create_dedicated_tokens(authenticated_client, test_user):
    response = authenticated_client.get("/api/tts/obs-links")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dock_token"]
    assert payload["source_token"]
    assert payload["dock_token"] != payload["source_token"]
    assert "/tts/obs-dock?dock_token=" in payload["dock_url"]
    assert "/tts-obs/" in payload["source_url"]

    dock_payload = verify_jwt_token(payload["dock_token"], expected_type="tts_dock")
    source_payload = verify_jwt_token(payload["source_token"], expected_type="tts_source")

    assert dock_payload["user_id"] == test_user.id
    assert dock_payload["scope"] == "tts_dock"
    assert source_payload["user_id"] == test_user.id
    assert source_payload["scope"] == "tts_source"


def test_tts_obs_links_regenerate_source_only(authenticated_client):
    first = authenticated_client.get("/api/tts/obs-links").json()
    response = authenticated_client.post(
        "/api/tts/obs-links/regenerate",
        json={"target": "source"},
    )

    assert response.status_code == 200
    second = response.json()
    assert second["dock_token"] == first["dock_token"]
    assert second["source_token"] != first["source_token"]


def test_youtube_obs_url_returns_stable_url(authenticated_client, test_user):
    first = authenticated_client.get("/api/youtube/obs-url")
    second = authenticated_client.get("/api/youtube/obs-url")

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()

    assert first_payload["obs_token"]
    assert first_payload["obs_token"] == second_payload["obs_token"]
    assert first_payload["youtube_obs_url"].endswith(first_payload["obs_token"])

    token_payload = verify_jwt_token(first_payload["obs_token"])
    assert token_payload["user_id"] == test_user.id
