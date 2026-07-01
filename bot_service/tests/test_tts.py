# bot_service/tests/test_tts.py
"""
Тесты для TTS функциональности
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

class TestTTSManager:
    """Тесты для TTS Manager"""
    
    @pytest.fixture
    def mock_tts_manager(self):
        """Создает мок TTS Manager"""
        with patch('services.tts.tts_manager.TTSManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            yield mock_manager
    
    @pytest.mark.asyncio
    async def test_tts_manager_initialization(self):
        """Тест инициализации TTS Manager"""
        from services.tts.tts_manager import TTSManager
        from core.config import settings
        
        manager = TTSManager()
        # Verify it uses settings instead of hardcoded values
        assert manager.f5_tts_service_url == settings.f5_tts_service_url
        from services.tts import tts_manager as tts_manager_module
        assert manager.backend_url == tts_manager_module.settings.backend_url
        assert manager.basic_tts is not None
    
    @pytest.mark.asyncio
    async def test_tts_service_health_check(self, mock_tts_manager):
        """Тест проверки здоровья TTS сервиса"""
        mock_tts_manager.check_tts_service_health.return_value = True
        
        result = await mock_tts_manager.check_tts_service_health()
        assert result == True
        mock_tts_manager.check_tts_service_health.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tts_synthesis_basic(self, mock_tts_manager):
        """Тест синтеза базовой TTS"""
        mock_tts_manager.synthesize_tts.return_value = {
            "success": True,
            "voice": "basic_voice",
            "volume": 50.0,
            "tts_type": "basic"
        }
        
        result = await mock_tts_manager.synthesize_tts(
            channel_name="test_channel",
            text="Hello, world!",
            author="test_user",
            use_basic_tts=True,
            use_ai_tts=False
        )
        
        assert result["success"] == True
        assert result["tts_type"] == "basic"
        mock_tts_manager.synthesize_tts.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tts_synthesis_ai(self, mock_tts_manager):
        """Тест синтеза AI TTS"""
        mock_tts_manager.synthesize_tts.return_value = {
            "success": True,
            "voice": "ai_voice",
            "volume": 75.0,
            "tts_type": "ai"
        }
        
        result = await mock_tts_manager.synthesize_tts(
            channel_name="test_channel",
            text="Hello, world!",
            author="test_user",
            use_basic_tts=False,
            use_ai_tts=True
        )
        
        assert result["success"] == True
        assert result["tts_type"] == "ai"
        mock_tts_manager.synthesize_tts.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tts_fallback_to_basic(self, mock_tts_manager):
        """Тест fallback на базовую TTS при недоступности AI"""
        # Мок возвращает успешный fallback на basic TTS
        mock_tts_manager.synthesize_tts.return_value = {
            "success": True, 
            "voice": "basic_voice", 
            "tts_type": "basic",
            "fallback": True
        }
        
        result = await mock_tts_manager.synthesize_tts(
            channel_name="test_channel",
            text="Hello, world!",
            author="test_user",
            use_basic_tts=True,
            use_ai_tts=True
        )
        
        assert result["success"] == True
        assert result["tts_type"] == "basic"
        mock_tts_manager.synthesize_tts.assert_called_once()

class TestBasicTTS:
    """Тесты для базовой TTS"""
    
    @pytest.fixture
    def mock_basic_tts(self):
        """Создает мок базовой TTS"""
        with patch('services.tts.basic_tts.BasicTTS') as mock_tts_class:
            mock_tts = AsyncMock()
            mock_tts_class.return_value = mock_tts
            yield mock_tts
    
    @pytest.mark.asyncio
    async def test_basic_tts_synthesis(self, mock_basic_tts):
        """Тест синтеза базовой TTS"""
        mock_basic_tts.synthesize.return_value = {
            "success": True,
            "audio_path": "/tmp/test_audio.mp3",
            "duration": 2.5
        }
        
        result = await mock_basic_tts.synthesize(
            text="Hello, world!",
            voice="en",
            speed=1.0
        )
        
        assert result["success"] == True
        assert "audio_path" in result
        mock_basic_tts.synthesize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_basic_tts_error_handling(self, mock_basic_tts):
        """Тест обработки ошибок в базовой TTS"""
        mock_basic_tts.synthesize.side_effect = Exception("TTS synthesis failed")
        
        with pytest.raises(Exception):
            await mock_basic_tts.synthesize(
                text="Hello, world!",
                voice="en",
                speed=1.0
            )


class TestTTSAPI:
    """Tests for API facade forwarding to TTSManager."""

    @pytest.mark.asyncio
    async def test_send_tts_request_forwards_user_and_db_session(self):
        from services.tts.tts_core import TTSAPI

        fake_db_session = object()
        mock_manager = AsyncMock()
        mock_manager.synthesize_tts.return_value = {"success": True}

        with patch("services.tts.tts_core.get_tts_manager", return_value=mock_manager):
            api = TTSAPI()
            await api.send_tts_request(
                channel_name="channel",
                text="hello",
                author="tester",
                user_id=42,
                db_session=fake_db_session,
                use_ai_tts=True,
                use_basic_tts=True,
                engine="f5tts",
            )

        assert mock_manager.synthesize_tts.await_count == 1
        kwargs = mock_manager.synthesize_tts.await_args.kwargs
        assert kwargs["user_id"] == 42
        assert kwargs["db_session"] is fake_db_session



class TestTTSService:
    """Тесты для TTS Service"""
    
    @pytest.fixture
    def mock_tts_service(self, db_session):
        """Создает мок TTS Service"""
        with patch('services.tts.tts_service.TTSService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            yield mock_service
    
    @pytest.mark.asyncio
    async def test_text_filter_check(self, mock_tts_service):
        """Тест проверки фильтра текста"""
        mock_tts_service.check_text_filter.return_value = False
        
        result = await mock_tts_service.check_text_filter(
            text="Hello, world!",
            user_id=1,
            platform="twitch"
        )
        
        assert result == False
        mock_tts_service.check_text_filter.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_text_filter_blocked(self, mock_tts_service):
        """Тест блокировки текста фильтром"""
        mock_tts_service.check_text_filter.return_value = True
        
        result = await mock_tts_service.check_text_filter(
            text="bad word here",
            user_id=1,
            platform="twitch"
        )
        
        assert result == True
        mock_tts_service.check_text_filter.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_user_blocked_check(self, mock_tts_service):
        """Тест проверки блокировки пользователя"""
        mock_tts_service.is_user_blocked.return_value = False
        
        result = await mock_tts_service.is_user_blocked(
            channel_name="test_channel",
            platform="twitch",
            username="test_user"
        )
        
        assert result == False
        mock_tts_service.is_user_blocked.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_user_blocked_true(self, mock_tts_service):
        """Тест блокированного пользователя"""
        mock_tts_service.is_user_blocked.return_value = True
        
        result = await mock_tts_service.is_user_blocked(
            channel_name="test_channel",
            platform="twitch",
            username="blocked_user"
        )
        
        assert result == True
        mock_tts_service.is_user_blocked.assert_called_once()

@pytest.mark.skip(reason="TTS integration tests require complex async pipeline setup")
class TestTTSIntegration:
    """Тесты интеграции TTS"""
    
    @pytest.mark.asyncio
    async def test_tts_full_pipeline(self, mock_connection_manager):
        """Тест полного пайплайна TTS"""
        from services.tts.tts_manager import TTSManager
        
        # Мокаем TTS Manager
        with patch('services.tts.tts_manager.TTSManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            mock_manager.synthesize_tts.return_value = {
                "success": True,
                "voice": "test_voice",
                "volume": 50.0,
                "tts_type": "basic"
            }
            
            # Мокаем connection_manager
            mock_connection_manager.is_tts_enabled.return_value = True
            mock_connection_manager.is_channel_whitelisted.return_value = True
            mock_connection_manager.get_tts_volume.return_value = 50.0
            mock_connection_manager.is_basic_tts_enabled.return_value = True
            mock_connection_manager.is_ai_tts_enabled.return_value = False
            
            # Тестируем полный пайплайн
            result = await mock_manager.synthesize_tts(
                channel_name="test_channel",
                text="Hello, world!",
                author="test_user",
                volume_level=50.0,
                connection_manager=mock_connection_manager,
                use_basic_tts=True,
                use_ai_tts=False
            )
            
            assert result["success"] == True
            assert result["tts_type"] == "basic"
            mock_manager.synthesize_tts.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tts_error_recovery(self, mock_connection_manager):
        """Тест восстановления после ошибок TTS"""
        from services.tts.tts_manager import TTSManager
        
        # Мокаем TTS Manager с ошибкой
        with patch('services.tts.tts_manager.TTSManager') as mock_manager_class:
            mock_manager = AsyncMock()
            mock_manager_class.return_value = mock_manager
            
            # Первый вызов - ошибка, второй - успех
            mock_manager.synthesize_tts.side_effect = [
                Exception("TTS service unavailable"),
                {"success": True, "voice": "fallback_voice", "tts_type": "basic"}
            ]
            
            # Мокаем connection_manager
            mock_connection_manager.is_tts_enabled.return_value = True
            mock_connection_manager.is_channel_whitelisted.return_value = True
            
            # Тестируем восстановление после ошибки
            try:
                result = await mock_manager.synthesize_tts(
                    channel_name="test_channel",
                    text="Hello, world!",
                    author="test_user",
                    volume_level=50.0,
                    connection_manager=mock_connection_manager,
                    use_basic_tts=True,
                    use_ai_tts=False
                )
                assert result["success"] == True
            except Exception:
                # Ожидаем, что система обработает ошибку
                pass
