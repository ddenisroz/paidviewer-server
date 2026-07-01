import pytest


def test_add_video_route_returns_exact_service_error(authenticated_client, monkeypatch):
    async def _fake_add(**_kwargs):
        return {
            "success": False,
            "error": "This video is already in the queue. Choose another one.",
        }

    monkeypatch.setattr("api.youtube.routes.queue_service.add_video_to_user_queue", _fake_add)

    response = authenticated_client.post(
        "/api/youtube/queue/add",
        json={"video_url": "duplicate query"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "This video is already in the queue. Choose another one."


def test_add_video_route_passes_raw_input_to_service(authenticated_client, monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_add(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "queue_item": {
                "id": 1,
                "title": "Test",
                "duration": "3:45",
                "position": 1,
                "requester_name": "test_user",
                "requester": "test_user",
                "is_paid": False,
                "points_cost": None,
                "paid_source": None,
                "paid_amount": None,
                "paid_currency": None,
                "source_alert_id": None,
            },
        }

    monkeypatch.setattr("api.youtube.routes.queue_service.add_video_to_user_queue", _fake_add)

    response = authenticated_client.post(
        "/api/youtube/queue/add",
        json={"video_url": "weird search query"},
    )

    assert response.status_code == 200
    assert captured["video_url"] == "weird search query"
    assert captured["platform"] == "web"
    assert captured["channel_name"] == "web_interface"
