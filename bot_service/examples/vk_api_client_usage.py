"""
Примеры использования VKLiveAPIClient

Дата создания: 27 декабря 2025
"""
import asyncio
from utils.vk_api_client import VKLiveAPIClient, VKAPIError


async def example_chat_operations():
    """Примеры работы с чатом"""
    async with VKLiveAPIClient() as client:
        token = "your_user_token"
        channel_url = "streamer_name"
        stream_id = "12345"
        
        try:
            # Отправить сообщение
            message_parts = [{'text': {'content': 'Привет, чат!'}}]
            result = await client.send_chat_message(
                token=token,
                channel_url=channel_url,
                stream_id=stream_id,
                message_parts=message_parts
            )
            print(f"Сообщение отправлено: {result}")
            
            # Получить последние сообщения
            messages = await client.get_chat_messages(
                token=token,
                channel_url=channel_url,
                limit=50
            )
            print(f"Получено сообщений: {len(messages['data']['messages'])}")
            
            # Получить участников чата
            members = await client.get_chat_members(
                token=token,
                channel_url=channel_url,
                limit=100
            )
            print(f"Участников в чате: {len(members['data']['members'])}")
            
        except VKAPIError as e:
            if e.error_code == 'send_too_fast':
                print("Слишком быстрая отправка, подождите немного")
                await asyncio.sleep(2)
            elif e.error_code == 'message_too_long':
                print("Сообщение слишком длинное, обрежьте его")
            else:
                print(f"Ошибка: {e.error_message}")


async def example_channel_points_operations():
    """Примеры работы с баллами канала"""
    async with VKLiveAPIClient() as client:
        token = "your_user_token"
        channel_url = "streamer_name"
        
        try:
            # Получить баланс баллов
            balance = await client.get_channel_points_balance(
                token=token,
                channel_url=channel_url
            )
            print(f"Баланс баллов: {balance['data']['balance']}")
            
            # Получить список наград
            rewards = await client.get_channel_rewards(
                token=token,
                channel_url=channel_url
            )
            print(f"Доступно наград: {len(rewards['data']['rewards'])}")
            
            # Создать награду (только для владельца канала)
            new_reward = await client.create_reward(
                token=token,
                channel_url=channel_url,
                name="TTS сообщение",
                description="Озвучить ваше сообщение",
                price=100,
                background_color=0x9147FF,  # Фиолетовый цвет
                is_message_required=True,
                max_uses_count_per_user=5
            )
            print(f"Награда создана: {new_reward['data']['reward']['id']}")
            
            # Активировать награду (купить)
            reward_id = "reward_123"
            activation = await client.activate_reward(
                token=token,
                channel_url=channel_url,
                reward_id=reward_id,
                message="Привет, стример!"
            )
            print(f"Награда активирована: {activation}")
            
        except VKAPIError as e:
            if e.error_code == 'insufficient_points':
                print("Недостаточно баллов для покупки награды")
            elif e.error_code == 'reward_disabled':
                print("Награда отключена")
            else:
                print(f"Ошибка: {e.error_message}")


async def example_reward_management():
    """Примеры управления наградами (для владельца канала)"""
    async with VKLiveAPIClient() as client:
        token = "owner_token"
        channel_url = "your_channel"
        
        try:
            # Получить список наград для управления
            rewards = await client.get_rewards_manage_info(
                token=token,
                channel_url=channel_url
            )
            print(f"Наград для управления: {len(rewards['data']['rewards'])}")
            
            reward_id = "reward_123"
            
            # Редактировать награду
            updated = await client.edit_reward(
                token=token,
                channel_url=channel_url,
                reward_id=reward_id,
                price=150,  # Изменить цену
                description="Новое описание"
            )
            print(f"Награда обновлена: {updated}")
            
            # Отключить награду
            await client.disable_reward(
                token=token,
                channel_url=channel_url,
                reward_id=reward_id
            )
            print("Награда отключена")
            
            # Включить награду
            await client.enable_reward(
                token=token,
                channel_url=channel_url,
                reward_id=reward_id
            )
            print("Награда включена")
            
            # Получить запросы наград
            demands = await client.get_reward_demands(
                token=token,
                channel_url=channel_url,
                limit=50
            )
            print(f"Запросов наград: {len(demands['data']['demands'])}")
            
            # Принять запросы
            if demands['data']['demands']:
                demand_ids = [d['id'] for d in demands['data']['demands'][:5]]
                await client.accept_reward_demands(
                    token=token,
                    channel_url=channel_url,
                    demand_ids=demand_ids
                )
                print(f"Принято запросов: {len(demand_ids)}")
                
        except VKAPIError as e:
            print(f"Ошибка управления наградами: {e.error_message}")


async def example_websocket_setup():
    """Пример настройки WebSocket подключения"""
    async with VKLiveAPIClient() as client:
        token = "your_user_token"
        
        try:
            # Получить токен для WebSocket
            ws_token = await client.get_websocket_token(token=token)
            print(f"WebSocket токен получен: {ws_token[:20]}...")
            
            # Получить токены для подписки на каналы
            channels = ['chat:streamer', 'stream:streamer']
            subscription_tokens = await client.get_subscription_tokens(
                token=token,
                channels=channels
            )
            print(f"Токены подписки получены для {len(subscription_tokens)} каналов")
            
            # Теперь можно подключиться к WebSocket
            # wss://pubsub-dev.live.vkvideo.ru/connection/websocket?format=json&cf_protocol_version=v2
            # Использовать ws_token для авторизации
            # Использовать subscription_tokens для подписки на каналы
            
        except VKAPIError as e:
            print(f"Ошибка WebSocket: {e.error_message}")


async def example_error_handling():
    """Примеры обработки ошибок"""
    async with VKLiveAPIClient() as client:
        token = "your_token"
        channel_url = "streamer"
        
        # Пример 1: Обработка send_too_fast
        async def send_with_retry(message: str, max_retries: int = 3):
            for attempt in range(max_retries):
                try:
                    message_parts = [{'text': {'content': message}}]
                    await client.send_chat_message(
                        token=token,
                        channel_url=channel_url,
                        stream_id="12345",
                        message_parts=message_parts
                    )
                    print("Сообщение отправлено")
                    return
                except VKAPIError as e:
                    if e.error_code == 'send_too_fast' and attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"Слишком быстро, ждем {wait_time}с...")
                        await asyncio.sleep(wait_time)
                    else:
                        raise
        
        # Пример 2: Обработка message_too_long
        async def send_with_truncate(message: str, max_length: int = 500):
            try:
                message_parts = [{'text': {'content': message}}]
                await client.send_chat_message(
                    token=token,
                    channel_url=channel_url,
                    stream_id="12345",
                    message_parts=message_parts
                )
            except VKAPIError as e:
                if e.error_code == 'message_too_long':
                    truncated = message[:max_length] + "..."
                    print(f"Сообщение обрезано до {max_length} символов")
                    message_parts = [{'text': {'content': truncated}}]
                    await client.send_chat_message(
                        token=token,
                        channel_url=channel_url,
                        stream_id="12345",
                        message_parts=message_parts
                    )
                else:
                    raise
        
        # Пример 3: Обработка insufficient_points
        async def buy_reward_if_possible(reward_id: str):
            try:
                # Проверить баланс
                balance = await client.get_channel_points_balance(
                    token=token,
                    channel_url=channel_url
                )
                
                # Получить цену награды
                rewards = await client.get_channel_rewards(
                    token=token,
                    channel_url=channel_url
                )
                reward = next(
                    (r for r in rewards['data']['rewards'] if r['id'] == reward_id),
                    None
                )
                
                if reward and balance['data']['balance'] >= reward['price']:
                    await client.activate_reward(
                        token=token,
                        channel_url=channel_url,
                        reward_id=reward_id
                    )
                    print("Награда куплена")
                else:
                    print("Недостаточно баллов")
                    
            except VKAPIError as e:
                print(f"Ошибка покупки награды: {e.error_message}")


async def main():
    """Главная функция с примерами"""
    print("=== Примеры работы с VK Live API ===\n")
    
    print("1. Работа с чатом:")
    await example_chat_operations()
    print()
    
    print("2. Работа с баллами:")
    await example_channel_points_operations()
    print()
    
    print("3. Управление наградами:")
    await example_reward_management()
    print()
    
    print("4. Настройка WebSocket:")
    await example_websocket_setup()
    print()
    
    print("5. Обработка ошибок:")
    await example_error_handling()


if __name__ == "__main__":
    # Запустить примеры
    # asyncio.run(main())
    
    # Или запустить конкретный пример:
    # asyncio.run(example_chat_operations())
    # asyncio.run(example_channel_points_operations())
    # asyncio.run(example_reward_management())
    # asyncio.run(example_websocket_setup())
    
    print("Примеры готовы к использованию!")
    print("Раскомментируйте нужный пример и запустите скрипт")
