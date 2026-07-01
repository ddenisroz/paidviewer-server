"""
Drops History, Stats, Streaks, and Open endpoints.

Clean Architecture: endpoints delegate to DropsService.
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from core.database import get_db, DropsHistory, ChatMessage, PendingStreakChest
from core.datetime_utils import utcnow_naive
from auth.auth import get_current_user, get_current_user_optional
from utils.enhanced_logger import drops_logger
logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/drops', tags=['drops'])

class DropsOpenRequest(BaseModel):
    """Payload for manually opening a drops reward."""
    drops_type: str = Field(..., pattern='^(streak|donation|mythical)$')
    viewer_id: str = Field(..., min_length=1, max_length=100)
    viewer_name: str = Field(..., min_length=1, max_length=100)
    donation_amount: Optional[float] = Field(None, ge=0.01)
    streak_days: Optional[int] = Field(None, ge=1)
    messages_count: Optional[int] = Field(None, ge=0)

def get_user_id(current_user: dict) -> int:
    """Extract the current user ID from the auth payload."""
    if not current_user:
        return None
    user_id = current_user.get('id')
    if not user_id or user_id <= 0:
        return None
    return user_id

def get_drops_service(db: Session):
    """Get DropsService instance."""
    from services.drops.drops_service import DropsService
    return DropsService(db)

@router.get('/qualities')
async def get_drops_qualities(db: Session=Depends(get_db)):
    """Get the list of available drops qualities."""
    try:
        service = get_drops_service(db)
        qualities = service.get_all_qualities()
        return {'success': True, 'data': qualities}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting drops qualities')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get('/history/{channel_name}')
async def get_drops_history(channel_name: str, platform: Optional[str]=None, viewer: Optional[str]=None, reward: Optional[str]=None, drops_type: Optional[str]=None, date_from: Optional[str]=None, date_to: Optional[str]=None, limit: int=50, offset: int=0, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get drops history for the selected channel."""
    try:
        service = get_drops_service(db)
        history = service.get_drops_history(user_id=current_user['id'], channel_name=channel_name, platform=platform or 'twitch', limit=limit, offset=offset)
        filtered_history = history
        if viewer:
            viewer_norm = viewer.strip().lower()
            filtered_history = [h for h in filtered_history if viewer_norm in (h.viewer_name or '').lower()]
        if reward:
            reward_norm = reward.strip().lower()
            filtered_history = [h for h in filtered_history if reward_norm in (h.reward_name or '').lower()]
        if drops_type:
            type_norm = drops_type.strip().lower()
            filtered_history = [h for h in filtered_history if (h.lootbox_type or '').lower() == type_norm]
        parsed_date_from: Optional[datetime] = None
        parsed_date_to: Optional[datetime] = None
        if date_from:
            try:
                parsed_date_from = datetime.fromisoformat(date_from)
            except ValueError:
                parsed_date_from = None
        if date_to:
            try:
                parsed_date_to = datetime.fromisoformat(date_to)
            except ValueError:
                parsed_date_to = None
        if parsed_date_from:
            filtered_history = [h for h in filtered_history if h.created_at and h.created_at >= parsed_date_from]
        if parsed_date_to:
            filtered_history = [h for h in filtered_history if h.created_at and h.created_at <= parsed_date_to]
        quality_ids = {e.quality_id for e in filtered_history if e.quality_id}
        qualities = service.get_qualities_by_ids(list(quality_ids))
        chat_message_ids = [entry.chat_message_id for entry in filtered_history if entry.chat_message_id]
        chat_messages = {}
        if chat_message_ids:
            chat_messages = {
                message.id: message
                for message in db.query(ChatMessage).filter(ChatMessage.id.in_(chat_message_ids)).all()
            }

        def _trigger_label(entry: DropsHistory) -> str:
            kind = (entry.lootbox_type or '').lower()
            if kind == 'donation':
                return 'Донат'
            if kind == 'mythical':
                return 'Мифический сундук'
            if kind == 'streak':
                return 'Стрик'
            return entry.lootbox_type or 'Drops'

        return {'success': True, 'data': [{
            'id': entry.id,
            'viewer_name': entry.viewer_name,
            'platform': entry.platform,
            'drops_type': entry.lootbox_type,
            'source_type': entry.lootbox_type,
            'trigger_label': _trigger_label(entry),
            'quality': qualities.get(entry.quality_id, {}),
            'reward_name': entry.reward_name,
            'reward_type': entry.reward_type,
            'donation_amount': entry.donation_amount,
            'streak_days': entry.streak_days,
            'messages_count': entry.messages_count,
            'chat_message_id': entry.chat_message_id,
            'message_text': getattr(chat_messages.get(entry.chat_message_id), 'message', None) if entry.chat_message_id else None,
            'has_platform_message': bool(entry.chat_message_id),
            'created_at': entry.created_at,
        } for entry in filtered_history]}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting drops history')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/open')
async def open_drops(request: DropsOpenRequest, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Manually open a drops reward for the selected viewer."""
    try:
        from services.drops.drops_service import DropsService
        from services.drops.drops_calculation_service import DropsCalculationService
        from repositories.drops_history_repository import DropsHistoryRepository
        drops_service = DropsService(db)
        calc_service = DropsCalculationService(db)
        history_repo = DropsHistoryRepository(db)
        config = drops_service.get_config_by_user_id(current_user['id'])
        if not config:
            raise HTTPException(status_code=404, detail='Drops configuration not found.')
        quality_name = None
        pending_chest = None
        if request.drops_type == 'streak':
            pending_chest = db.query(PendingStreakChest).filter(
                PendingStreakChest.user_id == current_user['id'],
                PendingStreakChest.channel_name == config.channel_name,
                PendingStreakChest.platform == config.platform,
                PendingStreakChest.viewer_id == request.viewer_id,
                PendingStreakChest.status == 'pending',
            ).first()
            if not pending_chest:
                pending_chest = db.query(PendingStreakChest).filter(
                    PendingStreakChest.user_id == current_user['id'],
                    PendingStreakChest.channel_name == config.channel_name,
                    PendingStreakChest.viewer_id == request.viewer_id,
                    PendingStreakChest.status == 'pending',
                ).order_by(PendingStreakChest.updated_at.desc()).first()
            if not pending_chest:
                raise HTTPException(status_code=400, detail='No pending streak chest for this viewer.')
            quality_name = pending_chest.quality_name
        elif request.drops_type == 'donation':
            if not request.donation_amount:
                raise HTTPException(status_code=400, detail='Not enough data to open streak drops.')
            if request.donation_amount >= config.donation_amount_legendary:
                quality_name = 'Legendary'
            elif request.donation_amount >= config.donation_amount_epic:
                quality_name = 'Epic'
            elif request.donation_amount >= config.donation_amount_rare:
                quality_name = 'Rare'
            elif request.donation_amount >= config.donation_amount_common:
                quality_name = 'Common'
            else:
                raise HTTPException(status_code=400, detail=f'Donation amount is too low for drop. Minimum required: {config.donation_amount_common}.')
        elif request.drops_type == 'mythical':
            quality_name = 'Mythical'
            if not drops_service._can_activate_mythical(config):
                raise HTTPException(status_code=400, detail='Not enough data to open mythical drops.')
        else:
            raise HTTPException(status_code=400, detail='Unsupported drops type.')
        try:
            drop_platform = pending_chest.platform if pending_chest else config.platform
            drop_result = calc_service.calculate_drop(user_id=current_user['id'], channel_name=config.channel_name, platform=drop_platform, quality_name=quality_name)
        except ValueError as e:
            logger.exception('[ERROR] [DROPS] Failed to calculate drop')
            raise HTTPException(status_code=500, detail='Internal server error.')
        quality = drops_service.get_quality_by_name(quality_name)
        history_entry = history_repo.create_history_entry(user_id=current_user['id'], channel_name=config.channel_name, platform=pending_chest.platform if pending_chest else config.platform, viewer_id=request.viewer_id, viewer_name=request.viewer_name, lootbox_type=request.drops_type, quality_id=quality.id if quality else None, reward_id=drop_result['reward_id'], reward_name=drop_result['reward_name'], reward_type=drop_result['reward_type'], reward_value=drop_result['reward_value'], donation_amount=request.donation_amount if request.drops_type == 'donation' else None, streak_days=pending_chest.streak_days if pending_chest else (request.streak_days if request.drops_type == 'streak' else None), messages_count=pending_chest.messages_count if pending_chest else (request.messages_count if request.drops_type == 'streak' else None))
        if pending_chest:
            pending_chest.status = 'opened'
            pending_chest.opened_history_id = history_entry.id
            pending_chest.opened_at = utcnow_naive()
            pending_chest.updated_at = utcnow_naive()
            db.commit()
        logger.info(f"[OK] [DROPS] Opened {request.drops_type} lootbox for {request.viewer_name}: {drop_result['reward_name']} ({quality_name})")
        try:
            from services.memory_websocket_manager import get_memory_websocket_manager
            ws_message = {'type': 'drops_opened', 'data': {'viewer_name': request.viewer_name, 'drops_type': request.drops_type, 'quality': quality_name, 'reward': drop_result, 'history_id': history_entry.id}}
            await get_memory_websocket_manager().send_to_user(current_user['id'], ws_message)
        except Exception as ws_error:
            logger.warning(f'Failed to send WebSocket notification: {ws_error}')
        return {'success': True, 'data': {'type': request.drops_type, 'viewer_name': request.viewer_name, 'quality': quality_name, 'reward': drop_result, 'history_id': history_entry.id}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error opening drops')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get('/stats/{channel_name}')
async def get_drops_stats(channel_name: str, platform: str='twitch', current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get aggregated drops statistics for a channel."""
    try:
        service = get_drops_service(db)
        stats = service.get_full_channel_stats(user_id=current_user['id'], channel_name=channel_name, platform=platform)
        return {'success': True, 'data': stats}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting drops stats')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get('/streaks/{channel_name}')
async def get_user_streaks(channel_name: str, platform: Optional[str]=None, limit: int=50, offset: int=0, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get current streak entries for the user's channel."""
    try:
        service = get_drops_service(db)
        user_id = get_user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=401, detail='Authentication required.')
        config = service.get_user_config(user_id=user_id, channel_name=channel_name, platform=None)
        streak_enabled = False
        if config:
            streak_enabled = getattr(config, 'streak_enabled_twitch', False) or getattr(config, 'streak_enabled_vk', False)
        if not config or not streak_enabled:
            return {'success': True, 'data': []}
        streaks = service.get_user_streaks_paginated(user_id=user_id, channel_name=channel_name, platform=platform, limit=limit, offset=offset)
        return {'success': True, 'data': streaks}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting user streaks')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/streak/reset/{channel_name}')
async def reset_streak_statistics(channel_name: str, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Reset streak statistics for the selected channel."""
    try:
        service = get_drops_service(db)
        user_id = get_user_id(current_user)
        if not user_id:
            raise HTTPException(status_code=401, detail='Authentication required.')
        config = service.get_user_config(user_id=user_id, channel_name=channel_name, platform=None)
        if not config:
            raise HTTPException(status_code=404, detail='Drops configuration not found.')
        deleted_count = service.reset_channel_streaks(user_id=user_id, channel_name=channel_name)
        drops_logger.info(f'...{deleted_count}...{channel_name}')
        return {'success': True, 'message': 'Streak statistics reset.', 'data': {'channel_name': channel_name, 'platform': 'all', 'deleted_count': deleted_count}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error resetting streak statistics')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get('/mythical-session/{channel_name}')
async def get_active_mythical_session(channel_name: str, widget_token: Optional[str]=None, current_user: Optional[dict]=Depends(get_current_user_optional), db: Session=Depends(get_db)):
    """Get the active mythical session for a channel."""
    try:
        service = get_drops_service(db)
        if widget_token:
            config = service.get_config_by_widget_token(widget_token)
            if not config:
                raise HTTPException(status_code=404, detail='Widget configuration not found.')
            user_id = config.user_id
        elif current_user:
            user_id = current_user.get('id')
        else:
            raise HTTPException(status_code=401, detail='Authentication required.')
        session_data = service.get_active_user_mythical_session(user_id=user_id, channel_name=channel_name)
        return {'success': True, 'data': session_data}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting active mythical session')
        raise HTTPException(status_code=500, detail='Internal server error.')
