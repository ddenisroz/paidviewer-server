"""
TTS Channel Points Mode API endpoints.

Clean Architecture: endpoints delegate to services/repositories.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from core.database import get_db
from auth.auth import get_current_user
from services.platform_rewards_service import get_platform_rewards_service
from services.tts.tts_core import AttachTtsRewardRequest, CreateTtsRewardRequest, UpdateTtsModeRequest
from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.user_token_repository import UserTokenRepository
logger = logging.getLogger('bot_service.tts.channel_points')
channel_points_router = APIRouter(prefix='/api/tts', tags=['tts-channel-points'])

@channel_points_router.get('/mode-settings')
async def get_tts_mode_settings(user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get the TTS mode and reward settings."""
    try:
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=user['id'])
        tts_reward_ids = settings.tts_reward_ids or {}
        token_repo = UserTokenRepository(db)
        active_tokens = token_repo.get_active_by_user(user['id'])
        tokens = {t.platform: t for t in active_tokens}
        platforms = {}
        for platform in ['twitch', 'vk']:
            if platform in tokens:
                platforms[platform] = {'connected': True, 'reward_id': tts_reward_ids.get(platform), 'reward_configured': platform in tts_reward_ids}
        return {'success': True, 'tts_mode': settings.tts_mode, 'tts_reward_ids': tts_reward_ids, 'platforms': platforms}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting TTS mode settings')
        raise HTTPException(status_code=500, detail='Internal server error.')

@channel_points_router.post('/mode-settings')
async def update_tts_mode_settings(request: UpdateTtsModeRequest, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Update the TTS operating mode."""
    try:
        if request.tts_mode not in ['all_messages', 'channel_points']:
            raise HTTPException(status_code=400, detail='Invalid TTS mode.')
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=user['id'])
        repo.update_settings(settings, {'tts_mode': request.tts_mode})
        logger.info(f"TTS mode updated for user {user['id']}: {request.tts_mode}")
        tts_reward_ids = settings.tts_reward_ids or {}
        token_repo = UserTokenRepository(db)
        active_tokens = token_repo.get_active_by_user(user['id'])
        tokens = {t.platform: t for t in active_tokens}
        platforms = {}
        for platform in ['twitch', 'vk']:
            if platform in tokens:
                reward_id = tts_reward_ids.get(platform)
                platforms[platform] = {
                    'connected': True,
                    'reward_id': reward_id,
                    'reward_configured': bool(str(reward_id or '').strip()),
                }
        return {
            'success': True,
            'tts_mode': request.tts_mode,
            'tts_reward_ids': tts_reward_ids,
            'platforms': platforms,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error updating TTS mode')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')

@channel_points_router.post('/rewards/create')
async def create_tts_reward(request: CreateTtsRewardRequest, starlette_request: Request, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Create a channel-points reward for TTS."""
    try:
        from platforms.registry import platform_registry
        if request.platform not in ['twitch', 'vk']:
            raise HTTPException(status_code=400, detail='Invalid platform.')
        token_repo = UserTokenRepository(db)
        active_tokens = token_repo.get_active_by_user(user['id'])
        tokens = {t.platform: t for t in active_tokens}
        if request.platform not in tokens:
            raise HTTPException(status_code=404, detail=f'Token for {request.platform} not found')
        platform = platform_registry.get(request.platform)
        if not platform:
            raise HTTPException(status_code=500, detail=f'Platform {request.platform} not initialized')
        reward_id = None
        if request.platform == 'twitch':
            reward_data = {'title': request.title, 'cost': request.cost, 'is_user_input_required': True, 'prompt': 'Enter a message for TTS playback', 'global_cooldown_seconds': request.cooldown}
            reward_id = await platform.create_reward(user['id'], reward_data)
        elif request.platform == 'vk':
            reward_data = {'title': request.title, 'cost': request.cost}
            reward_id = await platform.create_reward(user['id'], reward_data)
        if not reward_id:
            raise HTTPException(status_code=500, detail='Failed to create the reward.')
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=user['id'])
        tts_reward_ids = dict(settings.tts_reward_ids or {})
        tts_reward_ids[request.platform] = str(reward_id)
        repo.update_settings(settings, {'tts_reward_ids': tts_reward_ids})
        logger.info(f"Created TTS reward for user {user['id']} on {request.platform}: {reward_id}")
        return {'success': True, 'reward_id': reward_id, 'platform': request.platform}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error creating TTS reward')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')

@channel_points_router.post('/rewards/attach')
async def attach_tts_reward(request: AttachTtsRewardRequest, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Attach an existing Twitch channel-points reward to TTS."""
    try:
        platform = request.platform.lower().strip()
        reward_id = request.reward_id.strip()
        if platform != 'twitch':
            raise HTTPException(status_code=400, detail='Only Twitch rewards can be attached.')
        if not reward_id:
            raise HTTPException(status_code=400, detail='Reward id is required.')

        rewards = await get_platform_rewards_service().get_rewards(user['id'], platform, db)
        reward = next((item for item in rewards if str(item.get('id')) == reward_id), None)
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')
        if reward.get('is_user_input_required') is not True:
            raise HTTPException(status_code=400, detail='TTS requires a reward with user input enabled.')

        reward_title = str(reward.get('title') or reward.get('name') or '').strip()
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=user['id'])
        tts_reward_ids = dict(settings.tts_reward_ids or {})
        tts_reward_ids[platform] = reward_id
        repo.update_settings(settings, {'tts_reward_ids': tts_reward_ids})
        logger.info(f"Attached TTS reward for user {user['id']} on {platform}: {reward_id}")
        return {
            'success': True,
            'platform': platform,
            'reward_id': reward_id,
            'reward_title': reward_title,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error attaching TTS reward')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')

@channel_points_router.delete('/rewards/{platform}')
async def delete_tts_reward(platform: str, user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Detach the channel-points reward used for TTS."""
    try:
        if platform not in ['twitch', 'vk']:
            raise HTTPException(status_code=400, detail='Invalid platform.')
        repo = TTSSettingsRepository(db)
        settings = repo.get_by_user_id(user['id'])
        if not settings or not settings.tts_reward_ids:
            raise HTTPException(status_code=404, detail='Rewards are not configured yet.')
        tts_reward_ids = dict(settings.tts_reward_ids or {})
        if platform not in tts_reward_ids:
            raise HTTPException(status_code=404, detail=f'No reward for {platform}')
        del tts_reward_ids[platform]
        repo.update_settings(settings, {'tts_reward_ids': tts_reward_ids})
        logger.info(f"Detached TTS reward for user {user['id']} on {platform}")
        return {'success': True, 'platform': platform}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error deleting TTS reward')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')
