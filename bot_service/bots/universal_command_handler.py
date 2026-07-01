# bot_service/bots/universal_command_handler.py
"""Универсальный обработчик команд для Twitch и VK Live"""
import logging
import re
from typing import Optional, Any, Dict
from core.datetime_utils import utcnow_naive
from services.command_service import CommandService
from core.database import get_db, BotCommand, StreamSession, UserStreak
from utils.platform_role_checker import PlatformRoleChecker
from repositories.command_repository import CommandRepository

# Import Mixins
from bots.mixins.queue_handler_mixin import QueueHandlerMixin
from bots.mixins.stream_info_handler_mixin import StreamInfoHandlerMixin
from bots.mixins.tts_handler_mixin import TTSHandlerMixin
from bots.mixins.general_handler_mixin import GeneralHandlerMixin
from bots.mixins.memealerts_handler_mixin import MemeAlertsHandlerMixin

logger = logging.getLogger('bot_service')

class UniversalCommandHandler(
    QueueHandlerMixin,
    StreamInfoHandlerMixin,
    TTSHandlerMixin,
    GeneralHandlerMixin,
    MemeAlertsHandlerMixin,
):
    """Универсальный обреботчик команд с поддержкой глобальных команд, overrides и кастомных
    
    Inherits functionality from:
    - QueueHandlerMixin: !sr, !skip, !clear, !queue, !wronglink
    - StreamInfoHandlerMixin: !game, !title
    - TTSHandlerMixin: !voice, !randomvoice, !mute, !unmute, !ttsvolume
    - GeneralHandlerMixin: !help, !ytvolume, !analyze
    """

    def __init__(self):
        self.command_service = CommandService()
        self.role_checker = PlatformRoleChecker()
        # self.cooldowns is managed by CommandService now, but keeping local if needed for legacy mixins
        # Ideally mixins should use command_service too.
        # For now, let's proxy calls to command_service.
        self.logger = logging.getLogger('commands')
        self._timer_last_run: Dict[str, Any] = {}
        self._recent_command_response: Dict[str, Any] = {}

    def _has_fallback_permission(self, command_name: str, user_roles: list[str]) -> bool:
        """Lightweight permission checks for core commands when DB is missing."""
        cmd = command_name.lower()
        if cmd in {'skip', 'clear'}:
            return any(role in {'broadcaster', 'owner', 'moderator', 'mod'} for role in user_roles)
        return True


    async def handle_twitch_command(self, ctx: Any, bot: Any):
        """
        Обработка команды из Twitch чата
        
        Args:
            ctx: TwitchIO Context
            bot: TwitchBot экземпляр
        """
        try:
            message_content = ctx.message.content.strip()

            # Проверяем что это команда
            if not message_content.startswith('!'):
                return

            # Парсим команду
            parts = message_content[1:].split(maxsplit=1)
            if not parts:
                return

            command_name = parts[0].lower()
            command_args = parts[1] if len(parts) > 1 else ""

            # Получаем роли пользователя
            user_roles = self.role_checker.get_twitch_roles(ctx.author, ctx.channel.name)
            is_broadcaster = self.role_checker.is_broadcaster(user_roles)

            # Получаем user_id владельца канала
            channel_owner_id = await self._get_channel_owner_id_twitch(ctx.channel.name)
            if not channel_owner_id:
                self.logger.warning(f"Channel owner not found for {ctx.channel.name}")
                return

            # Ищем команду в БД
            db = next(get_db())
            try:
                command = self.command_service.find_command(
                    command_name=command_name,
                    user_id=channel_owner_id,
                    channel_name=ctx.channel.name,
                    platform='twitch',
                    db=db
                )

                if not command:
                    self.logger.debug(f"Command not found: !{command_name}")
                    fallback_core_commands = {'help', 'sr', 'queue', 'wronglink', 'skip', 'clear'}
                    if command_name in fallback_core_commands:
                        if not self._has_fallback_permission(command_name, user_roles):
                            await ctx.send(f"@{ctx.author.name} [ERROR] You do not have permission to use this command")
                            return
                        handler_name = f"_handle_{command_name}"
                        if hasattr(self, handler_name):
                            await getattr(self, handler_name)(ctx, bot, command_args, 'twitch', db)
                        return
                    return

                # Проверяем права
                # Note: pass user=None as we use user_roles list for compat
                if not self.command_service.check_permission(command, None, 'twitch', user_roles):
                    await ctx.send(f"@{ctx.author.name} [ERROR] You do not have permission to use this command")
                    return

                if command.command_type == 'custom' and not self._check_command_conditions(
                    command=command,
                    db=db,
                    owner_id=channel_owner_id,
                    channel_name=ctx.channel.name,
                    platform='twitch',
                    viewer_id=str(ctx.author.id),
                ):
                    return

                # Проверяем кулдаун
                if not is_broadcaster:  # Broadcaster игнорирует кулдауны
                    if not self.command_service.check_cooldown(command, str(ctx.author.id)):
                        # CommandService doesn't expose remaining time easily currently, or does it?
                        # It returns bool. Let's look at implementation.
                        # It doesn't have get_remaining. We should add it or accept generic message.
                        await ctx.send(f"@{ctx.author.name} [TIMEOUT] Команда на кулдауне.")
                        return
                    else:
                        # Update cooldown upon successful check (or should it be after execution?)
                        # Typically updated after execution starts.
                        self.command_service.update_cooldown(command, str(ctx.author.id))

                # Выполняем команду
                await self._execute_command(
                    command=command,
                    ctx=ctx,
                    bot=bot,
                    args=command_args,
                    used_trigger=command_name,
                    owner_id=channel_owner_id,
                    platform='twitch',
                    db=db,
                    channel_key=f"twitch:{ctx.channel.name}",
                )

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error handling Twitch command: {e}", exc_info=True)

    async def handle_vk_command(self, channel_name: str, message_data: Dict, vk_bot: Any):
        """
        Обработка команды из VK Live чата
        
        Args:
            channel_name: Название канала VK
            message_data: Данные сообщения
            vk_bot: VKLiveBot экземпляр
        """
        try:
            message = message_data.get('message', '').strip()
            self.logger.info(f"[DEBUG] [VK CMD HANDLER] Processing: {message}")

            # Проверяем что это команда
            if not message.startswith('!'):
                self.logger.warning(f"[DEBUG] [VK CMD HANDLER] Not a command: {message}")
                return

            # Парсим команду
            parts = message[1:].split(maxsplit=1)
            if not parts:
                self.logger.warning("[DEBUG] [VK CMD HANDLER] Empty command")
                return

            command_name = parts[0].lower()
            command_args = parts[1] if len(parts) > 1 else ""
            self.logger.info(f"[DEBUG] [VK CMD HANDLER] Command: !{command_name}, Args: '{command_args}'")

            # Получаем роли пользователя
            author_data = {
                'is_owner': message_data.get('is_owner', False),
                'is_moderator': message_data.get('is_moderator', False),
                'name': message_data.get('author_nick', 'Unknown')
            }
            user_roles = self.role_checker.get_vk_roles(author_data, channel_name)
            is_broadcaster = self.role_checker.is_broadcaster(user_roles)

            # Получаем user_id владельца канала
            channel_owner_id = await self._get_channel_owner_id_vk(channel_name)
            if not channel_owner_id:
                self.logger.warning(f"Channel owner not found for VK {channel_name}")
                return

            # Ищем команду в БД
            db = next(get_db())
            try:
                command = self.command_service.find_command(
                    command_name=command_name,
                    user_id=channel_owner_id,
                    channel_name=channel_name,
                    platform='vk',
                    db=db
                )

                author_id = str(message_data.get('author_id', ''))

                if not command:
                    self.logger.debug(f"Command not found: !{command_name}")
                    fallback_core_commands_vk = {'help', 'sr', 'queue', 'wronglink', 'skip', 'clear'}
                    if command_name in fallback_core_commands_vk:
                        if not self._has_fallback_permission(command_name, user_roles):
                            await vk_bot.send_message(channel_name, f"@{author_data['name']} [ERROR] You do not have permission to use this command")
                            return
                        handler_name = f"_handle_{command_name}_vk"
                        if hasattr(self, handler_name):
                            await getattr(self, handler_name)(channel_name, author_data['name'], author_id, command_args, vk_bot, message_data, db)
                        return
                    return

                # Проверяем права
                if not self.command_service.check_permission(command, None, 'vk', user_roles):
                    await vk_bot.send_message(channel_name,
                        f"@{author_data['name']} [ERROR] У вас нет прав на использование этой команды")
                    return

                if command.command_type == 'custom' and not self._check_command_conditions(
                    command=command,
                    db=db,
                    owner_id=channel_owner_id,
                    channel_name=channel_name,
                    platform='vk',
                    viewer_id=author_id,
                ):
                    return

                # Проверяем кулдаун
                if not is_broadcaster:
                    if not self.command_service.check_cooldown(command, author_id):
                        await vk_bot.send_message(channel_name,
                            f"@{author_data['name']} [TIMEOUT] Команда на кулдауне.")
                        return
                    else:
                        self.command_service.update_cooldown(command, author_id)

                # Выполняем команду
                await self._execute_command_vk(
                    command=command,
                    channel_name=channel_name,
                    author_name=author_data['name'],
                    author_id=author_id,
                    args=command_args,
                    used_trigger=command_name,
                    owner_id=channel_owner_id,
                    vk_bot=vk_bot,
                    message_data=message_data,
                    db=db,
                    channel_key=f"vk:{channel_name}",
                )

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error handling VK command: {e}", exc_info=True)

    async def _execute_command(
        self,
        command: BotCommand,
        ctx: Any,
        bot: Any,
        args: str,
        used_trigger: str,
        owner_id: int,
        platform: str,
        db: Any,
        channel_key: str,
    ):
        """Выполнить команду (Twitch)"""
        try:
            # Для команд с response_text просто отправляем ответ
            if command.response_text:
                if self._is_anti_spam_blocked(command, channel_key):
                    return
                await ctx.send(command.response_text)
                self._mark_response_sent(command, channel_key)
                self._mark_command_used(
                    command,
                    db,
                    owner_id=owner_id,
                    used_trigger=used_trigger,
                    platform=platform,
                    channel_name=getattr(ctx.channel, "name", None),
                    viewer_name=getattr(ctx.author, "name", None),
                    viewer_id=str(getattr(ctx.author, "id", "")),
                    message_text=getattr(ctx.message, "content", None),
                )
                self.logger.info(f"[OK] Executed text command: !{command.command_name}")
                return

            # Для специальных команд используем handlers (lookups on self which includes mixins)
            handler_name = f"_handle_{command.command_name}"
            if hasattr(self, handler_name):
                handler = getattr(self, handler_name)
                await handler(ctx, bot, args, platform, db)
                self._mark_command_used(
                    command,
                    db,
                    owner_id=owner_id,
                    used_trigger=used_trigger,
                    platform=platform,
                    channel_name=getattr(ctx.channel, "name", None),
                    viewer_name=getattr(ctx.author, "name", None),
                    viewer_id=str(getattr(ctx.author, "id", "")),
                    message_text=getattr(ctx.message, "content", None),
                )
            else:
                self.logger.warning(f"No handler for command: !{command.command_name}")

        except Exception as e:
            self.logger.error(f"Error executing command: {e}", exc_info=True)
            await ctx.send("[ERROR] Ошибка выполнения команды")

    async def _execute_command_vk(
        self,
        command: BotCommand,
        channel_name: str,
        author_name: str,
        author_id: str,
        args: str,
        used_trigger: str,
        owner_id: int,
        vk_bot: Any,
        message_data: Dict,
        db: Any,
        channel_key: str,
    ):
        """Выполнить команду (VK)"""
        try:
            # Для команд с response_text просто отправляем ответ
            if command.response_text:
                if self._is_anti_spam_blocked(command, channel_key):
                    return
                await vk_bot.send_message(channel_name, command.response_text)
                self._mark_response_sent(command, channel_key)
                self._mark_command_used(
                    command,
                    db,
                    owner_id=owner_id,
                    used_trigger=used_trigger,
                    platform="vk",
                    channel_name=channel_name,
                    viewer_name=author_name,
                    viewer_id=author_id,
                    message_text=message_data.get("message"),
                )
                self.logger.info(f"[OK] Executed text command: !{command.command_name}")
                return

            # Для специальных команд используем handlers (lookups on self which includes mixins)
            handler_name = f"_handle_{command.command_name}_vk"
            if hasattr(self, handler_name):
                handler = getattr(self, handler_name)
                await handler(channel_name, author_name, author_id, args, vk_bot, message_data, db)
                self._mark_command_used(
                    command,
                    db,
                    owner_id=owner_id,
                    used_trigger=used_trigger,
                    platform="vk",
                    channel_name=channel_name,
                    viewer_name=author_name,
                    viewer_id=author_id,
                    message_text=message_data.get("message"),
                )
            else:
                self.logger.warning(f"No handler for command: !{command.command_name}")

        except Exception as e:
            self.logger.error(f"Error executing VK command: {e}", exc_info=True)
            await vk_bot.send_message(channel_name, "[ERROR] Ошибка выполнения команды")

    def _extract_trigger_settings(self, command: BotCommand) -> tuple[str, str, int]:
        extra_settings = command.extra_settings or {}
        mode = str(extra_settings.get("trigger_mode") or "command").lower()
        keyword = str(extra_settings.get("trigger_keyword") or "").strip()
        try:
            interval = int(extra_settings.get("timer_interval_seconds") or 300)
        except (TypeError, ValueError):
            interval = 300
        interval = max(15, min(interval, 3600))
        if mode not in {"command", "keyword", "timer"}:
            mode = "command"
        return mode, keyword, interval

    @staticmethod
    def _extract_priority(command: BotCommand) -> int:
        extra_settings = command.extra_settings or {}
        try:
            priority = int(extra_settings.get("priority") or 0)
        except (TypeError, ValueError):
            priority = 0
        return max(0, min(priority, 100))

    @staticmethod
    def _extract_anti_spam_window(command: BotCommand) -> int:
        extra_settings = command.extra_settings or {}
        try:
            window = int(extra_settings.get("anti_spam_window_seconds") or 0)
        except (TypeError, ValueError):
            window = 0
        return max(0, min(window, 600))

    @staticmethod
    def _extract_conditions(command: BotCommand) -> tuple[bool, int]:
        extra_settings = command.extra_settings or {}
        live_only = bool(extra_settings.get("condition_live_only", False))
        try:
            min_streak_days = int(extra_settings.get("condition_min_streak_days") or 0)
        except (TypeError, ValueError):
            min_streak_days = 0
        return live_only, max(0, min(min_streak_days, 365))

    @staticmethod
    def _keyword_match(text: str, keyword: str) -> bool:
        if not keyword:
            return False
        pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
        return re.search(pattern, text, re.IGNORECASE) is not None

    def _should_run_timer(self, command: BotCommand, channel_key: str, interval_seconds: int) -> bool:
        timer_key = f"{channel_key}:{command.id}"
        now = utcnow_naive()
        last_run = self._timer_last_run.get(timer_key)
        if last_run is None:
            self._timer_last_run[timer_key] = now
            return True
        if (now - last_run).total_seconds() >= interval_seconds:
            self._timer_last_run[timer_key] = now
            return True
        return False

    def _is_anti_spam_blocked(self, command: BotCommand, channel_key: str) -> bool:
        anti_spam_window = self._extract_anti_spam_window(command)
        if anti_spam_window <= 0:
            return False
        key = f"{channel_key}:{command.id}"
        last_sent = self._recent_command_response.get(key)
        if not last_sent:
            return False
        return (utcnow_naive() - last_sent).total_seconds() < anti_spam_window

    def _mark_response_sent(self, command: BotCommand, channel_key: str):
        self._recent_command_response[f"{channel_key}:{command.id}"] = utcnow_naive()

    @staticmethod
    def _is_stream_live(db: Any, owner_id: int, channel_name: str, platform: str) -> bool:
        return (
            db.query(StreamSession)
            .filter(
                StreamSession.user_id == owner_id,
                StreamSession.channel_name == channel_name,
                StreamSession.platform == platform,
                StreamSession.is_active.is_(True),
            )
            .first()
            is not None
        )

    @staticmethod
    def _viewer_streak_days(
        db: Any,
        owner_id: int,
        channel_name: str,
        platform: str,
        viewer_id: Optional[str],
    ) -> int:
        if not viewer_id:
            return 0
        streak = (
            db.query(UserStreak)
            .filter(
                UserStreak.user_id == owner_id,
                UserStreak.channel_name == channel_name,
                UserStreak.platform == platform,
                UserStreak.viewer_id == str(viewer_id),
            )
            .first()
        )
        return int(getattr(streak, "current_streak", 0) or 0)

    def _check_command_conditions(
        self,
        command: BotCommand,
        db: Any,
        owner_id: int,
        channel_name: str,
        platform: str,
        viewer_id: Optional[str] = None,
    ) -> bool:
        live_only, min_streak_days = self._extract_conditions(command)
        if live_only and not self._is_stream_live(db, owner_id, channel_name, platform):
            return False
        if min_streak_days > 0 and viewer_id:
            if self._viewer_streak_days(db, owner_id, channel_name, platform, viewer_id) < min_streak_days:
                return False
        return True

    @staticmethod
    def _mark_command_used(
        command: BotCommand,
        db: Any,
        *,
        owner_id: Optional[int] = None,
        used_trigger: Optional[str] = None,
        platform: Optional[str] = None,
        channel_name: Optional[str] = None,
        viewer_name: Optional[str] = None,
        viewer_id: Optional[str] = None,
        message_text: Optional[str] = None,
        chat_message_id: Optional[int] = None,
        status: str = "success",
        error: Optional[str] = None,
    ):
        command.last_used = utcnow_naive()
        command.usage_count = int(command.usage_count or 0) + 1
        if owner_id:
            try:
                CommandRepository(db).create_invocation(
                    user_id=owner_id,
                    command_id=command.id,
                    canonical_command_name=command.command_name,
                    used_trigger=used_trigger or command.command_name,
                    platform=platform or "",
                    channel_name=channel_name,
                    viewer_name=viewer_name,
                    viewer_id=viewer_id,
                    message_text=message_text,
                    chat_message_id=chat_message_id,
                    status=status,
                    error=error,
                )
            except Exception:
                logger.exception("Failed to record command invocation for !%s", command.command_name)
        db.commit()

    async def handle_twitch_message(self, message: Any, bot: Any):
        """Handle non-command custom triggers for Twitch."""
        text = (message.content or "").strip()
        if not text or text.startswith("!"):
            return

        channel_name = message.channel.name
        channel_owner_id = await self._get_channel_owner_id_twitch(channel_name)
        if not channel_owner_id:
            return

        db = next(get_db())
        try:
            repo = CommandRepository(db)
            user_roles = self.role_checker.get_twitch_roles(message.author, channel_name)
            commands = [
                cmd for cmd in repo.get_user_custom_commands(channel_owner_id)
                if cmd.is_enabled and repo._check_platform(cmd, "twitch")
            ]
            commands.sort(key=lambda cmd: (self._extract_priority(cmd), int(cmd.id or 0)), reverse=True)
            for command in commands:
                if not self._check_command_conditions(
                    command=command,
                    db=db,
                    owner_id=channel_owner_id,
                    channel_name=channel_name,
                    platform='twitch',
                    viewer_id=str(message.author.id),
                ):
                    continue
                mode, keyword, interval_seconds = self._extract_trigger_settings(command)
                if mode == "keyword":
                    if not self._keyword_match(text, keyword):
                        continue
                    if not self.command_service.check_permission(command, None, 'twitch', user_roles):
                        continue
                    if not self.command_service.check_cooldown(command, str(message.author.id)):
                        continue
                    if self._is_anti_spam_blocked(command, f"twitch:{channel_name}"):
                        continue
                    self.command_service.update_cooldown(command, str(message.author.id))
                    await message.channel.send(command.response_text or "")
                    self._mark_response_sent(command, f"twitch:{channel_name}")
                    self._mark_command_used(
                        command,
                        db,
                        owner_id=channel_owner_id,
                        used_trigger=keyword,
                        platform="twitch",
                        channel_name=channel_name,
                        viewer_name=getattr(message.author, "name", None),
                        viewer_id=str(getattr(message.author, "id", "")),
                        message_text=text,
                    )
                    return
                if mode == "timer":
                    if not self._should_run_timer(command, f"twitch:{channel_name}", interval_seconds):
                        continue
                    if self._is_anti_spam_blocked(command, f"twitch:{channel_name}"):
                        continue
                    await message.channel.send(command.response_text or "")
                    self._mark_response_sent(command, f"twitch:{channel_name}")
                    self._mark_command_used(
                        command,
                        db,
                        owner_id=channel_owner_id,
                        used_trigger="timer",
                        platform="twitch",
                        channel_name=channel_name,
                        viewer_name=None,
                        viewer_id=None,
                        message_text=None,
                    )
                    return
        finally:
            db.close()

    async def handle_vk_message(self, channel_name: str, message_data: Dict, vk_bot: Any):
        """Handle non-command custom triggers for VK Live."""
        text = (message_data.get("message") or "").strip()
        if not text or text.startswith("!"):
            return

        channel_owner_id = await self._get_channel_owner_id_vk(channel_name)
        if not channel_owner_id:
            return

        author_id = str(message_data.get('author_id', ''))
        author_data = {
            'is_owner': message_data.get('is_owner', False),
            'is_moderator': message_data.get('is_moderator', False),
            'name': message_data.get('author_nick', 'Unknown')
        }
        user_roles = self.role_checker.get_vk_roles(author_data, channel_name)

        db = next(get_db())
        try:
            repo = CommandRepository(db)
            commands = [
                cmd for cmd in repo.get_user_custom_commands(channel_owner_id)
                if cmd.is_enabled and repo._check_platform(cmd, "vk")
            ]
            commands.sort(key=lambda cmd: (self._extract_priority(cmd), int(cmd.id or 0)), reverse=True)
            for command in commands:
                if not self._check_command_conditions(
                    command=command,
                    db=db,
                    owner_id=channel_owner_id,
                    channel_name=channel_name,
                    platform='vk',
                    viewer_id=author_id,
                ):
                    continue
                mode, keyword, interval_seconds = self._extract_trigger_settings(command)
                if mode == "keyword":
                    if not self._keyword_match(text, keyword):
                        continue
                    if not self.command_service.check_permission(command, None, 'vk', user_roles):
                        continue
                    if not self.command_service.check_cooldown(command, author_id):
                        continue
                    if self._is_anti_spam_blocked(command, f"vk:{channel_name}"):
                        continue
                    self.command_service.update_cooldown(command, author_id)
                    await vk_bot.send_message(channel_name, command.response_text or "")
                    self._mark_response_sent(command, f"vk:{channel_name}")
                    self._mark_command_used(
                        command,
                        db,
                        owner_id=channel_owner_id,
                        used_trigger=keyword,
                        platform="vk",
                        channel_name=channel_name,
                        viewer_name=author_data["name"],
                        viewer_id=author_id,
                        message_text=text,
                    )
                    return
                if mode == "timer":
                    if not self._should_run_timer(command, f"vk:{channel_name}", interval_seconds):
                        continue
                    if self._is_anti_spam_blocked(command, f"vk:{channel_name}"):
                        continue
                    await vk_bot.send_message(channel_name, command.response_text or "")
                    self._mark_response_sent(command, f"vk:{channel_name}")
                    self._mark_command_used(
                        command,
                        db,
                        owner_id=channel_owner_id,
                        used_trigger="timer",
                        platform="vk",
                        channel_name=channel_name,
                        viewer_name=None,
                        viewer_id=None,
                        message_text=None,
                    )
                    return
        finally:
            db.close()

    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===

    async def _get_channel_owner_id_twitch(self, channel_name: str) -> Optional[int]:
        """Получить user_id владельца Twitch канала"""
        try:
            db = next(get_db())
            try:
                from repositories.user_repository import UserRepository
                user = UserRepository(db).get_by_twitch_username(channel_name)
                return user.id if user else None
            finally:
                db.close()
        except Exception as e:
            self.logger.error(f"Error getting Twitch channel owner ID: {e}")
            return None

    async def _get_channel_owner_id_vk(self, channel_name: str) -> Optional[int]:
        """Получить user_id владельца VK канала"""
        try:
            db = next(get_db())
            try:
                from repositories.user_repository import UserRepository
                repo = UserRepository(db)
                # Сначала ищем по vk_channel_name (правильное поле)
                user = repo.get_by_vk_channel_name(channel_name)
                if user:
                    return user.id

                # Fallback: ищем по vk_username для обратной совместимости
                user = repo.get_by_vk_username(channel_name)
                return user.id if user else None
            finally:
                db.close()
        except Exception as e:
            self.logger.error(f"Error getting VK channel owner ID: {e}")
            return None

    # _check_cooldown and _get_cooldown_remaining are deprecated replaced by CommandService
