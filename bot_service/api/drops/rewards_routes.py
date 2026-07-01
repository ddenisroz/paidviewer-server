"""
Drops rewards API endpoints.
Clean Architecture: uses DropsRewardRepository for data access.
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth import get_current_user, get_current_user_optional
from core.database import get_db
from repositories.drops_reward_repository import DropsRewardRepository
from utils.cache import get_cached, invalidate_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/drops', tags=['drops'])
DROPS_REWARDS_CACHE_TTL = 60


class DropsRewardCreate(BaseModel):
    """Schema for creating a drops reward."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    quality_id: int = Field(..., ge=1)
    weight: int = Field(100, ge=1, le=1000)
    reward_type: str = Field(..., pattern='^(points|voice|command|custom)$')
    reward_value: str = Field(default='', max_length=1000)
    image_url: Optional[str] = Field(None, max_length=1000)
    sound_volume: float = Field(1.0, ge=0.0, le=2.0)
    is_active: bool = True


class DropsRewardUpdate(BaseModel):
    """Schema for updating a drops reward."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    quality_id: Optional[int] = Field(None, ge=1)
    weight: Optional[int] = Field(None, ge=1, le=1000)
    reward_type: Optional[str] = Field(None, pattern='^(points|voice|command|custom)$')
    reward_value: Optional[str] = Field(None, max_length=1000)
    image_url: Optional[str] = Field(None, max_length=1000)
    sound_volume: Optional[float] = Field(None, ge=0.0, le=2.0)
    is_active: Optional[bool] = None


class DropsRewardToggle(BaseModel):
    """Toggle reward active state."""

    is_active: bool


def sanitize_html(text: str) -> str:
    """Remove HTML tags from user-provided text."""
    if not text:
        return text
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)


def _reward_to_dict(reward, quality_info: dict) -> dict:
    """Convert reward model to dict for response."""
    return {
        'id': reward.id,
        'name': reward.name,
        'description': reward.description,
        'quality': quality_info,
        'weight': reward.weight,
        'reward_type': reward.reward_type,
        'reward_value': reward.reward_value,
        'image_url': reward.image_url,
        'sound_file': reward.sound_file,
        'sound_volume': reward.sound_volume,
        'is_active': reward.is_active,
        'created_at': reward.created_at,
        'updated_at': reward.updated_at,
    }


@router.get('/rewards/{channel_name}')
async def get_drops_rewards(
    channel_name: str,
    platform: str = 'twitch',
    quality: Optional[str] = None,
    widget_token: Optional[str] = None,
    current_user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Get drops rewards for a channel."""
    try:
        repo = DropsRewardRepository(db)
        user_id = None
        if current_user and current_user.get('id'):
            user_id = current_user['id']
        elif widget_token:
            config = repo.get_config_by_token(widget_token)
            if config and config.channel_name == channel_name:
                user_id = config.user_id
            else:
                raise HTTPException(status_code=403, detail='Widget token does not match the requested channel.')
        else:
            raise HTTPException(status_code=401, detail='Authentication required.')

        cache_key = f"drops_rewards:{user_id}:{channel_name}:{quality or 'all'}"
        if widget_token:
            cache_key = f'{cache_key}:token:{widget_token}'

        def _load_rewards():
            quality_id = None
            if quality:
                quality_obj = repo.get_quality_by_name(quality)
                if quality_obj:
                    quality_id = quality_obj.id
            rewards = repo.get_by_user_and_channel(user_id, channel_name, quality_id)
            quality_ids = {reward.quality_id for reward in rewards if reward.quality_id}
            qualities = repo.get_qualities_by_ids(list(quality_ids))
            return [_reward_to_dict(reward, qualities.get(reward.quality_id, {})) for reward in rewards]

        rewards = get_cached(cache_key, _load_rewards, ttl=DROPS_REWARDS_CACHE_TTL)
        return {'success': True, 'data': rewards}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting drops rewards')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.post('/rewards/{channel_name}')
async def create_drops_reward(
    channel_name: str,
    reward_data: DropsRewardCreate,
    platform: str = 'twitch',
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a drops reward."""
    try:
        repo = DropsRewardRepository(db)
        quality = repo.get_quality_by_id(reward_data.quality_id)
        if not quality:
            available_qualities = repo.get_all_qualities()
            available_ids = [item.id for item in available_qualities]
            logger.warning(f'Quality with id {reward_data.quality_id} not found. Available: {available_ids}')
            raise HTTPException(status_code=400, detail=f'Quality with id {reward_data.quality_id} was not found.')

        reward = repo.create(
            user_id=current_user['id'],
            channel_name=channel_name,
            platform=platform,
            name=sanitize_html(reward_data.name),
            description=sanitize_html(reward_data.description) if reward_data.description else None,
            quality_id=reward_data.quality_id,
            weight=reward_data.weight,
            reward_type=reward_data.reward_type,
            reward_value=reward_data.reward_value,
            image_url=reward_data.image_url,
            sound_volume=reward_data.sound_volume,
            is_active=reward_data.is_active,
        )
        invalidate_cache(f"drops_rewards:{current_user['id']}:{channel_name}:")
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            user_id = current_user.get('id')
            if user_id and user_id != -1:
                cache_invalidation_event = {
                    'type': 'cache_invalidate',
                    'cache_key': f'drops_rewards_{channel_name}',
                    'reason': 'drops_reward_created',
                }
                await get_memory_websocket_manager().send_to_user(user_id, cache_invalidation_event)
        except Exception as ws_error:
            logger.warning(f'Failed to send WebSocket notification: {ws_error}')

        return {
            'success': True,
            'message': 'Reward created.',
            'data': {
                'id': reward.id,
                'name': reward.name,
                'quality': quality.name,
                'reward_type': reward.reward_type,
                'created_at': reward.created_at,
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error creating drops reward')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.put('/rewards/{reward_id}')
async def update_drops_reward(
    reward_id: int,
    reward_data: DropsRewardUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a drops reward."""
    try:
        repo = DropsRewardRepository(db)
        reward = repo.get_by_id_and_user(reward_id, current_user['id'])
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')

        update_data = reward_data.model_dump(exclude_unset=True)
        if 'name' in update_data and update_data['name']:
            update_data['name'] = sanitize_html(update_data['name'])
        if 'description' in update_data and update_data['description']:
            update_data['description'] = sanitize_html(update_data['description'])
        reward = repo.update(reward, update_data)
        invalidate_cache(f"drops_rewards:{current_user['id']}:{reward.channel_name}:")
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            user_id = current_user.get('id')
            if user_id and user_id != -1:
                cache_invalidation_event = {
                    'type': 'cache_invalidate',
                    'cache_key': f'drops_rewards_{reward.channel_name}',
                    'reason': 'drops_reward_updated',
                }
                await get_memory_websocket_manager().send_to_user(user_id, cache_invalidation_event)
        except Exception as ws_error:
            logger.warning(f'Failed to send WebSocket notification: {ws_error}')

        return {
            'success': True,
            'message': 'Reward updated.',
            'data': {'id': reward.id, 'name': reward.name, 'updated_at': reward.updated_at},
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error updating drops reward')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.patch('/rewards/{reward_id}/toggle')
async def toggle_drops_reward(
    reward_id: int,
    toggle_data: DropsRewardToggle,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle drops reward active state."""
    try:
        repo = DropsRewardRepository(db)
        reward = repo.get_by_id_and_user(reward_id, current_user['id'])
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')

        reward = repo.update(reward, {'is_active': toggle_data.is_active})
        invalidate_cache(f"drops_rewards:{current_user['id']}:{reward.channel_name}:")
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            user_id = current_user.get('id')
            if user_id and user_id != -1:
                cache_invalidation_event = {
                    'type': 'cache_invalidate',
                    'cache_key': f'drops_rewards_{reward.channel_name}',
                    'reason': 'drops_reward_toggled',
                }
                await get_memory_websocket_manager().send_to_user(user_id, cache_invalidation_event)
        except Exception as ws_error:
            logger.warning(f'Failed to send WebSocket notification: {ws_error}')

        return {
            'success': True,
            'message': 'Reward status updated.',
            'data': {'id': reward.id, 'is_active': reward.is_active, 'updated_at': reward.updated_at},
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error toggling drops reward')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.delete('/rewards/{reward_id}')
async def delete_drops_reward(reward_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a drops reward."""
    try:
        repo = DropsRewardRepository(db)
        reward = repo.get_by_id_and_user(reward_id, current_user['id'])
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')

        channel_name = repo.delete(reward)
        invalidate_cache(f"drops_rewards:{current_user['id']}:{channel_name}:")
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager

            user_id = current_user.get('id')
            if user_id and user_id != -1:
                cache_invalidation_event = {
                    'type': 'cache_invalidate',
                    'cache_key': f'drops_rewards_{channel_name}',
                    'reason': 'drops_reward_deleted',
                }
                await get_memory_websocket_manager().send_to_user(user_id, cache_invalidation_event)
        except Exception as ws_error:
            logger.warning(f'Failed to send WebSocket notification: {ws_error}')

        return {'success': True, 'message': 'Reward deleted.'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error deleting drops reward')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.post('/rewards/{reward_id}/image')
async def upload_reward_image(
    reward_id: int,
    image_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an image for a drops reward."""
    try:
        import os

        repo = DropsRewardRepository(db)
        reward = repo.get_by_id_and_user(reward_id, current_user['id'])
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')
        if not image_file.content_type or not image_file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail='Only image files are allowed.')

        upload_dir = f"uploads/drops/{current_user['id']}/images"
        os.makedirs(upload_dir, exist_ok=True)
        safe_source_name = Path(image_file.filename or '').name
        file_extension = Path(safe_source_name).suffix.lower() or '.png'
        allowed_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        if file_extension not in allowed_image_extensions:
            raise HTTPException(status_code=400, detail='Unsupported image extension.')

        filename = f'reward_{reward_id}_{int(time.time())}{file_extension}'
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, 'wb') as buffer:
            content = await image_file.read()
            if len(content) > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail='Image file is too large.')
            buffer.write(content)

        image_url = f"/static/uploads/drops/{current_user['id']}/images/{filename}"
        repo.update_image(reward, image_url)
        invalidate_cache(f"drops_rewards:{current_user['id']}:{reward.channel_name}:")
        return {'success': True, 'message': 'Image uploaded.', 'data': {'image_url': image_url, 'filename': filename}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error uploading reward image')
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.post('/rewards/{reward_id}/sound')
async def upload_reward_sound(
    reward_id: int,
    sound_file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a sound file for a drops reward."""
    try:
        import os

        from validators.file_validators import validate_sound_file

        repo = DropsRewardRepository(db)
        reward = repo.get_by_id_and_user(reward_id, current_user['id'])
        if not reward:
            raise HTTPException(status_code=404, detail='Reward not found.')

        validate_sound_file(sound_file)
        upload_dir = f"uploads/sounds/{current_user['id']}"
        os.makedirs(upload_dir, exist_ok=True)
        safe_source_name = Path(sound_file.filename or '').name
        file_extension = Path(safe_source_name).suffix.lower() or '.wav'
        filename = f'reward_{reward_id}_{int(time.time())}{file_extension}'
        file_path = os.path.join(upload_dir, filename)
        with open(file_path, 'wb') as buffer:
            content = await sound_file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail='Sound file is too large.')
            buffer.write(content)

        repo.update_sound(reward, file_path)
        invalidate_cache(f"drops_rewards:{current_user['id']}:{reward.channel_name}:")
        return {'success': True, 'message': 'Sound uploaded.', 'data': {'sound_file': file_path, 'filename': filename}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error uploading reward sound')
        raise HTTPException(status_code=500, detail='Internal server error.')
