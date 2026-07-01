"""
VK Live API Client с retry logic и обработкой ошибок

Документация: docs/vk/API.md
Дата создания: 27 декабря 2025
"""
import httpx
import os
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Any, Dict, Optional, List
from utils.vk_channel_url import normalize_vk_channel_url

logger = structlog.get_logger(__name__)


class VKAPIError(Exception):
    """Ошибка VK Live API"""
    def __init__(self, error_code: str, error_message: str):
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(f"{error_code}: {error_message}")


class VKLiveAPIClient:
    """
    Клиент для работы с VK Live API
    
    Features:
    - Retry logic с exponential backoff (3 попытки, 2-10 сек)
    - Обработка всех ошибок из документации
    - Структурированное логирование
    - Type hints для всех методов
    - Async context manager support
    
    Документация: 
    - docs/vk/Авторизация.md
    - docs/vk/Методы_Чат.md
    - docs/vk/Методы_Баллы.md
    - docs/vk/Методы_Websocket.md
    
    Example:
        >>> async with VKLiveAPIClient() as client:
        ...     messages = await client.get_chat_messages(
        ...         token='user_token',
        ...         channel_url='streamer'
        ...     )
    """
    
    # Ошибки из документации VK Live API
    VK_ERRORS = {
        # Чат ошибки (docs/vk/Методы_Чат.md)
        'message_too_long': 'Сообщение слишком длинное',
        'same_message': 'Повторяющееся сообщение',
        'send_too_fast': 'Слишком быстрая отправка сообщений',
        
        # Общие ошибки (docs/vk/Ошибки.md)
        'unauthorized': 'Не авторизован',
        'forbidden': 'Доступ запрещен',
        'unprocessable_entity': 'Невозможно обработать запрос',
        'not_found': 'Ресурс не найден',
        'bad_request': 'Неверный запрос',
        
        # Баллы ошибки (docs/vk/Методы_Баллы.md)
        'reward_not_found': 'Награда не найдена',
        'insufficient_points': 'Недостаточно баллов',
        'reward_disabled': 'Награда отключена',
        'reward_limit_reached': 'Достигнут лимит использования награды',
    }
    
    PROD_BASE_URL = "https://api.live.vkvideo.ru"
    DEV_BASE_URL = "https://apidev.live.vkvideo.ru"

    def __init__(self, base_url: str = PROD_BASE_URL):
        """
        Инициализация клиента
        
        Args:
            base_url: Базовый URL API (из docs/vk/API.md)
        """
        self.base_url = base_url
        insecure_dev_ssl = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}
        ssl_verify = not insecure_dev_ssl
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            verify=ssl_verify
        )
        logger.info("vk_api_client_initialized", base_url=base_url, ssl_verify=ssl_verify)
        
    async def __aenter__(self):
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        
    async def close(self):
        """Закрыть клиент"""
        await self.client.aclose()
        logger.info("vk_api_client_closed")
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def make_request(
        self,
        method: str,
        endpoint: str,
        token: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Выполнить API запрос с retry logic
        
        Args:
            method: HTTP метод (GET, POST, PUT, DELETE)
            endpoint: API endpoint (например, /v1/chat/messages)
            token: Bearer токен для авторизации
            **kwargs: Дополнительные параметры для httpx (params, json, data)
            
        Returns:
            dict: Ответ API
            
        Raises:
            VKAPIError: При ошибке API
            httpx.RequestError: При сетевой ошибке
            
        Example:
            >>> response = await client.make_request(
            ...     'GET',
            ...     '/v1/chat/messages',
            ...     token='user_token',
            ...     params={'channel_url': 'streamer', 'limit': 50}
            ... )
        """
        # Добавить Authorization header если есть токен
        headers = kwargs.get('headers', {})
        if token:
            headers['Authorization'] = f'Bearer {token}'
            kwargs['headers'] = headers

        params = kwargs.get("params")
        if isinstance(params, dict) and "channel_url" in params:
            params["channel_url"] = normalize_vk_channel_url(params.get("channel_url"))
            kwargs["params"] = params
            
        try:
            logger.debug(
                "vk_api_request",
                method=method,
                endpoint=endpoint,
                has_token=bool(token)
            )
            
            response = await self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            
            logger.debug(
                "vk_api_success",
                method=method,
                endpoint=endpoint,
                status_code=response.status_code
            )
            
            return response.json()
            
        except httpx.HTTPStatusError as e:
            # Обработать ошибки API
            try:
                error_data = e.response.json()
                error_code = error_data.get('error', 'unknown')
                error_description = error_data.get('error_description', 'Unknown error')
                
                # Получить понятное сообщение на русском
                error_msg = self.VK_ERRORS.get(error_code, error_description)
                
                logger.error(
                    "vk_api_error",
                    error_code=error_code,
                    error_msg=error_msg,
                    endpoint=endpoint,
                    status_code=e.response.status_code
                )
                
                raise VKAPIError(error_code, error_msg) from e
                
            except (ValueError, KeyError):
                # Если не удалось распарсить JSON
                logger.error(
                    "vk_api_error_unparseable",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    response_text=e.response.text[:200]
                )
                raise
                
        except httpx.RequestError as e:
            logger.error(
                "vk_api_request_error",
                error=str(e),
                endpoint=endpoint,
                error_type=type(e).__name__
            )
            raise

    # === Методы для работы с чатом (docs/vk/Методы_Чат.md) ===
    
    async def send_chat_message(
        self,
        token: str,
        channel_url: str,
        stream_id: str,
        message_parts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Отправить сообщение в чат
        
        Документация: docs/vk/Методы_Чат.md
        POST /v1/chat/message/send
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            stream_id: ID стрима
            message_parts: Части сообщения (text, smile, mention, link)
            
        Returns:
            dict: Ответ API с информацией о сообщении
            
        Raises:
            VKAPIError: 
                - message_too_long: Сообщение слишком длинное
                - same_message: Повторяющееся сообщение
                - send_too_fast: Слишком быстрая отправка
                
        Example:
            >>> message_parts = [{'text': {'content': 'Привет!'}}]
            >>> await client.send_chat_message(
            ...     token='user_token',
            ...     channel_url='streamer',
            ...     stream_id='12345',
            ...     message_parts=message_parts
            ... )
        """
        return await self.make_request(
            'POST',
            '/v1/chat/message/send',
            token=token,
            params={'channel_url': channel_url, 'stream_id': stream_id},
            json={'parts': message_parts}
        )
        
    async def get_chat_messages(
        self,
        token: str,
        channel_url: str,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Получить сообщения из чата
        
        Документация: docs/vk/Методы_Чат.md
        GET /v1/chat/messages
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            limit: Количество сообщений (макс 200)
            offset: Смещение для пагинации
            
        Returns:
            dict: Список сообщений
        """
        return await self.make_request(
            'GET',
            '/v1/chat/messages',
            token=token,
            params={
                'channel_url': channel_url,
                'limit': min(limit, 200),
                'offset': offset
            }
        )
        
    async def get_chat_members(
        self,
        token: str,
        channel_url: str,
        limit: int = 200
    ) -> Dict[str, Any]:
        """
        Получить участников чата (до 200)
        
        Документация: docs/vk/Методы_Чат.md
        GET /v1/chat/members
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            limit: Количество участников (макс 200)
            
        Returns:
            dict: Список участников чата
        """
        return await self.make_request(
            'GET',
            '/v1/chat/members',
            token=token,
            params={'channel_url': channel_url, 'limit': min(limit, 200)}
        )
        
    async def get_chat_member(
        self,
        token: str,
        channel_url: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Получить информацию об участнике чата
        
        Документация: docs/vk/Методы_Чат.md
        GET /v1/chat/member
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            user_id: ID пользователя VK
            
        Returns:
            dict: Информация об участнике
        """
        return await self.make_request(
            'GET',
            '/v1/chat/member',
            token=token,
            params={'channel_url': channel_url, 'user_id': user_id}
        )
        
    async def get_chat_settings(
        self,
        token: str,
        channel_url: str
    ) -> Dict[str, Any]:
        """
        Получить настройки чата
        
        Документация: docs/vk/Методы_Чат.md
        GET /v1/chat/settings
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            
        Returns:
            dict: Настройки чата
        """
        return await self.make_request(
            'GET',
            '/v1/chat/settings',
            token=token,
            params={'channel_url': channel_url}
        )
        
    async def edit_chat_settings(
        self,
        token: str,
        channel_url: str,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Изменить настройки чата
        
        Документация: docs/vk/Методы_Чат.md
        POST /v1/chat/settings/edit
        
        Требования:
        - Авторизация: пользователь
        - Доступность: владелец канала
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            settings: Новые настройки чата
            
        Returns:
            dict: Обновленные настройки
        """
        return await self.make_request(
            'POST',
            '/v1/chat/settings/edit',
            token=token,
            params={'channel_url': channel_url},
            json={'settings': settings}
        )
    
    # === Методы для работы с баллами (docs/vk/Методы_Баллы.md) ===
    
    async def get_channel_points_balance(
        self,
        token: str,
        channel_url: str
    ) -> Dict[str, Any]:
        """
        Получить баланс баллов на канале
        
        Документация: docs/vk/Методы_Баллы.md
        GET /v1/channel_point
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            
        Returns:
            dict: Баланс баллов пользователя
        """
        return await self.make_request(
            'GET',
            '/v1/channel_point',
            token=token,
            params={'channel_url': channel_url}
        )
        
    async def get_channel_rewards(
        self,
        token: str,
        channel_url: str
    ) -> Dict[str, Any]:
        """
        Получить список наград за баллы
        
        Документация: docs/vk/Методы_Баллы.md
        GET /v1/channel_point/rewards
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            
        Returns:
            dict: Список доступных наград
        """
        return await self.make_request(
            'GET',
            '/v1/channel_point/rewards',
            token=token,
            params={'channel_url': channel_url}
        )
        
    async def activate_reward(
        self,
        token: str,
        channel_url: str,
        reward_id: str,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Активировать (купить) награду за баллы
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/activate
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            message: Сообщение (если награда требует)
            
        Returns:
            dict: Информация об активации
            
        Raises:
            VKAPIError:
                - insufficient_points: Недостаточно баллов
                - reward_disabled: Награда отключена
                - reward_limit_reached: Достигнут лимит
        """
        data = {'reward_id': reward_id}
        if message:
            data['message'] = message
            
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/activate',
            token=token,
            params={'channel_url': channel_url},
            json=data
        )
        
    async def create_reward(
        self,
        token: str,
        channel_url: str,
        name: str,
        description: str,
        price: int,
        background_color: int,
        is_message_required: bool = False,
        max_uses_count: Optional[int] = None,
        max_uses_count_per_user: Optional[int] = None,
        repair_timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Создать награду за баллы
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/create
        
        Требования:
        - Авторизация: пользователь
        - Доступность: владелец канала
        - Разрешения: channel:points:manage
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            name: Название награды
            description: Описание награды
            price: Цена в баллах
            background_color: Цвет фона (RGB int)
            is_message_required: Требуется ли сообщение от пользователя
            max_uses_count: Максимальное количество использований
            max_uses_count_per_user: Макс использований на пользователя
            repair_timeout: Время восстановления в секундах
            
        Returns:
            dict: Созданная награда
        """
        reward_data = {
            'name': name,
            'description': description,
            'price': price,
            'background_color': background_color,
            'is_message_required': is_message_required
        }
        
        if max_uses_count is not None:
            reward_data['max_uses_count'] = max_uses_count
        if max_uses_count_per_user is not None:
            reward_data['max_uses_count_per_user'] = max_uses_count_per_user
        if repair_timeout is not None:
            reward_data['repair_timeout'] = repair_timeout
            
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/create',
            token=token,
            params={'channel_url': channel_url},
            json={'reward': reward_data}
        )
        
    async def edit_reward(
        self,
        token: str,
        channel_url: str,
        reward_id: str,
        **reward_fields
    ) -> Dict[str, Any]:
        """
        Редактировать награду
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/edit
        
        Требования:
        - Авторизация: пользователь
        - Доступность: владелец канала
        - Разрешения: channel:points:manage
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            **reward_fields: Поля для обновления (name, description, price, etc.)
            
        Returns:
            dict: Обновленная награда
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/edit',
            token=token,
            params={'channel_url': channel_url, 'reward_id': reward_id},
            json={'reward': reward_fields}
        )
        
    async def enable_reward(
        self,
        token: str,
        channel_url: str,
        reward_id: str
    ) -> Dict[str, Any]:
        """
        Включить награду
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/enable
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            
        Returns:
            dict: Обновленная награда
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/enable',
            token=token,
            params={'channel_url': channel_url, 'reward_id': reward_id}
        )
        
    async def disable_reward(
        self,
        token: str,
        channel_url: str,
        reward_id: str
    ) -> Dict[str, Any]:
        """
        Отключить награду
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/disable
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            
        Returns:
            dict: Обновленная награда
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/disable',
            token=token,
            params={'channel_url': channel_url, 'reward_id': reward_id}
        )
        
    async def delete_reward(
        self,
        token: str,
        channel_url: str,
        reward_id: str
    ) -> Dict[str, Any]:
        """
        Удалить награду
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/delete
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            
        Returns:
            dict: Подтверждение удаления
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/delete',
            token=token,
            params={'channel_url': channel_url, 'reward_id': reward_id}
        )
        
    async def get_reward_manage_info(
        self,
        token: str,
        channel_url: str,
        reward_id: str
    ) -> Dict[str, Any]:
        """
        Получить информацию о награде для управления
        
        Документация: docs/vk/Методы_Баллы.md
        GET /v1/channel_point/reward/manage_info
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            reward_id: ID награды
            
        Returns:
            dict: Детальная информация о награде
        """
        return await self.make_request(
            'GET',
            '/v1/channel_point/reward/manage_info',
            token=token,
            params={'channel_url': channel_url, 'reward_id': reward_id}
        )
        
    async def get_rewards_manage_info(
        self,
        token: str,
        channel_url: str
    ) -> Dict[str, Any]:
        """
        Получить список наград для управления
        
        Документация: docs/vk/Методы_Баллы.md
        GET /v1/channel_point/rewards/manage_info
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            
        Returns:
            dict: Список наград с детальной информацией
        """
        return await self.make_request(
            'GET',
            '/v1/channel_point/rewards/manage_info',
            token=token,
            params={'channel_url': channel_url}
        )
        
    async def get_reward_demands(
        self,
        token: str,
        channel_url: str,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Получить список запросов наград
        
        Документация: docs/vk/Методы_Баллы.md
        GET /v1/channel_point/reward/demands
        
        Требования:
        - Авторизация: пользователь
        - Доступность: владелец канала
        - Разрешения: channel:points:rewards:demands:read
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            limit: Количество запросов
            offset: Смещение для пагинации
            
        Returns:
            dict: Список запросов наград
        """
        return await self.make_request(
            'GET',
            '/v1/channel_point/reward/demands',
            token=token,
            params={
                'channel_url': channel_url,
                'limit': limit,
                'offset': offset
            }
        )
        
    async def accept_reward_demands(
        self,
        token: str,
        channel_url: str,
        demand_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Принять запросы наград
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/demand/accept
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            demand_ids: Список ID запросов для принятия
            
        Returns:
            dict: Результат принятия
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/demand/accept',
            token=token,
            params={'channel_url': channel_url},
            json={'demand_ids': demand_ids}
        )
        
    async def reject_reward_demands(
        self,
        token: str,
        channel_url: str,
        demand_ids: List[int]
    ) -> Dict[str, Any]:
        """
        Отклонить запросы наград
        
        Документация: docs/vk/Методы_Баллы.md
        POST /v1/channel_point/reward/demand/reject
        
        Args:
            token: Bearer токен пользователя
            channel_url: URL канала
            demand_ids: Список ID запросов для отклонения
            
        Returns:
            dict: Результат отклонения
        """
        return await self.make_request(
            'POST',
            '/v1/channel_point/reward/demand/reject',
            token=token,
            params={'channel_url': channel_url},
            json={'demand_ids': demand_ids}
        )
    
    # === Методы для WebSocket (docs/vk/Методы_Websocket.md) ===
    
    async def get_websocket_token(self, token: str) -> str:
        """
        Получить токен для WebSocket подключения
        
        Документация: docs/vk/Методы_Websocket.md
        GET /v1/websocket/token
        
        Args:
            token: Bearer токен пользователя
            
        Returns:
            str: JWT токен для WebSocket подключения
            
        Example:
            >>> ws_token = await client.get_websocket_token('user_token')
            >>> # Использовать для подключения к wss://pubsub-dev.live.vkvideo.ru
        """
        response = await self.make_request(
            'GET',
            '/v1/websocket/token',
            token=token
        )
        return response['data']['token']
        
    async def get_subscription_tokens(
        self,
        token: str,
        channels: List[str]
    ) -> Dict[str, str]:
        """
        Получить токены для подписки на каналы
        
        Документация: docs/vk/Методы_Websocket.md
        GET /v1/websocket/subscription_token
        
        Используется для подписки на каналы с ограниченным доступом (limited).
        
        Args:
            token: Bearer токен пользователя
            channels: Список названий каналов для подписки
            
        Returns:
            dict: Маппинг channel -> subscription_token
            
        Example:
            >>> tokens = await client.get_subscription_tokens(
            ...     token='user_token',
            ...     channels=['chat:streamer', 'stream:streamer']
            ... )
            >>> # {'chat:streamer': 'jwt_token1', 'stream:streamer': 'jwt_token2'}
        """
        response = await self.make_request(
            'GET',
            '/v1/websocket/subscription_token',
            token=token,
            params={'channels': ','.join(channels)}
        )
        
        return {
            item['channel']: item['token']
            for item in response['data']['channel_tokens']
        }
