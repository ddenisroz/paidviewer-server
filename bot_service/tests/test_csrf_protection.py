"""CSRF middleware regression tests."""

from fastapi.testclient import TestClient


def test_state_change_requires_csrf_header(authenticated_client: TestClient):
    # Remove header added by fixture to emulate broken client.
    authenticated_client.headers.pop("X-CSRF-Token", None)

    response = authenticated_client.post("/api/auth/logout")
    assert response.status_code == 403
    assert response.json().get("detail") == "CSRF token validation failed"


def test_state_change_succeeds_with_csrf_header(authenticated_client: TestClient):
    response = authenticated_client.post("/api/auth/logout")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("success") is True
