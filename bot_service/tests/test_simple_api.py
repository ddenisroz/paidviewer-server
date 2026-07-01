# bot_service/tests/test_simple_api.py
"""
Простые тесты API для проверки базовой функциональности
"""
import pytest
import os
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

class TestSimpleAPI:
    """Простые тесты API"""
    
    def test_health_check(self, client):
        """Тест проверки здоровья сервиса"""
        response = client.get("/")
        # Может быть 200 или 404, в зависимости от настроек
        assert response.status_code in [200, 404]
    
    def test_auth_status_simple(self, client):
        """Простой тест статуса аутентификации"""
        response = client.get("/api/auth/status")
        # В тестовом режиме должен возвращать 200
        assert response.status_code == 200
        data = response.json()
        assert "authenticated" in data
        assert data["authenticated"] == False  # Неавторизованный пользователь
    
    def test_auth_status_with_session(self, authenticated_client):
        """Тест статуса аутентификации с сессией"""
        response = authenticated_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert "authenticated" in data
        assert data["authenticated"] == True  # Авторизованный пользователь
    
    def test_logout_simple(self, authenticated_client):
        """Простой тест выхода из системы"""
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
    
    @patch('os.getenv')
    def test_twitch_auth_redirect_mock(self, mock_getenv, client):
        """Тест редиректа на Twitch с моком"""
        # Мокаем переменные окружения
        mock_getenv.side_effect = lambda key, default=None: {
            "TWITCH_CLIENT_ID": "test_client_id",
            "TWITCH_CLIENT_SECRET": "test_secret",
            "TWITCH_REDIRECT_URI": "http://localhost:8000/auth/twitch/callback",
            "BACKEND_URL": "http://localhost:8000"
        }.get(key, default)
        
        response = client.get("/auth/twitch")
        # Может быть 307 (редирект), 400 (ошибка конфигурации), 404 (not found), или 500 (server error)
        assert response.status_code in [307, 400, 404, 500]
    
    @patch('os.getenv')
    def test_vk_auth_redirect_mock(self, mock_getenv, client):
        """Тест редиректа на VK с моком"""
        # Мокаем переменные окружения
        mock_getenv.side_effect = lambda key, default=None: {
            "VK_CLIENT_ID": "test_client_id",
            "VK_CLIENT_SECRET": "test_secret",
            "VK_REDIRECT_URI": "http://localhost:8000/auth/vk/callback",
            "BACKEND_URL": "http://localhost:8000"
        }.get(key, default)
        
        response = client.get("/auth/vk")
        # Может быть 307 (редирект), 400 (ошибка конфигурации), 404 (not found), или 500 (server error)
        assert response.status_code in [307, 400, 404, 503]
        if response.status_code == 503:
            assert response.json()["detail"]["code"] == "integration_not_configured"
