"""Service for managing the YouTube queue. Uses YouTubeQueueRepository and PointsRepository."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from constants import MAX_YOUTUBE_QUEUE_SIZE
from core.database import ChannelPoints, PointsTransaction, YouTubeQueue, get_db
from core.datetime_utils import utcnow_naive
from repositories.points_repository import PointsRepository
from repositories.user_repository import UserRepository
from repositories.youtube_queue_repository import YouTubeQueueRepository
from utils.websocket_broadcast import broadcast_youtube_queue_update

from .youtube_service import YouTubeService

logger = logging.getLogger("bot_service")
DEFAULT_REQUESTER_RE = re.compile(r"^user[_\-\s]?\d+$", flags=re.IGNORECASE)


class QueueService:
    def __init__(self, connection_manager=None):
        self.youtube_service = YouTubeService()
        self.connection_manager = connection_manager

    async def _broadcast_queue_update(self, user_id: int | None) -> None:
        if not user_id:
            return
        try:
            await broadcast_youtube_queue_update(user_id)
        except Exception:
            logger.exception('[QUEUE] Failed to broadcast queue update')

    def _broadcast_queue_update_sync(self, user_id: int | None) -> None:
        if not user_id:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(broadcast_youtube_queue_update(user_id))

    @staticmethod
    def _normalize_scope_args(
        user_id: int | None = None,
        session_id: str | Session | None = None,
        db: Session | None = None,
    ) -> tuple[int | None, str | None, Session | None]:
        """
        Normalize legacy queue scope arguments.

        Some older callers still pass ``get_queue(user_id, db)`` positionally.
        Keep that path working while active runtime moves to explicit user-only methods.
        """
        if db is None and isinstance(session_id, Session):
            db = session_id
            session_id = None
        return (user_id, session_id, db)

    @staticmethod
    def _clean_requester_name(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if DEFAULT_REQUESTER_RE.match(normalized):
            return None
        return normalized

    def _resolve_requester_name(
        self,
        *,
        user_id: int | None,
        platform: str | None,
        requester_name: str | None,
        requester_id: str | None,
        db: Session,
    ) -> str:
        explicit_name = self._clean_requester_name(requester_name)
        if explicit_name:
            return explicit_name

        user = UserRepository(db).get_by_id(int(user_id)) if user_id else None
        if user is not None:
            platform_key = str(platform or "").strip().lower()
            candidates: list[str | None]
            if platform_key == "vk":
                candidates = [user.vk_username, user.vk_channel_name, user.twitch_username]
            elif platform_key in {"twitch", "donationalerts", "web"}:
                candidates = [user.twitch_username, user.vk_username, user.vk_channel_name]
            else:
                candidates = [user.twitch_username, user.vk_username, user.vk_channel_name]

            for candidate in candidates:
                cleaned = self._clean_requester_name(candidate)
                if cleaned:
                    return cleaned

        cleaned_requester_id = str(requester_id or "").strip()
        if cleaned_requester_id:
            return cleaned_requester_id
        if user_id:
            return f"User_{user_id}"
        return "Unknown"

    async def add_video_to_user_queue(
        self,
        user_id: int,
        video_url: str,
        channel_name: str | None = None,
        platform: str | None = None,
        requester_name: str | None = None,
        requester_id: str | None = None,
        is_paid: bool = False,
        points_cost: int | None = None,
        paid_source: str | None = None,
        paid_amount: float | None = None,
        paid_currency: str | None = None,
        source_alert_id: str | None = None,
        priority_next: bool = False,
        priority_by_amount: bool = False,
        db: Session | None = None,
    ) -> Dict[str, Any]:
        """Active user-only queue path for dashboard and bot commands."""
        return await self.add_video_to_queue(
            user_id=user_id,
            session_id=None,
            video_url=video_url,
            channel_name=channel_name,
            platform=platform,
            requester_name=requester_name,
            requester_id=requester_id,
            is_paid=is_paid,
            points_cost=points_cost,
            paid_source=paid_source,
            paid_amount=paid_amount,
            paid_currency=paid_currency,
            source_alert_id=source_alert_id,
            priority_next=priority_next,
            priority_by_amount=priority_by_amount,
            db=db,
        )

    async def add_video_to_queue(self, user_id: int=None, session_id: str=None, video_url: str=None, channel_name: str=None, platform: str=None, requester_name: str=None, requester_id: str=None, is_paid: bool=False, points_cost: int=None, paid_source: str | None=None, paid_amount: float | None=None, paid_currency: str | None=None, source_alert_id: str | None=None, priority_next: bool=False, priority_by_amount: bool=False, db: Session=None) -> Dict[str, Any]:
        """Add a video to the queue."""
        user_id, session_id, db = self._normalize_scope_args(user_id=user_id, session_id=session_id, db=db)
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            if not user_id and (not session_id):
                return {'success': False, 'error': 'user_id or session_id is required.'}
            if queue_repo.count_pending(user_id=user_id, session_id=session_id) >= MAX_YOUTUBE_QUEUE_SIZE:
                return {
                    'success': False,
                    'error': f'Queue limit reached: at most {MAX_YOUTUBE_QUEUE_SIZE} videos are allowed. Remove old items before adding more.',
                }
            video_input = (video_url or '').strip()
            if not video_input:
                return {'success': False, 'error': 'Provide a YouTube URL or a search query.'}
            if not self.youtube_service.is_valid_youtube_url(video_input):
                if len(video_input) < 2:
                    return {'success': False, 'error': 'Search query is too short.'}
                search_results = await self.youtube_service.search_videos(video_input, max_results=5)
                if not search_results:
                    return {'success': False, 'error': 'Video was not found. Try a different query or URL.'}
                selected_url = None
                for candidate in search_results:
                    candidate_id = candidate.get('video_id')
                    candidate_url = candidate.get('url')
                    if not candidate_id or not candidate_url:
                        continue
                    if queue_repo.get_banned_by_video_id(candidate_id, user_id=user_id, session_id=session_id):
                        continue
                    if queue_repo.get_pending_by_video_id(candidate_id, user_id=user_id, session_id=session_id):
                        continue
                    selected_url = candidate_url
                    break
                if not selected_url:
                    return {'success': False, 'error': 'All matching videos are already queued or banned. Refine the query.'}
                video_url = selected_url
            else:
                video_url = video_input
            video_info = await self.youtube_service.get_video_info(video_url)
            if not video_info:
                return {'success': False, 'error': 'Video is unavailable or has been removed. Check the URL and try again.'}
            banned = queue_repo.get_banned_by_video_id(video_id=video_info['video_id'], user_id=user_id, session_id=session_id)
            if banned:
                return {'success': False, 'error': 'This video is banned for this queue.'}
            existing = queue_repo.get_pending_by_video_id(video_id=video_info['video_id'], user_id=user_id, session_id=session_id)
            if existing:
                return {'success': False, 'error': 'This video is already in the queue. Choose another one.'}
            pending_items = queue_repo.get_pending_queue(user_id=user_id, session_id=session_id)
            max_position = len(pending_items)
            insert_position = max_position + 1
            if priority_by_amount and is_paid and paid_amount is not None:
                donation_amount = float(paid_amount or 0)
                for item in pending_items:
                    if max_position > 0 and item.position <= 1:
                        continue
                    item_amount = float(getattr(item, "paid_amount", 0) or 0)
                    if getattr(item, "is_paid", False) and item_amount + 1e-9 < donation_amount:
                        insert_position = item.position
                        break
                if insert_position <= max_position:
                    for item in pending_items:
                        if item.position >= insert_position:
                            item.position += 1
                    db.flush()
            elif priority_next:
                insert_position = 2 if max_position > 0 else 1
                for item in pending_items:
                    if item.position >= insert_position:
                        item.position += 1
                db.flush()
            resolved_requester_name = self._resolve_requester_name(
                user_id=user_id,
                platform=platform,
                requester_name=requester_name,
                requester_id=requester_id,
                db=db,
            )
            if is_paid and points_cost:
                points_result = await self._deduct_points(user_id, requester_id, resolved_requester_name, platform, channel_name, points_cost, f"Song request: {video_info['title']}", db)
                if not points_result['success']:
                    return points_result
            queue_item = YouTubeQueue(user_id=user_id, session_id=session_id, video_url=video_url, video_id=video_info['video_id'], title=video_info['title'], duration=video_info['duration'], thumbnail_url=video_info['thumbnail_url'], channel_name=channel_name, platform=platform, requester_name=resolved_requester_name, requester_id=requester_id, position=insert_position, is_paid=is_paid, points_cost=points_cost, paid_source=paid_source, paid_amount=paid_amount, paid_currency=paid_currency, source_alert_id=source_alert_id)
            queue_item = queue_repo.add_item(queue_item)
            logger.info(f"Added video to queue: {video_info['title']} by {resolved_requester_name}")
            if self.connection_manager:
                try:
                    if queue_item.position == 1:
                        await self.connection_manager.send_youtube_to_obs(channel_name=channel_name, action='play', data={'video': {'video_id': video_info['video_id'], 'title': video_info['title'], 'duration': video_info['duration'], 'thumbnail_url': video_info['thumbnail_url']}})
                    else:
                        await self.connection_manager.send_youtube_to_obs(channel_name=channel_name, action='queue_update', data={'queue_length': max_position + 1})
                except Exception:
                    logger.exception('Error sending YouTube OBS command')
            await self._broadcast_queue_update(user_id)
            return {'success': True, 'video_info': video_info, 'queue_item': {'id': queue_item.id, 'title': queue_item.title, 'duration': queue_item.duration, 'position': queue_item.position, 'requester': queue_item.requester_name, 'requester_name': queue_item.requester_name, 'is_paid': queue_item.is_paid, 'points_cost': queue_item.points_cost, 'paid_source': queue_item.paid_source, 'paid_amount': queue_item.paid_amount, 'paid_currency': queue_item.paid_currency, 'source_alert_id': queue_item.source_alert_id}}
        except Exception:
            db.rollback()
            logger.exception('Error adding video to queue')
            return {'success': False, 'error': 'Failed to add the video to the queue.'}
        finally:
            if should_close:
                db.close()

    async def add_video(self, user_id: int, url: str, requested_by: str, requester_id: str=None, platform: str=None, channel_name: str=None, is_paid: bool=False, points_cost: int=None, db: Session=None) -> Dict[str, Any]:
        """Backward-compatible wrapper for adding a video to the queue."""
        return await self.add_video_to_user_queue(user_id=user_id, video_url=url, channel_name=channel_name, platform=platform, requester_name=requested_by, requester_id=requester_id, is_paid=is_paid, points_cost=points_cost, db=db)

    async def _deduct_points(self, user_id: int, viewer_id: str, viewer_name: str, platform: str, channel_name: str, cost: int, reason: str, db: Session) -> Dict[str, Any]:
        """Deduct points for a request with race-condition protection."""
        try:
            points_repo = PointsRepository(db)
            points_record = points_repo.get_user_points_for_update(user_id=user_id, viewer_id=viewer_id, platform=platform, channel_name=channel_name)
            if not points_record or points_record.points < cost:
                db.rollback()
                return {'success': False, 'error': f'Not enough points. Required: {cost}, available: {(points_record.points if points_record else 0)}'}
            points_record.points -= cost
            points_record.total_spent += cost
            points_record.last_activity = utcnow_naive()
            points_repo.create_transaction(user_id=user_id, viewer_id=viewer_id, viewer_name=viewer_name, platform=platform, channel_name=channel_name, transaction_type='spend', amount=-cost, reason=reason)
            logger.info(f'Deducted {cost} points from {viewer_name} for {reason}')
            return {'success': True}
        except Exception:
            db.rollback()
            logger.exception('Error deducting points')
            return {'success': False, 'error': 'Failed to deduct points.'}
    def get_user_queue(self, user_id: int, db: Session=None) -> List[Dict[str, Any]]:
        """Active user-only queue path for dashboard and bot commands."""
        return self.get_queue(user_id=user_id, session_id=None, db=db)

    def get_queue(self, user_id: int=None, session_id: str=None, db: Session=None) -> List[Dict[str, Any]]:
        """Get queue items for a user or legacy session scope."""
        user_id, session_id, db = self._normalize_scope_args(user_id=user_id, session_id=session_id, db=db)
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_items = queue_repo.get_pending_queue(user_id=user_id, session_id=session_id)
            result = []
            for item in queue_items:
                result.append({'id': item.id, 'video_id': item.video_id, 'title': item.title, 'duration': item.duration, 'thumbnail_url': item.thumbnail_url, 'url': item.video_url, 'channel_name': item.channel_name, 'platform': item.platform, 'requester_name': item.requester_name, 'position': item.position, 'is_paid': item.is_paid, 'points_cost': item.points_cost, 'paid_source': item.paid_source, 'paid_amount': item.paid_amount, 'paid_currency': item.paid_currency, 'source_alert_id': item.source_alert_id, 'added_at': item.added_at.isoformat() if item.added_at else None, 'played_at': item.played_at.isoformat() if item.played_at else None})
            return result
        except Exception:
            logger.exception('Error getting queue')
            return []
        finally:
            if should_close:
                db.close()

    def remove_from_queue(self, user_id: int, queue_id: int, db: Session=None) -> bool:
        """Remove a video from the queue."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_item = queue_repo.get_pending_item(queue_id, user_id)
            if not queue_item:
                return False
            if queue_item.is_paid and queue_item.points_cost:
                self._refund_points_sync(user_id, queue_item.requester_id, queue_item.requester_name, queue_item.platform, queue_item.channel_name, queue_item.points_cost, f'Refund: {queue_item.title}', db)
            queue_repo.update_status(queue_item, 'skipped')
            self._rebuild_positions(user_id, db)
            logger.info(f'Removed video from queue: {queue_item.title}')
            self._broadcast_queue_update_sync(user_id)
            return True
        except Exception:
            db.rollback()
            logger.exception('Error removing from queue')
            return False
        finally:
            if should_close:
                db.close()

    def ban_video(self, user_id: int, queue_id: int, db: Session=None) -> Dict[str, Any]:
        """Ban a video by queue item ID (removes from queue and blocks future adds)."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_item = queue_repo.get_item_by_id(queue_id, user_id)
            if not queue_item:
                return {'success': False, 'error': 'Video not found in queue'}
            video_id = queue_item.video_id
            pending_items = queue_repo.get_pending_by_video_id_all(video_id, user_id=user_id)
            banned_count = 0
            for item in pending_items:
                queue_repo.update_status(item, 'banned')
                banned_count += 1
            if banned_count == 0:
                queue_repo.update_status(queue_item, 'banned')
                banned_count = 1
            self._rebuild_positions(user_id, db)
            logger.info(f'Banned video {video_id} for user {user_id} (count={banned_count})')
            self._broadcast_queue_update_sync(user_id)
            return {'success': True, 'video_id': video_id, 'banned_count': banned_count}
        except Exception:
            db.rollback()
            logger.exception('Error banning video')
            return {'success': False, 'error': 'Failed to ban video'}
        finally:
            if should_close:
                db.close()

    def remove_last_user_video(self, user_id: int, requester_id: str, requester_name: str, platform: str, db: Session=None) -> Dict[str, Any]:
        """
        Remove the last queued video added by a specific user (`!wronglink`).

        Args:
            user_id: Channel owner ID.
            requester_id: ID of the user who added the video.
            requester_name: Display name of the requester.
            platform: Platform name, for example twitch or vk.
            db: Database session.

        Returns:
            Operation result payload.
        """
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            last_video = queue_repo.get_last_pending_by_requester(user_id, requester_id, platform)
            if not last_video:
                return {'success': False, 'error': f'@{requester_name}, you have no videos in the queue'}
            video_title = last_video.title
            if last_video.is_paid and last_video.points_cost:
                self._refund_points_sync(user_id, requester_id, requester_name, platform, last_video.channel_name, last_video.points_cost, f'Wronglink refund: {video_title}', db)
            queue_repo.update_status(last_video, 'skipped')
            self._rebuild_positions(user_id, db)
            logger.info(f'[WRONGLINK] User {requester_name} removed their video: {video_title}')
            self._broadcast_queue_update_sync(user_id)
            return {'success': True, 'message': f"@{requester_name}, video '{video_title}' was removed from the queue", 'refunded': last_video.is_paid, 'points_refunded': last_video.points_cost if last_video.is_paid else 0}
        except Exception:
            if db:
                db.rollback()
            logger.exception('[WRONGLINK] Error removing last user video')
            return {'success': False, 'error': f'@{requester_name}, failed to remove the video'}
        finally:
            if should_close:
                db.close()

    async def _refund_points(self, user_id: int, viewer_id: str, viewer_name: str, platform: str, channel_name: str, amount: int, reason: str, db: Session):
        """Refund points (async wrapper)."""
        self._refund_points_sync(user_id, viewer_id, viewer_name, platform, channel_name, amount, reason, db)

    def _refund_points_sync(self, user_id: int, viewer_id: str, viewer_name: str, platform: str, channel_name: str, amount: int, reason: str, db: Session):
        """Refund points (sync implementation)."""
        try:
            points_repo = PointsRepository(db)
            points_record = points_repo.get_user_points(user_id=user_id, viewer_id=viewer_id, platform=platform, channel_name=channel_name)
            if points_record:
                points_record.points += amount
                points_record.total_spent -= amount
                points_record.last_activity = utcnow_naive()
                transaction = PointsTransaction(user_id=user_id, viewer_id=viewer_id, viewer_name=viewer_name, platform=platform, channel_name=channel_name, transaction_type='refund', amount=amount, reason=reason)
                db.add(transaction)
        except Exception:
            logger.exception('Error refunding points')

    def _rebuild_positions(self, user_id: int, db: Session):
        """Rebuild queue positions."""
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_items = queue_repo.get_pending_ordered(user_id)
            for (i, item) in enumerate(queue_items):
                item.position = i + 1
        except Exception:
            logger.exception('Error rebuilding positions')

    def clear_queue(self, user_id: int, db: Session=None) -> int:
        """Clear the entire queue."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_items = queue_repo.get_all_pending_for_user(user_id)
            count = 0
            for item in queue_items:
                if item.is_paid and item.points_cost:
                    self._refund_points_sync(user_id, item.requester_id, item.requester_name, item.platform, item.channel_name, item.points_cost, f'Queue cleared: {item.title}', db)
                queue_repo.update_status(item, 'skipped')
                count += 1
            logger.info(f'Cleared {count} items from queue for user {user_id}')
            self._broadcast_queue_update_sync(user_id)
            return count
        except Exception:
            db.rollback()
            logger.exception('Error clearing queue')
            return 0
        finally:
            if should_close:
                db.close()

    def get_next_video(self, user_id: int, db: Session=None) -> Optional[Dict[str, Any]]:
        """Get the next video in the queue."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            next_item = queue_repo.get_next_pending(user_id)
            if not next_item:
                return None
            return {'id': next_item.id, 'video_id': next_item.video_id, 'title': next_item.title, 'duration': next_item.duration, 'thumbnail_url': next_item.thumbnail_url, 'url': next_item.video_url, 'requester_name': next_item.requester_name, 'embed_url': self.youtube_service.get_embed_url(next_item.video_id)}
        except Exception:
            logger.exception('Error getting next video')
            return None
        finally:
            if should_close:
                db.close()

    def mark_as_played(self, user_id: int, queue_id: int, db: Session=None) -> bool:
        """Mark a video as played."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            queue_item = queue_repo.get_item_by_id(queue_id, user_id)
            if not queue_item:
                return False
            queue_item.status = 'played'
            queue_item.played_at = utcnow_naive()
            self._rebuild_positions(user_id, db)
            db.commit()
            logger.info(f'Marked video as played: {queue_item.title}')
            self._broadcast_queue_update_sync(user_id)
            return True
        except Exception:
            db.rollback()
            logger.exception('Error marking video as played')
            return False
        finally:
            if should_close:
                db.close()

    def move_to_top(self, user_id: int, queue_id: int, db: Session=None) -> bool:
        """Move selected queue item to the top (play next)."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            items = queue_repo.get_pending_ordered(user_id)
            if not items:
                return False
            selected = next((item for item in items if item.id == queue_id), None)
            if not selected:
                return False
            if items[0].id == queue_id:
                return True
            items = [selected] + [item for item in items if item.id != queue_id]
            queue_repo.rebuild_positions(items)
            db.commit()
            logger.info(f'Moved queue item to top: {selected.title}')
            self._broadcast_queue_update_sync(user_id)
            return True
        except Exception:
            db.rollback()
            logger.exception('Error moving queue item to top')
            return False
        finally:
            if should_close:
                db.close()

    def cut_to_item(self, user_id: int, queue_id: int, db: Session=None) -> bool:
        """Skip all items before the selected one and make it the current item."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            items = queue_repo.get_pending_ordered(user_id)
            if not items:
                return False
            selected_index = next((idx for (idx, item) in enumerate(items) if item.id == queue_id), None)
            if selected_index is None:
                return False
            if selected_index == 0:
                return True
            now = utcnow_naive()
            for item in items[:selected_index]:
                item.status = 'skipped'
                item.played_at = now
            remaining = items[selected_index:]
            queue_repo.rebuild_positions(remaining)
            db.commit()
            logger.info(f'Cut queue to item: {remaining[0].title}')
            self._broadcast_queue_update_sync(user_id)
            return True
        except Exception:
            db.rollback()
            logger.exception('Error cutting queue to item')
            return False
        finally:
            if should_close:
                db.close()

    def reorder_queue_items(self, user_id: int, active_queue_id: int, over_queue_id: int, db: Session=None) -> bool:
        """Move a pending queue item before/after another pending item by rebuilding positions."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_repo = YouTubeQueueRepository(db)
            items = queue_repo.get_pending_ordered(user_id)
            if not items:
                return False

            active_index = next((idx for (idx, item) in enumerate(items) if item.id == active_queue_id), None)
            over_index = next((idx for (idx, item) in enumerate(items) if item.id == over_queue_id), None)
            if active_index is None or over_index is None:
                return False
            if active_index == over_index:
                return True

            active_item = items.pop(active_index)
            items.insert(over_index, active_item)
            queue_repo.rebuild_positions(items)
            db.commit()
            logger.info(f'Reordered queue item {active_queue_id} relative to {over_queue_id}')
            self._broadcast_queue_update_sync(user_id)
            return True
        except Exception:
            db.rollback()
            logger.exception('Error reordering queue items')
            return False
        finally:
            if should_close:
                db.close()

    async def get_current_video(self, user_id: int, db: Session=None) -> Optional[Dict[str, Any]]:
        """Get the current video (the first item in the queue)."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_items = self.get_queue(user_id=user_id, db=db)
            if queue_items and len(queue_items) > 0:
                return queue_items[0]
            return None
        finally:
            if should_close:
                db.close()

    async def skip_current(self, user_id: int, db: Session=None) -> Dict[str, Any]:
        """Skip the current video and move to the next one."""
        if db is None:
            db = next(get_db())
            should_close = True
        else:
            should_close = False
        try:
            queue_items = self.get_queue(user_id=user_id, db=db)
            if not queue_items or len(queue_items) == 0:
                return {'success': False, 'error': 'Queue is empty.'}
            current_video_id = queue_items[0]['id']
            success = self.mark_as_played(user_id, current_video_id, db)
            if not success:
                return {'success': False, 'error': 'Failed to skip the video.'}
            logger.info(f"Skipped video for user {user_id}: {queue_items[0].get('title', 'Unknown')}")
            await self._broadcast_queue_update(user_id)
            return {'success': True, 'message': 'Video skipped.'}
        except Exception:
            logger.exception('Error skipping current video')
            return {'success': False, 'error': 'Failed to skip the video.'}
        finally:
            if should_close:
                db.close()
