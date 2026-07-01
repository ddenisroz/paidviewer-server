# features/commands/mixins/general_handler_mixin.py
"""Mixin for General commands (Help, YouTube Volume, Analyze)."""
import logging

logger = logging.getLogger(__name__)

HELP_STUB_TEXT = (
    "Дашборд зрителя скоро появится: там будут стрик, портрет по истории сообщений "
    "и плейлист. Пока основные команды: !sr, !queue, !skip, !voice."
)


class GeneralHandlerMixin:
    """Mixin for processing general commands."""

    logger: logging.Logger

    async def _handle_help(self, ctx, bot, args, platform, db):
        """Stub handler for !help (Twitch)."""
        try:
            await ctx.send(f"@{ctx.author.name} {HELP_STUB_TEXT}")
        except Exception as e:
            self.logger.error(f"Error in !help handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка получения списка команд")

    async def _handle_help_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Stub handler for !help (VK)."""
        try:
            await vk_bot.send_message(channel_name, f"@{author_name} {HELP_STUB_TEXT}")
        except Exception as e:
            self.logger.error(f"Error in !help VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Ошибка получения списка команд")

    async def _handle_ytvolume(self, ctx, bot, args, platform, db):
        """Handler для !ytvolume (Twitch)."""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !ytvolume <0-100>")
                return

            try:
                volume = int(args)
                if not 0 <= volume <= 100:
                    raise ValueError
            except ValueError:
                await ctx.send(f"@{ctx.author.name} [ERROR] Громкость должна быть от 0 до 100")
                return

            from repositories.user_repository import UserRepository

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            from repositories.user_settings_repository import UserSettingsRepository

            settings_repo = UserSettingsRepository(db)
            settings = settings_repo.get_or_create(user_id=user.id)
            settings_repo.update_settings(settings, {"youtube_volume": volume})
            db.commit()

            await ctx.send(f"@{ctx.author.name} [AUDIO] Громкость YouTube: {volume}%")
            self.logger.info(f"[OK] YouTube volume set to {volume}% for {ctx.channel.name}")

        except Exception as e:
            self.logger.error(f"Error in !ytvolume handler: {e}", exc_info=True)
            db.rollback()
            await ctx.send(f"@{ctx.author.name} [ERROR] Ошибка изменения громкости")

    async def _handle_ytvolume_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !ytvolume (VK)."""
        try:
            if not args:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Использование: !ytvolume <0-100>")
                return

            try:
                volume = int(args)
                if not 0 <= volume <= 100:
                    raise ValueError
            except ValueError:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Громкость должна быть от 0 до 100")
                return

            from repositories.user_repository import UserRepository

            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            from repositories.user_settings_repository import UserSettingsRepository

            settings_repo = UserSettingsRepository(db)
            settings = settings_repo.get_or_create(user_id=user.id)
            settings_repo.update_settings(settings, {"youtube_volume": volume})
            db.commit()

            await vk_bot.send_message(channel_name, f"@{author_name} [AUDIO] Громкость YouTube: {volume}%")
            self.logger.info(f"[OK] YouTube volume set to {volume}% for VK {channel_name}")

        except Exception as e:
            self.logger.error(f"Error in !ytvolume VK handler: {e}", exc_info=True)
            db.rollback()
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Ошибка изменения громкости")

    async def _handle_analyze(self, ctx, bot, args, platform, db):
        """Handler для !analyze (Twitch)."""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Использование: !analyze <username>")
                return

            target_username = args.strip().split()[0].lstrip('@')
            if not target_username:
                await ctx.send(f"@{ctx.author.name} [ERROR] Укажите пользователя для анализа")
                return

            from repositories.user_repository import UserRepository

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)

            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Канал не найден")
                return

            from services.psychology_service import PsychologyService

            service = PsychologyService(db)
            result = await service.analyze_user_psychology(
                target_username=target_username,
                platform=platform,
                analyzed_by_user_id=user.id,
                analyzed_by_username=ctx.author.name,
                channel_name=ctx.channel.name,
            )

            if result:
                await ctx.send(result)
            else:
                await ctx.send(f"@{ctx.author.name} [ERROR] Не удалось выполнить анализ")

            self.logger.info(f"!analyze completed for {target_username} on {ctx.channel.name}")
        except Exception as e:
            self.logger.error(f"Error in !analyze handler: {e}", exc_info=True)

    async def _handle_analyze_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler для !analyze (VK)."""
        try:
            if not args:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Использование: !analyze <username>")
                return

            target_username = args.strip().split()[0].lstrip('@')
            if not target_username:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Укажите пользователя для анализа")
                return

            from repositories.user_repository import UserRepository

            user = UserRepository(db).get_by_vk_username(channel_name)

            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Канал не найден")
                return

            from services.psychology_service import PsychologyService

            service = PsychologyService(db)
            result = await service.analyze_user_psychology(
                target_username=target_username,
                platform='vk',
                analyzed_by_user_id=user.id,
                analyzed_by_username=author_name,
                channel_name=channel_name,
            )

            if result:
                await vk_bot.send_message(channel_name, result)
            else:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Не удалось выполнить анализ")

            self.logger.info(f"!analyze completed for {target_username} on VK {channel_name}")
        except Exception as e:
            self.logger.error(f"Error in !analyze VK handler: {e}", exc_info=True)
