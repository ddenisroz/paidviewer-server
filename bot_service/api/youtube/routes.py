from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import logging
import asyncio
import time
from core.database import get_db
from services.youtube.queue_service import QueueService
from services.youtube.skip_vote_store import skip_vote_store
from repositories.command_repository import CommandRepository
from services.youtube.youtube_service import YouTubeService
from utils.enhanced_logger import log_request, log_response
from auth.auth import get_current_user, get_current_user_optional, verify_jwt_token
from services.youtube.obs_overlay import build_youtube_obs_state
logger = logging.getLogger('bot_service')
youtube_router = APIRouter(prefix='/api/youtube', tags=['youtube'])

class AddVideoRequest(BaseModel):
    video_url: str
    is_paid: Optional[bool] = False
    points_cost: Optional[int] = None

class QueueResponse(BaseModel):
    id: int
    video_id: str
    title: str
    duration: Optional[str]
    thumbnail_url: Optional[str]
    url: str
    channel_name: str
    platform: str
    requester_name: str
    position: int
    is_paid: bool
    points_cost: Optional[int]
    added_at: Optional[str]
    played_at: Optional[str] = None

class QueueManagementRequest(BaseModel):
    queue_id: int


class QueueReorderRequest(BaseModel):
    active_queue_id: int
    over_queue_id: int


queue_service = QueueService()
youtube_service = YouTubeService()

@youtube_router.post('/queue/add')
async def add_video_to_queue(request: AddVideoRequest, user: dict=Depends(get_current_user_optional), db: Session=Depends(get_db)):
    """Add a video to the YouTube queue."""
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required.')
    user_id = user.get('id')
    if not user_id or user_id <= 0:
        raise HTTPException(status_code=401, detail='Authentication required.')
    log_request('/youtube/queue/add', 'POST', {'video_url': request.video_url}, user_id)
    start_time = time.time()
    try:
        result = await queue_service.add_video_to_user_queue(
            user_id=user_id,
            video_url=request.video_url,
            channel_name='web_interface',
            platform='web',
            requester_name=(
                user.get('username')
                or user.get('twitch_username')
                or user.get('vk_username')
                or user.get('vk_channel_name')
            ),
            requester_id=str(user_id),
            is_paid=request.is_paid,
            points_cost=request.points_cost,
            db=db,
        )
        if result['success']:
            response = {'success': True, 'message': 'Video added to the queue.', 'queue_item': result['queue_item']}
            log_response('/youtube/queue/add', 200, response, time.time() - start_time)
            return response
        else:
            log_response('/youtube/queue/add', 400, {'error': result['error']}, time.time() - start_time)
            raise HTTPException(status_code=400, detail=result['error'])
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error adding video to queue via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.get('/queue')
async def get_queue(user: dict=Depends(get_current_user_optional), db: Session=Depends(get_db)):
    """Get the current YouTube queue for the authenticated user."""
    try:
        if not user:
            raise HTTPException(status_code=401, detail='Authentication required.')
        user_id = user.get('id')
        if not user_id or user_id <= 0:
            raise HTTPException(status_code=401, detail='Authentication required.')
        queue_items = queue_service.get_user_queue(user_id=user_id, db=db)
        current_video = queue_items[0] if queue_items and len(queue_items) > 0 else None
        logger.debug(f"[QUEUE] User {user_id}: {len(queue_items)} videos, current: {(current_video['title'] if current_video else 'None')}")
        skip_votes_required = 1
        try:
            cmd_repo = CommandRepository(db)
            override = cmd_repo.get_override_by_name('skip', user_id)
            if override and override.extra_settings:
                skip_votes_required = override.extra_settings.get('skip_votes_required', 1)
        except Exception:
            logger.exception('[QUEUE] Skip votes override lookup failed')
        skip_votes = None
        if current_video:
            video_id = current_video.get('id') or current_video.get('video_id')
            current_votes = skip_vote_store.get_vote_count(user_id, video_id)
            skip_votes = {'current': current_votes, 'required': skip_votes_required, 'video_id': video_id}
        return {'queue': queue_items, 'current_video': current_video, 'is_playing': current_video is not None, 'skip_votes': skip_votes}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting queue via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.get('/queue/next')
async def get_next_video(user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get the next video from the queue."""
    try:
        next_video = queue_service.get_next_video(user['id'], db)
        if next_video:
            return {'success': True, 'video': next_video}
        else:
            raise HTTPException(status_code=404, detail='No next video is available in the queue.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting next video via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.post('/player/next')
async def skip_to_next_video(user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Switch playback to the next video."""
    try:
        queue_items = queue_service.get_user_queue(user['id'], db=db)
        if not queue_items or len(queue_items) == 0:
            raise HTTPException(status_code=404, detail='Queue is empty.')
        current_video_id = queue_items[0]['id']
        success = queue_service.mark_as_played(user['id'], current_video_id, db)
        if not success:
            raise HTTPException(status_code=404, detail='Failed to switch the current video.')
        updated_queue = queue_service.get_user_queue(user['id'], db=db)
        current_video = updated_queue[0] if updated_queue and len(updated_queue) > 0 else None
        return {'success': True, 'message': 'Switched to the next video.', 'current_video': current_video}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error skipping to next video via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.post('/queue/play/{queue_id}')
async def play_queue_item(queue_id: int, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Skip ahead to selected queue item and start playing it."""
    try:
        success = queue_service.cut_to_item(user['id'], queue_id, db)
        if not success:
            raise HTTPException(status_code=404, detail='Video was not found in the queue.')
        updated_queue = queue_service.get_user_queue(user['id'], db=db)
        current_video = updated_queue[0] if updated_queue and len(updated_queue) > 0 else None
        return {'success': True, 'current_video': current_video}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error moving queue item to top via API')
        raise HTTPException(status_code=500, detail='Internal server error.')


@youtube_router.get('/obs-state/{token}')
async def get_youtube_obs_state(token: str, db: Session=Depends(get_db)):
    """Get current YouTube OBS overlay state using an OBS token."""
    try:
        payload = verify_jwt_token(token, expected_type='obs')
        user_id = payload.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail='Invalid OBS token.')
        return build_youtube_obs_state(int(user_id), db)
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting YouTube OBS state')
        raise HTTPException(status_code=500, detail='Internal server error.')


@youtube_router.post('/queue/reorder')
async def reorder_queue_items(request: QueueReorderRequest, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Reorder pending queue items while keeping the current queue contract stable."""
    try:
        success = queue_service.reorder_queue_items(
            user['id'],
            request.active_queue_id,
            request.over_queue_id,
            db,
        )
        if not success:
            raise HTTPException(status_code=404, detail='Failed to reorder the queue.')
        updated_queue = queue_service.get_user_queue(user['id'], db=db)
        current_video = updated_queue[0] if updated_queue and len(updated_queue) > 0 else None
        return {'success': True, 'queue': updated_queue, 'current_video': current_video}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error reordering queue via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.post('/queue/ban/{queue_id}')
async def ban_queue_item(queue_id: int, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Ban a video and remove it from the queue."""
    try:
        result = queue_service.ban_video(user['id'], queue_id, db)
        if not result.get('success'):
            raise HTTPException(status_code=404, detail='Video was not found in the queue.')
        return {'success': True, 'message': 'Video added to the ban list.', 'video_id': result.get('video_id'), 'banned_count': result.get('banned_count', 0)}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error banning video')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.delete('/queue/remove/{queue_id}')
async def remove_from_queue(queue_id: int, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Remove a video from the queue."""
    try:
        success = queue_service.remove_from_queue(user['id'], queue_id, db)
        if success:
            return {'success': True, 'message': 'Video removed from the queue.'}
        else:
            raise HTTPException(status_code=404, detail='Failed to remove the video from the queue.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error removing video from queue via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.delete('/queue/clear')
@youtube_router.post('/clear')
async def clear_queue(user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Clear the YouTube queue."""
    try:
        cleared_count = queue_service.clear_queue(user['id'], db)
        return {'success': True, 'message': f'Queue cleared. Removed videos: {cleared_count}'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error clearing queue via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.post('/queue/mark-played/{queue_id}')
async def mark_as_played(queue_id: int, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Mark a video as played."""
    try:
        success = queue_service.mark_as_played(user['id'], queue_id, db)
        if success:
            return {'success': True, 'message': 'Video marked as played.'}
        else:
            raise HTTPException(status_code=404, detail='Failed to mark the video as played.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error marking video as played via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.get('/video-info')
async def get_video_info(video_url: str):
    """Get video information from a YouTube URL."""
    try:
        if not youtube_service.is_valid_youtube_url(video_url):
            raise HTTPException(status_code=400, detail='Invalid YouTube URL.')
        video_info = await youtube_service.get_video_info(video_url)
        if video_info:
            return {'success': True, 'video_info': video_info}
        else:
            raise HTTPException(status_code=404, detail='Video was not found.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting video info via API')
        raise HTTPException(status_code=500, detail='Internal server error.')

@youtube_router.get('/search')
async def search_youtube_videos(query: str=None, platform: str='youtube', user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Search YouTube videos for queue insertion."""
    log_request('/youtube/search', 'GET', {'query': query}, user.get('id'))
    start_time = time.time()
    try:
        if not query or len(query.strip()) < 2:
            response = {'success': True, 'results': [{'video_id': 'dQw4w9WgXcQ', 'title': 'Rick Astley - Never Gonna Give You Up (Video)', 'thumbnail': 'https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg', 'channel': 'Rick Astley Official', 'duration': '3:33', 'views': '1.2B'}, {'video_id': 'jNQXAC9IVRw', 'title': 'Me at the zoo', 'thumbnail': 'https://img.youtube.com/vi/jNQXAC9IVRw/mqdefault.jpg', 'channel': 'jawed', 'duration': '0:18', 'views': '300M'}], 'count': 2}
            log_response('/youtube/search', 200, response, time.time() - start_time)
            return response
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'default_search': 'ytsearch5', 'extract_flat': True, 'skip_download': True}
        search_results = []
        try:
            def _extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(query, download=False)

            info = await asyncio.to_thread(_extract_info)
            if 'entries' in info:
                for entry in info['entries'][:5]:
                    if entry.get('id'):
                        search_results.append({'video_id': entry.get('id'), 'title': entry.get('title', 'Unknown'), 'thumbnail': entry.get('thumbnail', f"https://img.youtube.com/vi/{entry.get('id')}/mqdefault.jpg"), 'channel': entry.get('uploader', 'Unknown'), 'duration': entry.get('duration', 'Unknown'), 'url': f"https://www.youtube.com/watch?v={entry.get('id')}"})
        except Exception as yt_error:
            logger.warning(f'yt-dlp search failed: {yt_error}, using fallback')
            search_results = []
        response = {'success': True, 'results': search_results, 'count': len(search_results), 'query': query}
        log_response('/youtube/search', 200, response, time.time() - start_time)
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error searching YouTube')
        log_response('/youtube/search', 500, {'error': 'Internal server error.'}, time.time() - start_time)
        raise HTTPException(status_code=500, detail='Internal server error.')
