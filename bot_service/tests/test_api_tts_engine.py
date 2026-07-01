from unittest.mock import AsyncMock, patch


def _csrf_headers(authenticated_client):
    warmup = authenticated_client.get("/api/tts/status")
    assert warmup.status_code == 200
    token = authenticated_client.cookies.get("csrf_token")
    assert token
    return {"X-CSRF-Token": token}


def test_set_engine_gcloud(authenticated_client):
    headers = _csrf_headers(authenticated_client)
    with patch(
        "services.tts.tts_service.TTSService.save_tts_settings",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.return_value = {"success": True, "version": 2}
        response = authenticated_client.post(
            "/api/tts/engine",
            json={"engine_type": "gcloud"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["engine_type"] == "gcloud"
    kwargs = mock_save.await_args.kwargs
    assert kwargs["engine"] == "gcloud"
    assert kwargs["advanced_provider"] == "gcloud"
    assert kwargs["use_local_tts"] is False


def test_set_engine_alias_cloud_maps_to_f5_cloud(authenticated_client):
    headers = _csrf_headers(authenticated_client)
    with patch(
        "services.tts.tts_service.TTSService.save_tts_settings",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.return_value = {"success": True, "version": 2}
        response = authenticated_client.post(
            "/api/tts/engine",
            json={"engine_type": "cloud"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["engine_type"] == "f5_cloud"
    kwargs = mock_save.await_args.kwargs
    assert kwargs["engine"] == "f5tts"
    assert kwargs["advanced_provider"] == "f5"
    assert kwargs["f5_mode"] == "cloud"
    assert kwargs["use_local_tts"] is False


def test_set_engine_f5_local(authenticated_client):
    headers = _csrf_headers(authenticated_client)
    with patch(
        "services.tts.tts_service.TTSService.save_tts_settings",
        new_callable=AsyncMock,
    ) as mock_save:
        mock_save.return_value = {"success": True, "version": 2}
        response = authenticated_client.post(
            "/api/tts/engine",
            json={"engine_type": "f5_local"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["engine_type"] == "f5_local"
    kwargs = mock_save.await_args.kwargs
    assert kwargs["engine"] == "f5tts"
    assert kwargs["advanced_provider"] == "f5"
    assert kwargs["f5_mode"] == "local"
    assert kwargs["use_local_tts"] is True


def test_set_engine_invalid_value(authenticated_client):
    headers = _csrf_headers(authenticated_client)
    response = authenticated_client.post(
        "/api/tts/engine",
        json={"engine_type": "invalid_engine"},
        headers=headers,
    )
    assert response.status_code == 400
