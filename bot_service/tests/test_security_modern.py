import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import jwt

from core.security_modern import modern_security_manager, rate_limit, login_rate_limit


class TestModernSecurityManager:
    """Тесты для ModernSecurityManager"""
    
    def test_create_access_token(self):
        """Тест создания JWT токена"""
        data = {"user_id": 123, "is_admin": True}
        token = modern_security_manager.create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_verify_token_valid(self):
        """Тест верификации валидного токена"""
        data = {"user_id": 123, "is_admin": True}
        token = modern_security_manager.create_access_token(data)
        
        payload = modern_security_manager.verify_token(token)
        
        assert payload is not None
        assert payload["user_id"] == 123
        assert payload["is_admin"] == True
    
    def test_verify_token_invalid(self):
        """Тест верификации невалидного токена"""
        with pytest.raises(Exception):
            modern_security_manager.verify_token("invalid_token")
    
    def test_verify_token_expired(self):
        """Тест верификации истекшего токена"""
        # Создаем токен с очень коротким временем жизни
        data = {"user_id": 123, "is_admin": True}
        token = modern_security_manager.create_access_token(
            data, 
            expires_delta=timedelta(seconds=-1)  # Уже истек
        )
        
        with pytest.raises(Exception):
            modern_security_manager.verify_token(token)
    
    def test_generate_session_id(self):
        """Тест генерации ID сессии"""
        session_id = modern_security_manager.generate_session_id()
        
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        
        # Генерируем еще один - должен быть разным
        session_id2 = modern_security_manager.generate_session_id()
        assert session_id != session_id2
    
    def test_generate_csrf_token(self):
        """Тест генерации CSRF токена"""
        csrf_token = modern_security_manager.generate_csrf_token()
        
        assert csrf_token is not None
        assert isinstance(csrf_token, str)
        assert len(csrf_token) > 0
        
        # Генерируем еще один - должен быть разным
        csrf_token2 = modern_security_manager.generate_csrf_token()
        assert csrf_token != csrf_token2
    
    def test_verify_csrf_token(self):
        """Тест проверки CSRF токена"""
        token = "test_csrf_token"
        session_token = "test_csrf_token"
        
        # Правильный токен
        assert modern_security_manager.verify_csrf_token(token, session_token) == True
        
        # Неправильный токен
        wrong_token = "wrong_csrf_token"
        assert modern_security_manager.verify_csrf_token(wrong_token, session_token) == False


class TestRateLimiting:
    """Тесты для rate limiting"""
    
    def test_rate_limit_decorator(self):
        """Тест декоратора rate_limit"""
        # Создаем простую функцию для тестирования с параметром request
        @rate_limit("10/minute")
        def test_function(request):
            return "success"
        
        # Функция должна быть доступна
        assert callable(test_function)
    
    def test_login_rate_limit_decorator(self):
        """Тест декоратора login_rate_limit"""
        # login_rate_limit возвращает декоратор
        decorator = login_rate_limit()
        
        # Декоратор должен быть callable
        assert callable(decorator)
        
        # Применяем декоратор к функции с параметром request
        def test_login_function(request):
            return "success"
        
        decorated_function = decorator(test_login_function)
        
        # Функция должна быть доступна
        assert callable(decorated_function)


class TestSecurityIntegration:
    """Интеграционные тесты безопасности"""
    
    def test_jwt_with_oauth_integration(self):
        """Тест интеграции JWT с OAuth"""
        # 1. Создаем JWT токен с данными пользователя
        user_data = {
            "user_id": 123,
            "username": "testuser",
            "is_admin": False,
            "oauth_provider": "twitch"
        }
        
        jwt_token = modern_security_manager.create_access_token(user_data)
        
        # 2. Верифицируем JWT токен
        payload = modern_security_manager.verify_token(jwt_token)
        
        # 3. Проверяем данные
        assert payload["user_id"] == 123
        assert payload["username"] == "testuser"
        assert payload["is_admin"] == False
        assert payload["oauth_provider"] == "twitch"
    
    def test_session_security(self):
        """Тест безопасности сессий"""
        # 1. Генерируем ID сессии
        session_id = modern_security_manager.generate_session_id()
        
        # 2. Генерируем CSRF токен
        csrf_token = modern_security_manager.generate_csrf_token()
        
        # 3. Проверяем CSRF токен
        assert modern_security_manager.verify_csrf_token(csrf_token, csrf_token) == True
        
        # 4. Проверяем, что токены уникальны
        assert session_id != csrf_token


class TestSecurityErrorHandling:
    """Тесты обработки ошибок безопасности"""
    
    
    def test_jwt_verification_error_handling(self):
        """Тест обработки ошибок при верификации JWT"""
        # Тестируем с невалидным токеном
        with pytest.raises(Exception):
            modern_security_manager.verify_token("invalid.jwt.token")
        
        # Тестируем с пустым токеном
        with pytest.raises(Exception):
            modern_security_manager.verify_token("")
        
        # Тестируем с None
        with pytest.raises(Exception):
            modern_security_manager.verify_token(None)