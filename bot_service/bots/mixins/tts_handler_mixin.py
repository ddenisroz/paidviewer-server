# features/commands/mixins/tts_handler_mixin.py
"""Mixin for TTS and Audio management commands (Voice, Mute, Volume)"""
import logging

logger = logging.getLogger(__name__)


class TTSHandlerMixin:
    """Mixin for processing TTS and Audio related commands"""

    # Expected attributes/methods from main class
    logger: logging.Logger

    async def _handle_voice(self, ctx, bot, args, platform, db):
        """Handler для !voice (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !voice <имя голоса>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Получаем настройки TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService(db)

            # Устанавливаем голос (объединяем аргументы если имя голоса состоит из нескольких слов)
            voice_name = ' '.join(args).lower() if isinstance(args, list) else args.lower()
            success = await tts_service.set_voice(user.id, voice_name, db)

            if success:
                voice_display = ' '.join(args) if isinstance(args, list) else args
                await ctx.send(f"@{ctx.author.name} [MIC] Голос изменён на: {voice_display}")
                self.logger.info(f"[OK] Voice changed to {args} for {ctx.channel.name}")
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Голос '{args}' не найден")

        except Exception as e:
            self.logger.error(f"Error in !voice handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка смены голоса")

    async def _handle_voice_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !voice (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !voice <имя голоса>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Получаем настройки TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService(db)

            # Устанавливаем голос (объединяем аргументы если имя голоса состоит из нескольких слов)
            voice_name = ' '.join(args).lower() if isinstance(args, list) else args.lower()
            success = await tts_service.set_voice(user.id, voice_name, db)

            if success:
                voice_display = ' '.join(args) if isinstance(args, list) else args
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [MIC] Голос изменён на: {voice_display}")
                self.logger.info(f"[OK] Voice changed to {args} for VK {channel_name}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Голос '{args}' не найден")

        except Exception as e:
            self.logger.error(f"Error in !voice VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка смены голоса")

    async def _handle_randomvoice(self, ctx, bot, args, platform, db):
        """Handler для !randomvoice (Twitch)"""
        try:
            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Получаем настройки TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            # Устанавливаем случайный голос
            voice_name = await tts_service.set_random_voice(user.id, db)

            if voice_name:
                await ctx.send(f"@{ctx.author.name} [DICE] Случайный голос: {voice_name}")
                self.logger.info(f"[OK] Random voice {voice_name} for {ctx.channel.name}")
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Не удалось выбрать случайный голос")

        except Exception as e:
            self.logger.error(f"Error in !randomvoice handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка выбора случайного голоса")

    async def _handle_randomvoice_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !randomvoice (VK)"""
        try:
            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Получаем настройки TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            # Устанавливаем случайный голос
            voice_name = await tts_service.set_random_voice(user.id, db)

            if voice_name:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [DICE] Случайный голос: {voice_name}")
                self.logger.info(f"[OK] Random voice {voice_name} for VK {channel_name}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Не удалось выбрать случайный голос")

        except Exception as e:
            self.logger.error(f"Error in !randomvoice VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка выбора случайного голоса")

    async def _handle_mute(self, ctx, bot, args, platform, db):
        """Handler для !mute (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !mute <username>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Блокируем пользователя для TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            target_username = args.strip().lower()
            success = tts_service.block_user(user.id, target_username, 'twitch', db)

            if success:
                await ctx.send(f"@{ctx.author.name} [MUTE] TTS отключен для: {target_username}")
                self.logger.info(f"[OK] User {target_username} muted for {ctx.channel.name}")
            else:
                await ctx.send(f"@{ctx.author.name} [WARN] Пользователь уже в списке")

        except Exception as e:
            self.logger.error(f"Error in !mute handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка блокировки пользователя")

    async def _handle_mute_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !mute (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !mute <username>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Блокируем пользователя для TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            target_username = args.strip().lower()
            success = tts_service.block_user(user.id, target_username, 'vk', db)

            if success:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [MUTE] TTS отключен для: {target_username}")
                self.logger.info(f"[OK] User {target_username} muted for VK {channel_name}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [WARN] Пользователь уже в списке")

        except Exception as e:
            self.logger.error(f"Error in !mute VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка блокировки пользователя")

    async def _handle_unmute(self, ctx, bot, args, platform, db):
        """Handler для !unmute (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !unmute <username>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Разблокируем пользователя для TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            target_username = args.strip().lower()
            success = tts_service.unblock_user(user.id, target_username, 'twitch', db)

            if success:
                await ctx.send(f"@{ctx.author.name} [VOLUME] TTS включен для: {target_username}")
                self.logger.info(f"[OK] User {target_username} unmuted for {ctx.channel.name}")
            else:
                await ctx.send(f"@{ctx.author.name} [WARN] Пользователь не найден в списке")

        except Exception as e:
            self.logger.error(f"Error in !unmute handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка разблокировки пользователя")

    async def _handle_unmute_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !unmute (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !unmute <username>")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Разблокируем пользователя для TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            target_username = args.strip().lower()
            success = tts_service.unblock_user(user.id, target_username, 'vk', db)

            if success:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [VOLUME] TTS включен для: {target_username}")
                self.logger.info(f"[OK] User {target_username} unmuted for VK {channel_name}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [WARN] Пользователь не найден в списке")

        except Exception as e:
            self.logger.error(f"Error in !unmute VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка разблокировки пользователя")

    async def _handle_ttsvolume(self, ctx, bot, args, platform, db):
        """Handler для !ttsvolume (Twitch)"""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !ttsvolume <0-100>")
                return

            try:
                volume = int(args)
                if not 0 <= volume <= 100:
                    raise ValueError
            except ValueError:
                await ctx.send(f"@{ctx.author.name} [ERROR] Громкость должна быть от 0 до 100")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            # Устанавливаем громкость TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService()

            success = await tts_service.set_volume(user.id, volume, db)

            if success:
                await ctx.send(f"@{ctx.author.name} [VOLUME] Громкость TTS: {volume}%")
                self.logger.info(f"[OK] TTS volume set to {volume}% for {ctx.channel.name}")
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Не удалось изменить громкость")

        except Exception as e:
            self.logger.error(f"Error in !ttsvolume handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка изменения громкости")

    async def _handle_ttsvolume_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !ttsvolume (VK)"""
        try:
            if not args:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Использование: !ttsvolume <0-100>")
                return

            try:
                volume = int(args)
                if not 0 <= volume <= 100:
                    raise ValueError
            except ValueError:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Громкость должна быть от 0 до 100")
                return

            # Получаем user_id владельца канала
            from repositories.user_repository import UserRepository
            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            # Устанавливаем громкость TTS
            from services.tts.tts_service import TTSService
            tts_service = TTSService(db)

            success = await tts_service.set_volume(user.id, volume, db)

            if success:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [VOLUME] Громкость TTS: {volume}%")
                self.logger.info(f"[OK] TTS volume set to {volume}% for VK {channel_name}")
            else:
                await vk_bot.send_message(channel_name,
                    f"@{author_name} [ERROR] Не удалось изменить громкость")

        except Exception as e:
            self.logger.error(f"Error in !ttsvolume VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name,
                f"@{author_name} [ERROR] Ошибка изменения громкости")
