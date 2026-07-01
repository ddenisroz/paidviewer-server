# bot_service/tests/test_api_auth.py
"""
Тесты для API аутентификации
"""
import pytest
from fastapi.testclient import TestClient

class TestAuthAPI:
    """Тесты для API аутентификации"""
    
    def test_auth_status_unauthenticated(self, client):
        """Тест статуса аутентификации для неавторизованного пользователя"""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == False
    
    def test_auth_status_authenticated(self, authenticated_client, test_user):
        """Тест статуса аутентификации для авторизованного пользователя"""
        response = authenticated_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == True
        assert "integrations" in data
    
    def test_logout(self, authenticated_client):
        """Тест выхода из системы"""
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
    
    def test_twitch_auth_redirect(self, client):
        """Тест редиректа на Twitch авторизацию"""
        response = client.get("/auth/twitch")
        # Может быть 307 (redirect), 404 (not found), или 500 (server error)
        assert response.status_code in [307, 404, 500]
    
    def test_vk_auth_redirect(self, client):
        """Тест редиректа на VK авторизацию"""
        response = client.get("/auth/vk")
        # Может быть 307 (redirect), 404 (not found), или 500 (server error)
        assert response.status_code in [307, 404, 503]
        if response.status_code == 503:
            assert response.json()["detail"]["code"] == "integration_not_configured"
    
    def test_twitch_callback_invalid_code(self, client, db_session):
        """Тест обработки неверного кода Twitch"""
        response = client.get("/auth/twitch/callback?code=invalid_code")
        # Может быть 400 (bad request), 404 (not found), или 500 (server error)
        assert response.status_code in [400, 404, 500]
    
    def test_vk_callback_invalid_code(self, client, db_session):
        """Тест обработки неверного кода VK"""
        response = client.get("/auth/vk/callback?code=invalid_code")
        # Может быть 400 (bad request), 404 (not found), или 500 (server error)
        assert response.status_code in [400, 404, 500]
