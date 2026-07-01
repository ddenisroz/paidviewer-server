# features/commands/mixins/stream_info_handler_mixin.py
"""Mixin for Stream Info management commands (Game, Title)"""
import logging

logger = logging.getLogger(__name__)


class StreamInfoHandlerMixin:
    """Mixin for processing stream info commands (game, title)"""

    # Expected attributes/methods from main class
    logger: logging.Logger

    async def _broadcast_stream_info_update(self, user_id: int, platform: str, db) -> None:
        try:
            from services.stream_info_service import StreamInfoService
            from utils.stream_info_cache import set_cached_stream_info
            from utils.websocket_broadcast import broadcast_stream_info_change

            service = StreamInfoService(db)
            info = await service.get_stream_info(user_id, platform)
            set_cached_stream_info(user_id, platform, info)
            await broadcast_stream_info_change(user_id, platform, info)
        except Exception as e:
            self.logger.warning(f"[STREAM_INFO] Broadcast failed for {platform}: {e}")

    async def _handle_game(self, ctx, bot, args, platform, db):
        """Handler для !game (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !game <название игры>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Проверяем настройку объединения категорий
            combine_categories = user.combine_categories if hasattr(user, 'combine_categories') else False

            # Ищем игру через Twitch API
            from platforms.registry import platform_registry
            from utils.category_search import expand_query_with_aliases

            twitch_platform = platform_registry.get('twitch')
            if not twitch_platform:
                await ctx.send(f"@{ctx.author.name} [ERROR] Twitch platform not available")
                return

            # Расширяем запрос с учётом алиасов (dbd -> Dead by Daylight)
            search_queries = expand_query_with_aliases(args)

            # Пробуем поиск по всем вариантам запроса
            games = None
            for search_query in search_queries:
                games = await twitch_platform.search_categories(search_query)
                if games:
                    break

            if not games:
                await ctx.send(f"@{ctx.author.name} [ERROR] Игра '{args}' не найдена")
                return

            # Берём первую найденную игру
            game = games[0]
            game_id = game.get('id')
            game_name = game.get('name', args)

            # Обновляем категорию на Twitch
            success_twitch = await twitch_platform.update_stream_category(user.id, game_id)

            results = []
            if success_twitch:
                results.append("Twitch")
                await self._broadcast_stream_info_update(user.id, "twitch", db)
                await self._broadcast_stream_info_update(user.id, "twitch", db)

            # Если включено объединение категорий И есть VK канал - обновляем и VK
            if combine_categories and user.vk_username:
                try:
                    vk_platform = platform_registry.get('vk')
                    if not vk_platform:
                        raise Exception("VK platform not available")

                    # Ищем категорию на VK используя те же алиасы
                    vk_categories = None
                    for search_query in search_queries:
                        vk_categories = await vk_platform.search_categories_for_user(search_query, user.id)
                        if vk_categories:
                            break

                    if vk_categories:
                        success_vk = await vk_platform.update_stream_category(user.id, vk_categories[0].get('id'))
                        if success_vk:
                            results.append("VK Live")
                            await self._broadcast_stream_info_update(user.id, "vk", db)
                            await self._broadcast_stream_info_update(user.id, "vk", db)
                except Exception as e:
                    self.logger.error(f"Error updating VK category: {e}")

            if results:
                platforms_text = " и ".join(results)
                await ctx.send(f"@{ctx.author.name} [OK] Игра изменена на: {game_name} ({platforms_text})")
                self.logger.info(f"[OK] Game changed to {game_name} for {platforms_text}")
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Не удалось изменить игру")

        except Exception as e:
            self.logger.error(f"Error in !game handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка изменения игры")

    async def _handle_game_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !game (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !game <название игры>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Проверяем настройку объединения категорий
            combine_categories = user.combine_categories if hasattr(user, 'combine_categories') else False

            # Ищем игру через VK API
            from platforms.registry import platform_registry
            from utils.category_search import expand_query_with_aliases

            vk_platform = platform_registry.get('vk')
            if not vk_platform:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] VK platform not available")
                return

            # Расширяем запрос с учётом алиасов (dbd -> Dead by Daylight)
            search_queries = expand_query_with_aliases(args)

            # Пробуем поиск по всем вариантам запроса
            categories = None
            for search_query in search_queries:
                categories = await vk_platform.search_categories_for_user(search_query, user.id)
                if categories:
                    break

            if not categories:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Игра '{args}' не найдена")
                return

            # Берём первую найденную игру
            category = categories[0]
            game_name = category.get('name', args)

            # Обновляем категорию на VK
            success_vk = await vk_platform.update_stream_category(user.id, category.get('id'))

            results = []
            if success_vk:
                results.append("VK Live")
                await self._broadcast_stream_info_update(user.id, "vk", db)
                await self._broadcast_stream_info_update(user.id, "vk", db)

            # Если включено объединение категорий И есть Twitch канал - обновляем и Twitch
            if combine_categories and user.twitch_username:
                try:
                    from platforms.registry import platform_registry

                    twitch_platform = platform_registry.get('twitch')
                    if not twitch_platform:
                        raise Exception("Twitch platform not available")

                    # Ищем игру на Twitch используя те же алиасы
                    games = None
                    for search_query in search_queries:
                        games = await twitch_platform.search_categories(search_query)
                        if games:
                            break

                    if games:
                        success_twitch = await twitch_platform.update_stream_category(user.id, games[0].get('id'))
                        if success_twitch:
                            results.append("Twitch")
                            await self._broadcast_stream_info_update(user.id, "twitch", db)
                except Exception as e:
                    self.logger.error(f"Error updating Twitch category: {e}")

            if results:
                platforms_text = " и ".join(results)
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [OK] Игра изменена на: {game_name} ({platforms_text})")
                self.logger.info(f"[OK] Game changed to {game_name} for {platforms_text}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Не удалось изменить игру")

        except Exception as e:
            self.logger.error(f"Error in !game VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка изменения игры")

    async def _handle_title(self, ctx, bot, args, platform, db):
        """Handler для !title (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !title <новое название>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Проверяем настройку объединения названий
            combine_titles = user.combine_titles if hasattr(user, 'combine_titles') else False

            # Обновляем название через Twitch API
            from platforms.registry import platform_registry
            twitch_platform = platform_registry.get('twitch')
            if not twitch_platform:
                await ctx.send(f"@{ctx.author.name} [ERROR] Twitch platform not available")
                return

            success_twitch = await twitch_platform.update_stream_title(user.id, args)

            results = []
            if success_twitch:
                results.append("Twitch")

            # Если включено объединение названий И есть VK канал - обновляем и VK
            if combine_titles and user.vk_username:
                try:
                    vk_platform = platform_registry.get('vk')
                    if vk_platform:
                        success_vk = await vk_platform.update_stream_title(user.id, args)
                        if success_vk:
                            results.append("VK Live")
                except Exception as e:
                    self.logger.error(f"Error updating VK title: {e}")

            if results:
                # Обрезаем название для отображения
                display_title = args[:50] + '...' if len(args) > 50 else args
                platforms_text = " и ".join(results)
                await ctx.send(f"@{ctx.author.name} [OK] Название изменено на: {display_title} ({platforms_text})")
                self.logger.info(f"[OK] Title changed for {platforms_text}")
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Не удалось изменить название")

        except Exception as e:
            self.logger.error(f"Error in !title handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка изменения названия")

    async def _handle_title_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !title (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !title <новое название>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Проверяем настройку объединения названий
            combine_titles = user.combine_titles if hasattr(user, 'combine_titles') else False

            # Обновляем название через VK API
            from platforms.registry import platform_registry
            vk_platform = platform_registry.get('vk')
            if not vk_platform:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] VK platform not available")
                return

            success_vk = await vk_platform.update_stream_title(user.id, args)

            results = []
            if success_vk:
                results.append("VK Live")

            # Если включено объединение названий И есть Twitch канал - обновляем и Twitch
            if combine_titles and user.twitch_username:
                try:
                    from platforms.registry import platform_registry

                    twitch_platform = platform_registry.get('twitch')
                    if not twitch_platform:
                        raise Exception("Twitch platform not available")

                    success_twitch = await twitch_platform.update_stream_title(user.id, args)
                    if success_twitch:
                        results.append("Twitch")
                        await self._broadcast_stream_info_update(user.id, "twitch", db)
                except Exception as e:
                    self.logger.error(f"Error updating Twitch title: {e}")

            if results:
                # Обрезаем название для отображения
                display_title = args[:50] + '...' if len(args) > 50 else args
                platforms_text = " и ".join(results)
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [OK] Название изменено на: {display_title} ({platforms_text})")
                self.logger.info(f"[OK] Title changed for {platforms_text}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Не удалось изменить название")

        except Exception as e:
            self.logger.error(f"Error in !title VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка изменения названия")
