"""
Тесты для VKLiveWebSocketClient

Автор: AI Assistant
Дата: 27 декабря 2025
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from utils.vk_live_websocket import VKLiveWebSocketClient


@pytest_asyncio.fixture
async def ws_client():
    """Фикстура для VKLiveWebSocketClient"""
    client = VKLiveWebSocketClient(access_token="test_token")
    yield client
    await client.disconnect()


@pytest.mark.asyncio
class TestVKLiveWebSocketClient:
    """Тесты для VKLiveWebSocketClient"""
    
    async def test_client_initialization(self):
        """Тест инициализации клиента"""
        client = VKLiveWebSocketClient(access_token="test_token")
        assert client.access_token == "test_token"
        assert client.is_connected is False
        assert len(client.subscribed_channels) == 0
        assert client.reconnect_delay == 1
        assert client.max_reconnect_delay == 60
        await client.disconnect()
        
    async def test_connect_success(self, ws_client):
        """Тест успешного подключения"""
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"type":"welcome"}')
        
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_websocket
            
            result = await ws_client.connect()
            
            assert result is True
            assert ws_client.is_connected is True
            assert ws_client.reconnect_attempts == 0
            assert ws_client.reconnect_delay == 1
            
    async def test_connect_failure(self, ws_client):
        """Тест неудачного подключения"""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            result = await ws_client.connect()
            
            assert result is False
            assert ws_client.is_connected is False
            
    async def test_connect_with_retry_success(self, ws_client):
        """Тест подключения с retry (успех на 2-й попытке)"""
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"type":"welcome"}')
        
        call_count = 0
        async def connect_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First attempt failed")
            return mock_websocket
        
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = connect_side_effect
            
            result = await ws_client.connect_with_retry(max_attempts=3)
            
            assert result is True
            assert ws_client.is_connected is True
            assert call_count == 2
            
    async def test_connect_with_retry_max_attempts(self, ws_client):
        """Тест исчерпания попыток подключения"""
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            result = await ws_client.connect_with_retry(max_attempts=3)
            
            assert result is False
            assert ws_client.is_connected is False
            assert mock_connect.call_count == 3
            
    async def test_exponential_backoff(self, ws_client):
        """Тест exponential backoff"""
        delays = []
        
        async def mock_sleep(delay):
            delays.append(delay)
        
        with patch('websockets.connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep_patch:
                mock_sleep_patch.side_effect = mock_sleep
                
                await ws_client.connect_with_retry(max_attempts=4)
                
                # Проверяем что задержки растут экспоненциально
                assert len(delays) == 4
                assert delays[0] == 1  # 1 * 2^0
                assert delays[1] == 2  # 1 * 2^1
                assert delays[2] == 4  # 1 * 2^2
                assert delays[3] == 8  # 1 * 2^3
                
    async def test_subscribe_to_channel_public(self, ws_client):
        """Тест подписки на публичный канал"""
        mock_websocket = AsyncMock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"result": true}')
        
        ws_client.websocket = mock_websocket
        ws_client.is_connected = True
        
        result = await ws_client.subscribe_to_channel("chat:streamer", use_subscription_token=False)
        
        assert result is True
        assert "chat:streamer" in ws_client.subscribed_channels
        mock_websocket.send.assert_called_once()
        
    async def test_subscribe_to_channel_with_token(self, ws_client):
        """Тест подписки на приватный канал с subscription token"""
        mock_websocket = AsyncMock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"result": true}')
        
        ws_client.websocket = mock_websocket
        ws_client.is_connected = True
        
        # Мокаем получение subscription token
        with patch.object(
            ws_client,
            '_get_subscription_token_for_channel',
            new_callable=AsyncMock
        ) as mock_get_token:
            mock_get_token.return_value = "subscription_token_123"
            
            result = await ws_client.subscribe_to_channel("limited_chat:streamer", use_subscription_token=True)
            
            assert result is True
            assert "limited_chat:streamer" in ws_client.subscribed_channels
            mock_get_token.assert_called_once_with("limited_chat:streamer")
            
            # Проверяем что токен был добавлен в subscribe сообщение
            call_args = mock_websocket.send.call_args[0][0]
            import json
            subscribe_msg = json.loads(call_args)
            assert "token" in subscribe_msg["params"]
            assert subscribe_msg["params"]["token"] == "subscription_token_123"
            
    async def test_subscribe_timeout(self, ws_client):
        """Тест таймаута при подписке"""
        mock_websocket = AsyncMock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        
        ws_client.websocket = mock_websocket
        ws_client.is_connected = True
        
        result = await ws_client.subscribe_to_channel("chat:streamer", use_subscription_token=False)
        
        assert result is False
        assert "chat:streamer" not in ws_client.subscribed_channels
        
    async def test_subscribe_error_response(self, ws_client):
        """Тест ошибки при подписке"""
        mock_websocket = AsyncMock()
        mock_websocket.send = AsyncMock()
        mock_websocket.recv = AsyncMock(
            return_value='{"error": {"code": 403, "message": "Access denied"}}'
        )
        
        ws_client.websocket = mock_websocket
        ws_client.is_connected = True
        
        result = await ws_client.subscribe_to_channel("private_chat:streamer", use_subscription_token=False)
        
        assert result is False
        assert "private_chat:streamer" not in ws_client.subscribed_channels
        
    async def test_get_subscription_token(self, ws_client):
        """Тест получения subscription token через VKLiveAPIClient"""
        with patch('utils.vk_api_client.VKLiveAPIClient') as mock_api_class:
            mock_api_client = AsyncMock()
            mock_api_client.get_subscription_tokens = AsyncMock(
                return_value={"chat:streamer": "token_123"}
            )
            mock_api_class.return_value = mock_api_client
            
            token = await ws_client._get_subscription_token_for_channel("chat:streamer")
            
            assert token == "token_123"
            mock_api_client.get_subscription_tokens.assert_called_once()
            
    async def test_get_subscription_token_not_found(self, ws_client):
        """Тест когда subscription token не найден"""
        with patch('utils.vk_api_client.VKLiveAPIClient') as mock_api_class:
            mock_api_client = AsyncMock()
            mock_api_client.get_subscription_tokens = AsyncMock(
                return_value={"other_channel": "token_123"}
            )
            mock_api_class.return_value = mock_api_client
            
            token = await ws_client._get_subscription_token_for_channel("chat:streamer")
            
            assert token is None
            
    async def test_disconnect(self, ws_client):
        """Тест отключения"""
        mock_websocket = AsyncMock()
        mock_websocket.close = AsyncMock()
        
        ws_client.websocket = mock_websocket
        ws_client.is_connected = True
        
        await ws_client.disconnect()
        
        assert ws_client.is_connected is False
        assert ws_client.websocket is None
        mock_websocket.close.assert_called_once()
        
    async def test_disconnect_with_api_client(self, ws_client):
        """Тест отключения с закрытием API client"""
        mock_websocket = AsyncMock()
        mock_websocket.close = AsyncMock()
        
        mock_api_client = AsyncMock()
        mock_api_client.close = AsyncMock()
        
        ws_client.websocket = mock_websocket
        ws_client._api_client = mock_api_client
        ws_client.is_connected = True
        
        await ws_client.disconnect()
        
        assert ws_client.is_connected is False
        assert ws_client.websocket is None
        assert ws_client._api_client is None
        mock_websocket.close.assert_called_once()
        mock_api_client.close.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
