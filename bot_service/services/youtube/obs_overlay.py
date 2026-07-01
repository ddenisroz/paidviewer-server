"""Shared state builder for the public YouTube OBS overlay."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.command_repository import CommandRepository
from services.youtube.queue_service import QueueService
from services.youtube.reward_settings import build_youtube_settings_response
from services.youtube.skip_vote_store import skip_vote_store


def build_youtube_obs_state(user_id: int, db: Session) -> dict[str, Any]:
    """Return queue and settings state consumed by OBS overlay clients."""

    queue_items = QueueService().get_user_queue(user_id=user_id, db=db)
    current_video = queue_items[0] if queue_items else None
    tts_settings = TTSSettingsRepository(db).get_or_create(user_id=user_id)
    settings = build_youtube_settings_response(getattr(tts_settings, "youtube_settings", None) or {})
    skip_votes_required = 1
    try:
        override = CommandRepository(db).get_override_by_name("skip", user_id)
        if override and override.extra_settings:
            skip_votes_required = int(override.extra_settings.get("skip_votes_required", 1) or 1)
    except Exception:
        skip_votes_required = 1

    skip_votes = None
    if current_video:
        video_id = current_video.get("id") or current_video.get("video_id")
        skip_votes = {
            "current": skip_vote_store.get_vote_count(user_id, video_id),
            "required": skip_votes_required,
            "video_id": video_id,
        }

    return {
        "queue": queue_items,
        "current_video": current_video,
        "is_playing": current_video is not None,
        "skip_votes": skip_votes,
        "settings": settings,
        "timestamp": time.time(),
    }
