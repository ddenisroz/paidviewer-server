# features/commands/mixins/queue_handler_mixin.py
"""Mixin for queue-related bot commands."""

import logging

logger = logging.getLogger(__name__)


class QueueHandlerMixin:
    """Mixin for processing queue-related commands (sr, skip, clear, wronglink, queue)."""

    logger: logging.Logger

    @staticmethod
    def _get_skip_votes_required(command_repo, owner_id: int) -> int:
        skip_votes_required = 1
        override = command_repo.get_override_by_name("skip", owner_id)
        if override and override.extra_settings:
            try:
                skip_votes_required = int(override.extra_settings.get("skip_votes_required", 1) or 1)
            except (TypeError, ValueError):
                skip_votes_required = 1
        return max(1, skip_votes_required)

    @staticmethod
    def _get_vk_owner(repo, channel_name: str):
        return repo.get_by_vk_channel_name(channel_name) or repo.get_by_vk_username(channel_name)

    async def _handle_sr(self, ctx, bot, args, platform, db):
        """Handler for !sr (Song Request)."""
        try:
            if not args:
                await ctx.send(f"@{ctx.author.name} [ERROR] Usage: !sr <YouTube URL or ID>")
                return

            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)
            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            result = await queue_service.add_video_to_queue(
                user_id=user.id,
                video_url=args,
                channel_name=ctx.channel.name,
                platform="twitch",
                requester_name=ctx.author.name,
                requester_id=str(getattr(ctx.author, "id", ctx.author.name)),
                is_paid=False,
                db=db,
            )

            if result.get("success"):
                queue_item = result.get("queue_item", {})
                await ctx.send(
                    f"[OK] @{ctx.author.name} Added to queue: {queue_item.get('title', 'video')} "
                    f"(pos {queue_item.get('position', '?')}, {queue_item.get('duration', 'Unknown')})"
                )
            else:
                await ctx.send(f"[ERROR] @{ctx.author.name} {result.get('error')}")

        except Exception as e:
            self.logger.error(f"Error in !sr handler: {e}")
            await ctx.send(f"@{ctx.author.name} [ERROR] Failed to add video")

    async def _handle_sr_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler for !sr in VK."""
        try:
            if not args:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Usage: !sr <YouTube URL>")
                return

            from services.youtube.queue_service import QueueService

            channel_owner_id = await self._get_channel_owner_id_vk(channel_name)
            if not channel_owner_id:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Channel is not registered")
                return

            queue_service = QueueService()
            result = await queue_service.add_video_to_queue(
                user_id=channel_owner_id,
                video_url=args,
                channel_name=channel_name,
                platform="vk",
                requester_name=author_name,
                requester_id=author_id,
                is_paid=False,
                db=db,
            )

            if result.get("success"):
                queue_item = result["queue_item"]
                await vk_bot.send_message(
                    channel_name,
                    f"[OK] @{author_name} Added to queue: {queue_item['title']} "
                    f"(position {queue_item['position']}, {queue_item.get('duration', 'Unknown')})",
                )
            else:
                await vk_bot.send_message(channel_name, f"[ERROR] @{author_name} {result['error']}")

        except Exception as e:
            self.logger.error(f"Error in VK song request: {e}")
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Failed to add video")

    async def _handle_skip(self, ctx, bot, args, platform, db):
        """Handler for !skip in Twitch chat."""
        try:
            from repositories.command_repository import CommandRepository
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService
            from services.youtube.skip_vote_store import skip_vote_store

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)
            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            current_video = await queue_service.get_current_video(user.id, db=db)
            if not current_video:
                await ctx.send(f"@{ctx.author.name} [INFO] Queue is empty")
                return

            skip_votes_required = self._get_skip_votes_required(CommandRepository(db), user.id)
            video_key = current_video.get("id") or current_video.get("video_id")
            voter_id = getattr(ctx.author, "id", None) or ctx.author.name
            current_votes, added = skip_vote_store.add_vote(user.id, video_key, voter_id)
            if not added:
                await ctx.send(f"@{ctx.author.name} [INFO] You already voted to skip")
                return

            if current_votes >= skip_votes_required:
                result = await queue_service.skip_current(user.id, db=db)
                if result.get("success"):
                    skip_vote_store.clear_owner(user.id)
                    await ctx.send(f"[SKIP] Video skipped! ({current_votes}/{skip_votes_required} votes)")
                    self.logger.info(f"[OK] Vote skip reached for {ctx.channel.name}")
                else:
                    await ctx.send(f"@{ctx.author.name} [ERROR] {result.get('error', 'Failed to skip video')}")
                return

            remaining = skip_votes_required - current_votes
            await ctx.send(
                f"[VOTE] @{ctx.author.name} voted to skip ({current_votes}/{skip_votes_required}). "
                f"{remaining} more needed."
            )

        except Exception as e:
            self.logger.error(f"Error in !skip handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Failed to skip video")

    async def _handle_skip_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler for !skip in VK."""
        try:
            from repositories.command_repository import CommandRepository
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService
            from services.youtube.skip_vote_store import skip_vote_store

            repo = UserRepository(db)
            user = self._get_vk_owner(repo, channel_name)
            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            current_video = await queue_service.get_current_video(user.id, db=db)
            if not current_video:
                await vk_bot.send_message(channel_name, f"@{author_name} [INFO] Queue is empty")
                return

            skip_votes_required = self._get_skip_votes_required(CommandRepository(db), user.id)
            video_key = current_video.get("id") or current_video.get("video_id")
            voter_id = author_id or author_name
            current_votes, added = skip_vote_store.add_vote(user.id, video_key, voter_id)
            if not added:
                await vk_bot.send_message(channel_name, f"@{author_name} [INFO] You already voted to skip")
                return

            if current_votes >= skip_votes_required:
                result = await queue_service.skip_current(user.id, db=db)
                if result.get("success"):
                    skip_vote_store.clear_owner(user.id)
                    await vk_bot.send_message(channel_name, f"[SKIP] Video skipped! ({current_votes}/{skip_votes_required} votes)")
                    self.logger.info(f"[OK] Vote skip reached for VK {channel_name}")
                else:
                    await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] {result.get('error', 'Failed to skip video')}")
                return

            remaining = skip_votes_required - current_votes
            await vk_bot.send_message(
                channel_name,
                f"[VOTE] @{author_name} voted to skip ({current_votes}/{skip_votes_required}). {remaining} more needed.",
            )

        except Exception as e:
            self.logger.error(f"Error in !skip VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Failed to skip video")

    async def _handle_clear(self, ctx, bot, args, platform, db):
        """Handler for !clear in Twitch."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)
            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            deleted_count = queue_service.clear_queue(user.id, db=db)

            if deleted_count > 0:
                await ctx.send(f"@{ctx.author.name} [DELETE] Queue cleared ({deleted_count} videos)")
                self.logger.info(f"[OK] Queue cleared for {ctx.channel.name}: {deleted_count} videos")
            else:
                await ctx.send(f"@{ctx.author.name} [INFO] Queue is already empty")

        except Exception as e:
            self.logger.error(f"Error in !clear handler: {e}", exc_info=True)
            db.rollback()
            await ctx.send(f"@{ctx.author.name} [ERROR] Failed to clear queue")

    async def _handle_clear_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler for !clear in VK."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            repo = UserRepository(db)
            user = self._get_vk_owner(repo, channel_name)
            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            deleted_count = queue_service.clear_queue(user.id, db=db)

            if deleted_count > 0:
                await vk_bot.send_message(channel_name, f"@{author_name} [DELETE] Queue cleared ({deleted_count} videos)")
                self.logger.info(f"[OK] Queue cleared for VK {channel_name}: {deleted_count} videos")
            else:
                await vk_bot.send_message(channel_name, f"@{author_name} [INFO] Queue is already empty")

        except Exception as e:
            self.logger.error(f"Error in !clear VK handler: {e}", exc_info=True)
            db.rollback()
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Failed to clear queue")

    async def _handle_queue(self, ctx, bot, args, platform, db):
        """Handler for !queue in Twitch."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)
            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            queue = queue_service.get_user_queue(user.id, db=db)
            if not queue:
                await ctx.send(f"@{ctx.author.name} [INFO] Queue is empty")
                return

            queue_list = []
            for i, video in enumerate(queue[:5], 1):
                title = video["title"][:50] + "..." if len(video["title"]) > 50 else video["title"]
                queue_list.append(f"{i}. {title}")

            queue_text = " | ".join(queue_list)
            total = len(queue)
            if total > 5:
                await ctx.send(f"[LIST] Queue ({total} videos): {queue_text} and {total - 5} more...")
            else:
                await ctx.send(f"[LIST] Queue ({total} videos): {queue_text}")

        except Exception as e:
            self.logger.error(f"Error in !queue handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Failed to get queue")

    async def _handle_wronglink(self, ctx, bot, args, platform, db):
        """Handler for !wronglink in Twitch."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            user = UserRepository(db).get_by_twitch_username(ctx.channel.name)
            if not user:
                await ctx.send(f"@{ctx.author.name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            result = queue_service.remove_last_user_video(
                user_id=user.id,
                requester_id=str(ctx.author.id),
                requester_name=ctx.author.name,
                platform="twitch",
                db=db,
            )

            if result["success"]:
                refund_msg = ""
                if result.get("refunded"):
                    refund_msg = f" ({result['points_refunded']} points refunded)"
                await ctx.send(f"{result['message']}{refund_msg}")
            else:
                await ctx.send(result["error"])

        except Exception as e:
            self.logger.error(f"Error in !wronglink handler: {e}", exc_info=True)
            await ctx.send(f"@{ctx.author.name} [ERROR] Failed to remove video")

    async def _handle_wronglink_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler for !wronglink in VK."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            repo = UserRepository(db)
            user = self._get_vk_owner(repo, channel_name)
            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            result = queue_service.remove_last_user_video(
                user_id=user.id,
                requester_id=str(author_id),
                requester_name=author_name,
                platform="vk",
                db=db,
            )

            if result["success"]:
                refund_msg = ""
                if result.get("refunded"):
                    refund_msg = f" ({result['points_refunded']} points refunded)"
                await vk_bot.send_message(channel_name, f"{result['message']}{refund_msg}")
            else:
                await vk_bot.send_message(channel_name, result["error"])

        except Exception as e:
            self.logger.error(f"Error in !wronglink VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Failed to remove video")

    async def _handle_queue_vk(self, channel_name, author_name, author_id, args, vk_bot, message_data, db):
        """Handler for !queue in VK."""
        try:
            from repositories.user_repository import UserRepository
            from services.youtube.queue_service import QueueService

            repo = UserRepository(db)
            user = self._get_vk_owner(repo, channel_name)
            if not user:
                await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Channel not found")
                return

            queue_service = QueueService()
            queue = queue_service.get_user_queue(user.id, db=db)
            if not queue:
                await vk_bot.send_message(channel_name, f"@{author_name} [INFO] Queue is empty")
                return

            queue_list = []
            for i, video in enumerate(queue[:5], 1):
                title = video["title"][:50] + "..." if len(video["title"]) > 50 else video["title"]
                queue_list.append(f"{i}. {title}")

            queue_text = " | ".join(queue_list)
            total = len(queue)
            if total > 5:
                await vk_bot.send_message(channel_name, f"[LIST] Queue ({total} videos): {queue_text} and {total - 5} more...")
            else:
                await vk_bot.send_message(channel_name, f"[LIST] Queue ({total} videos): {queue_text}")

        except Exception as e:
            self.logger.error(f"Error in !queue VK handler: {e}", exc_info=True)
            await vk_bot.send_message(channel_name, f"@{author_name} [ERROR] Failed to get queue")
