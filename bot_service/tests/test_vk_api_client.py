"""
Тесты для VKLiveAPIClient

Дата создания: 27 декабря 2025
"""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
import pytest_asyncio
from utils.vk_api_client import VKLiveAPIClient, VKAPIError


@pytest_asyncio.fixture
async def vk_client():
    """Фикстура для VK API клиента"""
    client = VKLiveAPIClient()
    yield client
    await client.close()


@pytest.mark.asyncio
class TestVKLiveAPIClient:
    """Тесты для VKLiveAPIClient"""
    
    async def test_client_initialization(self):
        """Тест инициализации клиента"""
        client = VKLiveAPIClient()
        assert client.base_url == "https://api.live.vkvideo.ru"
        assert client.client is not None
        await client.close()
        
    async def test_async_context_manager(self):
        """Тест async context manager"""
        async with VKLiveAPIClient() as client:
            assert client.client is not None
        # После выхода из контекста клиент должен быть закрыт
        
    async def test_make_request_success(self, vk_client):
        """Тест успешного запроса"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'test': 'value'}}
        
        with patch.object(vk_client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.make_request('GET', '/test')
            
            assert result == {'data': {'test': 'value'}}
            mock_request.assert_called_once()
            
    async def test_make_request_with_token(self, vk_client):
        """Тест запроса с токеном авторизации"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {}}
        
        with patch.object(vk_client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            await vk_client.make_request('GET', '/test', token='test_token')
            
            # Проверить что Authorization header добавлен
            call_kwargs = mock_request.call_args[1]
            assert 'headers' in call_kwargs
            assert call_kwargs['headers']['Authorization'] == 'Bearer test_token'
            
    async def test_make_request_vk_api_error(self, vk_client):
        """Тест обработки ошибки VK API"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'error': 'send_too_fast',
            'error_description': 'Too many requests'
        }
        
        with patch.object(vk_client.client, 'request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                'Bad Request',
                request=MagicMock(),
                response=mock_response
            )
            
            with pytest.raises(VKAPIError) as exc_info:
                await vk_client.make_request('POST', '/test')
                
            assert exc_info.value.error_code == 'send_too_fast'
            assert 'Слишком быстрая отправка' in exc_info.value.error_message
            
    async def test_send_chat_message(self, vk_client):
        """Тест отправки сообщения в чат"""
        mock_response = {'data': {'message_id': '123'}}
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            message_parts = [{'text': {'content': 'Привет!'}}]
            result = await vk_client.send_chat_message(
                token='test_token',
                channel_url='streamer',
                stream_id='12345',
                message_parts=message_parts
            )
            
            assert result == mock_response
            mock_request.assert_called_once_with(
                'POST',
                '/v1/chat/message/send',
                token='test_token',
                params={'channel_url': 'streamer', 'stream_id': '12345'},
                json={'parts': message_parts}
            )
            
    async def test_get_chat_messages(self, vk_client):
        """Тест получения сообщений из чата"""
        mock_response = {'data': {'messages': []}}
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.get_chat_messages(
                token='test_token',
                channel_url='streamer',
                limit=50
            )
            
            assert result == mock_response
            mock_request.assert_called_once()
            
    async def test_get_channel_points_balance(self, vk_client):
        """Тест получения баланса баллов"""
        mock_response = {'data': {'balance': 1000}}
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.get_channel_points_balance(
                token='test_token',
                channel_url='streamer'
            )
            
            assert result == mock_response
            assert result['data']['balance'] == 1000
            
    async def test_create_reward(self, vk_client):
        """Тест создания награды"""
        mock_response = {'data': {'reward': {'id': 'reward_123'}}}
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.create_reward(
                token='test_token',
                channel_url='streamer',
                name='Test Reward',
                description='Test Description',
                price=100,
                background_color=0xFF0000
            )
            
            assert result == mock_response
            # Проверить что reward_data передан правильно
            call_kwargs = mock_request.call_args[1]
            assert 'json' in call_kwargs
            assert call_kwargs['json']['reward']['name'] == 'Test Reward'
            assert call_kwargs['json']['reward']['price'] == 100
            
    async def test_get_websocket_token(self, vk_client):
        """Тест получения WebSocket токена"""
        mock_response = {'data': {'token': 'ws_token_123'}}
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.get_websocket_token(token='test_token')
            
            assert result == 'ws_token_123'
            mock_request.assert_called_once_with(
                'GET',
                '/v1/websocket/token',
                token='test_token'
            )
            
    async def test_get_subscription_tokens(self, vk_client):
        """Тест получения токенов для подписки на каналы"""
        mock_response = {
            'data': {
                'channel_tokens': [
                    {'channel': 'chat:streamer', 'token': 'token1'},
                    {'channel': 'stream:streamer', 'token': 'token2'}
                ]
            }
        }
        
        with patch.object(vk_client, 'make_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            
            result = await vk_client.get_subscription_tokens(
                token='test_token',
                channels=['chat:streamer', 'stream:streamer']
            )
            
            assert result == {
                'chat:streamer': 'token1',
                'stream:streamer': 'token2'
            }
            
    async def test_retry_logic(self, vk_client):
        """Тест retry logic при сетевых ошибках"""
        # Первые 2 попытки - ошибка, 3-я - успех
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'success': True}}
        
        call_count = 0
        async def mock_request_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.RequestError('Connection error')
            return mock_response
            
        with patch.object(vk_client.client, 'request', side_effect=mock_request_with_retry):
            result = await vk_client.make_request('GET', '/test')
            
            assert result == {'data': {'success': True}}
            assert call_count == 3  # 2 retry + 1 успешная попытка
            
    async def test_error_messages_in_russian(self, vk_client):
        """Тест что сообщения об ошибках на русском языке"""
        error_codes = [
            ('message_too_long', 'Сообщение слишком длинное'),
            ('send_too_fast', 'Слишком быстрая отправка'),
            ('unauthorized', 'Не авторизован'),
            ('insufficient_points', 'Недостаточно баллов')
        ]
        
        for error_code, expected_message in error_codes:
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.json.return_value = {
                'error': error_code,
                'error_description': 'English description'
            }
            
            with patch.object(vk_client.client, 'request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = mock_response
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    'Error',
                    request=MagicMock(),
                    response=mock_response
                )
                
                with pytest.raises(VKAPIError) as exc_info:
                    await vk_client.make_request('GET', '/test')
                    
                assert exc_info.value.error_code == error_code
                assert expected_message in exc_info.value.error_message
