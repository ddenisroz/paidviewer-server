"""API for webhook events, widget tokens, and internal drops triggers."""
import math
import logging
import random
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from core.database import get_db, DonationAlert
from core.config import settings
from auth.auth import get_current_user
from repositories.user_repository import UserRepository
from repositories.drops_reward_repository import DropsRewardRepository
from services.donations.donationalerts_provider import DonationAlertsProvider
logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/drops', tags=['drops'])

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/(?:watch\?[^\s<>]*v=|shorts/|live/)|youtu\.be/)[^\s<>]+",
    re.IGNORECASE,
)


class DropsWidgetTestEventRequest(BaseModel):
    """Request body for sending a test case-opening event to the OBS widget."""

    quality: str = Field(..., min_length=1, max_length=32)
    platform: Optional[str] = Field(default="global", max_length=32)


_QUALITY_ALIASES = {
    "common": "Common",
    "rare": "Rare",
    "epic": "Epic",
    "legendary": "Legendary",
    "mythical": "Mythical",
    "mythyc": "Mythical",
}

_QUALITY_LABELS = {
    "common": "Обычный",
    "rare": "Редкий",
    "epic": "Эпический",
    "legendary": "Легендарный",
    "mythical": "Мифический",
}


def _normalize_widget_quality(quality: str) -> tuple[str, str]:
    normalized = (quality or "").strip().lower()
    canonical = _QUALITY_ALIASES.get(normalized)
    if not canonical:
        raise HTTPException(status_code=400, detail="Unknown drops quality.")
    return normalized if normalized != "mythyc" else "mythical", canonical


def _weighted_reward_choice(rewards):
    if not rewards:
        return None

    total_weight = sum(max(1, int(getattr(reward, "weight", 1) or 1)) for reward in rewards)
    roll = random.uniform(0, total_weight)
    cursor = 0
    for reward in rewards:
        cursor += max(1, int(getattr(reward, "weight", 1) or 1))
        if roll <= cursor:
            return reward
    return rewards[-1]


def _build_widget_reward_payload(*, quality_key: str, quality, reward, channel_name: str) -> dict:
    if reward:
        reward_name = reward.name
        return {
            "type": "test",
            "viewer_name": "Тест",
            "quality": quality_key,
            "quality_name": quality_key,
            "quality_color": getattr(quality, "color", None),
            "reward": reward_name,
            "reward_name": reward_name,
            "reward_id": reward.id,
            "reward_type": reward.reward_type,
            "reward_value": reward.reward_value,
            "description": reward.description,
            "image_url": reward.image_url,
            "sound_file": reward.sound_file,
            "sound_volume": reward.sound_volume,
            "channel_name": channel_name,
        }

    label = _QUALITY_LABELS.get(quality_key, "Тестовый")
    reward_name = f"{label} сундук"
    return {
        "type": "test",
        "viewer_name": "Тест",
        "quality": quality_key,
        "quality_name": quality_key,
        "quality_color": getattr(quality, "color", None) if quality else None,
        "reward": reward_name,
        "reward_name": reward_name,
        "reward_id": -1,
        "reward_type": "custom",
        "reward_value": "",
        "description": "Тестовое событие виджета",
        "image_url": None,
        "sound_file": None,
        "sound_volume": 1,
        "channel_name": channel_name,
    }


def _extract_donationalerts_webhook_secret(request: Request) -> str:
    """Extract a webhook secret from supported request sources."""
    return (
        request.headers.get("X-DonationAlerts-Secret")
        or request.headers.get("X-Webhook-Secret")
        or request.query_params.get("secret")
        or ""
    )


def _verify_donationalerts_webhook_secret(request: Request) -> None:
    """
    Validate the DonationAlerts webhook secret.

    In production, a missing secret is treated as a configuration error.
    In non-production, compatibility mode is preserved without a hard failure.
    """
    configured_secret = (settings.donationalerts_webhook_secret or "").strip()
    if not configured_secret:
        if settings.is_production:
            logger.error("DonationAlerts webhook secret is not configured in production")
            raise HTTPException(status_code=503, detail="Webhook is temporarily unavailable.")
        logger.warning("DonationAlerts webhook secret is not configured; accepting request in non-production mode")
        return

    provided_secret = _extract_donationalerts_webhook_secret(request).strip()
    if not provided_secret or not secrets.compare_digest(provided_secret, configured_secret):
        logger.warning("Rejected DonationAlerts webhook request: invalid or missing webhook secret")
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")


def _extract_first_youtube_url(message: str) -> str | None:
    match = YOUTUBE_URL_RE.search(str(message or ""))
    if not match:
        return None
    return match.group(0).rstrip(".,!?)\"]'}")


def _safe_amount(value: object) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _duration_string_to_seconds(value: str | None) -> int:
    parts = str(value or "").split(":")
    if not parts or any(not part.isdigit() for part in parts):
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total

@router.get('/triggers')
async def get_drops_triggers(current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get the current user's drops triggers."""
    try:
        logger.info(f"[DROPS] Getting triggers for user {current_user.get('id')}")
        return {'success': True, 'triggers': []}
    except HTTPException:
        raise
    except Exception:
        logger.exception('[DROPS] Error getting triggers')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/triggers')
async def create_drops_trigger(request: dict, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Create a drops trigger."""
    try:
        logger.info(f"[DROPS] Creating trigger for user {current_user.get('id')}")
        return {'success': True, 'message': 'Trigger created.', 'trigger_id': 1}
    except HTTPException:
        raise
    except Exception:
        logger.exception('[DROPS] Error creating trigger')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.put('/triggers/{trigger_id}')
async def update_drops_trigger(trigger_id: int, request: dict, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Update a drops trigger."""
    try:
        logger.info(f'[DROPS] Updating trigger {trigger_id}')
        return {'success': True, 'message': 'Trigger updated.'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('[DROPS] Error updating trigger')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.delete('/triggers/{trigger_id}')
async def delete_drops_trigger(trigger_id: int, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Delete a drops trigger."""
    try:
        logger.info(f'[DROPS] Deleting trigger {trigger_id}')
        return {'success': True, 'message': 'Trigger deleted.'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('[DROPS] Error deleting trigger')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/triggers/test/{trigger_id}')
async def test_drops_trigger(trigger_id: int, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Run a test drops trigger."""
    try:
        logger.info(f'[DROPS] Testing trigger {trigger_id}')
        return {'success': True, 'message': 'Trigger test completed.'}
    except HTTPException:
        raise
    except Exception:
        logger.exception('[DROPS] Error testing trigger')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.get('/user-from-token/{token}')
async def get_user_from_token(token: str, db: Session=Depends(get_db)):
    """Resolve a user and channel by drops widget token."""
    try:
        repo = DropsRewardRepository(db)
        config = repo.get_config_by_token(token)
        if not config or not config.user_id:
            logger.warning(f'Drops widget: Config not found for token: {token[:8]}...')
            raise HTTPException(status_code=404, detail='Widget configuration not found.')
        return {'user_id': config.user_id, 'channel_name': config.channel_name, 'platform': config.platform or 'global', 'success': True}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting user from token')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/widget-url')
async def generate_widget_url(regenerate: bool=False, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get or generate the drops widget URL for the current user."""
    try:
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(current_user['id'])
        if not user:
            raise HTTPException(status_code=400, detail='Could not resolve the widget user.')
        channel_name = user.twitch_username or user.vk_channel_name or getattr(user, 'username', None) or 'unknown'
        if channel_name == 'unknown':
            raise HTTPException(status_code=400, detail='Could not resolve the drops widget channel.')
        from services.drops.drops_service import DropsService
        drops_service = DropsService(db)
        config = drops_service.get_user_config(
            user_id=current_user['id'],
            channel_name=channel_name,
            platform=None,
        )
        widget_token_value = None
        if config and hasattr(config, 'widget_token'):
            widget_token_value = config.widget_token
        if config and widget_token_value and (not regenerate):
            frontend_url = settings.frontend_url
            widget_url = f'{frontend_url}/drops-widget/{widget_token_value}'
            return {'success': True, 'data': {'url': widget_url, 'token': widget_token_value}}
        token = secrets.token_urlsafe(32)
        if config:
            try:
                from sqlalchemy import text
                db.execute(text('UPDATE drops_configs SET widget_token = :token WHERE id = :config_id'), {'token': token, 'config_id': config.id})
                if hasattr(config, 'widget_token'):
                    config.widget_token = token
            except Exception:
                logger.exception('Cannot set widget_token')
        if not config:
            config = drops_service.create_or_update_user_config(
                user_id=current_user['id'],
                channel_name=channel_name,
                platform=None,
                config_data={},
            )
            try:
                from sqlalchemy import text
                db.execute(text('UPDATE drops_configs SET widget_token = :token WHERE id = :config_id'), {'token': token, 'config_id': config.id})
                if hasattr(config, 'widget_token'):
                    config.widget_token = token
            except Exception:
                logger.exception('Cannot set widget_token on new config')
        db.commit()
        frontend_url = settings.frontend_url
        widget_url = f'{frontend_url}/drops-widget/{token}'
        return {'success': True, 'data': {'url': widget_url, 'token': token}}
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error generating widget URL')
        db.rollback()
        raise HTTPException(status_code=500, detail='Internal server error.')


@router.post('/widget/test-event/{channel_name}')
async def send_widget_test_event(
    channel_name: str,
    request: DropsWidgetTestEventRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a test case-opening event to the current user's connected drops widget."""
    try:
        quality_key, quality_name = _normalize_widget_quality(request.quality)
        reward_repo = DropsRewardRepository(db)
        quality = reward_repo.get_quality_by_name(quality_name)
        if not quality:
            raise HTTPException(status_code=400, detail='Drops quality was not found.')

        rewards = reward_repo.get_active_by_user_and_channel(
            user_id=current_user['id'],
            channel_name=channel_name,
            quality_id=quality.id,
        )
        selected_reward = _weighted_reward_choice(rewards)
        payload = _build_widget_reward_payload(
            quality_key=quality_key,
            quality=quality,
            reward=selected_reward,
            channel_name=channel_name,
        )
        event_data = {
            "type": "drops",
            "event": "reward_received",
            "data": payload,
        }

        from services.memory_websocket_manager import get_memory_websocket_manager

        sent = await get_memory_websocket_manager().send_to_user(
            current_user['id'],
            event_data,
            client_roles={"drops_widget"},
        )
        logger.info(
            "[DROPS WIDGET] Test event sent user_id=%s channel=%s quality=%s reward=%s delivered=%s",
            current_user['id'],
            channel_name,
            quality_name,
            payload.get("reward_name"),
            sent,
        )
        return {
            "success": True,
            "message": "Test event sent.",
            "data": {
                "delivered": sent,
                "quality": quality_key,
                "reward_name": payload.get("reward_name"),
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error sending drops widget test event')
        raise HTTPException(status_code=500, detail='Internal server error.')

@router.post('/donationalerts/webhook')
async def donationalerts_webhook(request: Request, db: Session=Depends(get_db)):
    """Handle DonationAlerts webhooks and grant drops when applicable."""
    try:
        _verify_donationalerts_webhook_secret(request)

        from services.drops.drops_service import DropsService
        from services.memealerts_service import MemeAlertsService
        data = await request.json()
        donation_event = await DonationAlertsProvider().normalize_event(data)
        donation_amount = donation_event.amount_rub
        donor_name = donation_event.donor_name
        donor_id = donation_event.donor_id
        message = donation_event.message
        alert_id = donation_event.event_id
        logger.info(
            "[DONATION DROPS] Received donation provider=%s donor=%s amount_original=%s currency=%s amount_rub=%s rate_source=%s",
            donation_event.provider,
            donor_name,
            donation_event.amount_original,
            donation_event.currency_original,
            donation_event.amount_rub,
            donation_event.rate_source,
        )
        user_repo = UserRepository(db)
        user_token = user_repo.get_token_by_platform('donationalerts', donation_event.provider_user_id)
        if not user_token:
            logger.warning("No user found for DonationAlerts ID: %s", donation_event.provider_user_id)
            return {'success': True, 'processed': False, 'message': 'User for the DonationAlerts webhook was not found.'}
        user = user_repo.get_by_id(user_token.user_id)
        if not user:
            logger.warning(f'DonationAlerts user not found for user_id: {user_token.user_id}')
            return {'success': True, 'processed': False, 'message': 'User for the DonationAlerts token was not found.'}
        channel_name = user.twitch_username or user.vk_channel_name or 'default'
        result = None
        memealerts_result = None
        youtube_result = None
        try:
            existing_donation = db.query(DonationAlert).filter(DonationAlert.alert_id == alert_id).with_for_update().first()
            if existing_donation and existing_donation.is_processed:
                logger.info(f'[DONATION RECORD] Donation {alert_id} already processed')
                return {'success': True, 'processed': False, 'duplicate': True, 'message': 'Donation already processed.'}
            if not existing_donation:
                donation_record = DonationAlert(user_id=user_token.user_id, channel_name=channel_name, amount=float(donation_event.amount_original), currency=donation_event.currency_original, message=message, alert_id=alert_id, is_processed=False)
                db.add(donation_record)
                logger.info(f'[DONATION RECORD] Saved donation {alert_id}')
            else:
                donation_record = existing_donation
                logger.info(f'[DONATION RECORD] Donation {alert_id} already recorded')
            drops_service = DropsService(db)
            result = drops_service.process_donation_drops_for_user(user_id=user_token.user_id, channel_name=channel_name, platform='donationalerts', viewer_id=donor_id, viewer_name=donor_name, donation_amount=donation_amount)
            memealerts_service = MemeAlertsService(db)
            memealerts_result = await memealerts_service.process_donation_auto_grant(user_id=user_token.user_id, channel_name=channel_name, donor_name=donor_name, donation_amount=donation_amount)
            try:
                from repositories.tts_settings_repository import TTSSettingsRepository
                from services.youtube.queue_service import QueueService
                from services.youtube.reward_settings import build_youtube_settings_response

                settings_row = TTSSettingsRepository(db).get_or_create(user_id=user_token.user_id)
                youtube_settings = build_youtube_settings_response(getattr(settings_row, "youtube_settings", None))
                donation_value = _safe_amount(donation_amount)
                paid_orders_enabled = bool(
                    youtube_settings.get("paid_orders_enabled")
                    or youtube_settings.get("donationalerts_video_enabled")
                )
                paid_order_mode = youtube_settings.get("paid_order_mode") or "rub_per_minute"
                rate_per_minute = _safe_amount(
                    youtube_settings.get("paid_order_rate_rub_per_minute")
                    if youtube_settings.get("paid_order_rate_rub_per_minute") is not None
                    else youtube_settings.get("donationalerts_video_min_amount")
                )
                full_video_min_amount = _safe_amount(
                    youtube_settings.get("paid_order_min_amount_rub")
                    if youtube_settings.get("paid_order_min_amount_rub") is not None
                    else youtube_settings.get("donationalerts_video_min_amount")
                )
                priority_by_amount = bool(youtube_settings.get("paid_order_priority_by_amount"))
                priority_next = bool(youtube_settings.get("donationalerts_video_priority_next", True))
                youtube_url = _extract_first_youtube_url(message)
                if paid_orders_enabled and youtube_url:
                    queue_service = QueueService()
                    if paid_order_mode == "full_video":
                        required_amount = full_video_min_amount
                        if donation_value + 1e-9 < required_amount:
                            youtube_result = {
                                "success": False,
                                "error": f"Paid video donation requires {required_amount:g} RUB.",
                            }
                        else:
                            youtube_result = await queue_service.add_video_to_user_queue(
                                user_id=user_token.user_id,
                                video_url=youtube_url,
                                channel_name=channel_name,
                                platform="donationalerts",
                                requester_name=donor_name,
                                requester_id=str(donor_id),
                                is_paid=True,
                                paid_source="donationalerts",
                                paid_amount=donation_value,
                                paid_currency="RUB",
                                source_alert_id=alert_id,
                                priority_next=priority_next and not priority_by_amount,
                                priority_by_amount=priority_by_amount,
                                db=db,
                            )
                    elif rate_per_minute > 0:
                        video_info = await queue_service.youtube_service.get_video_info(youtube_url)
                        if not video_info:
                            youtube_result = {
                                "success": False,
                                "error": "Video is unavailable or has been removed. Check the URL and try again.",
                            }
                        else:
                            duration_seconds = _duration_string_to_seconds(video_info.get("duration"))
                            billed_minutes = max(1, math.ceil(duration_seconds / 60)) if duration_seconds > 0 else 1
                            required_amount = billed_minutes * rate_per_minute
                            if donation_value + 1e-9 < required_amount:
                                youtube_result = {
                                    "success": False,
                                    "error": f"Paid video tariff requires {required_amount:g} for {billed_minutes} min.",
                                }
                            else:
                                youtube_result = await queue_service.add_video_to_user_queue(
                                    user_id=user_token.user_id,
                                    video_url=youtube_url,
                                    channel_name=channel_name,
                                    platform="donationalerts",
                                    requester_name=donor_name,
                                    requester_id=str(donor_id),
                                    is_paid=True,
                                    paid_source="donationalerts",
                                    paid_amount=donation_value,
                                    paid_currency="RUB",
                                    source_alert_id=alert_id,
                                    priority_next=priority_next and not priority_by_amount,
                                    priority_by_amount=priority_by_amount,
                                    db=db,
                                )
                    else:
                        youtube_result = await queue_service.add_video_to_user_queue(
                            user_id=user_token.user_id,
                            video_url=youtube_url,
                            channel_name=channel_name,
                            platform="donationalerts",
                            requester_name=donor_name,
                            requester_id=str(donor_id),
                            is_paid=True,
                            paid_source="donationalerts",
                            paid_amount=donation_value,
                            paid_currency="RUB",
                            source_alert_id=alert_id,
                            priority_next=priority_next and not priority_by_amount,
                            priority_by_amount=priority_by_amount,
                            db=db,
                        )
                    if not youtube_result.get("success"):
                        logger.warning("[YOUTUBE] DonationAlerts paid video skipped: %s", youtube_result.get("error"))
            except Exception:
                logger.exception("[YOUTUBE] DonationAlerts paid video processing failed")
            donation_record.is_processed = True
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(f'Error processing donation {alert_id}')
        if memealerts_result and memealerts_result.get('handled'):
            if memealerts_result.get('success'):
                logger.info('[MEMEALERTS] Donation auto-grant success: donor=%s, amount=%s', memealerts_result.get('nickname'), memealerts_result.get('amount'))
            else:
                logger.warning('[MEMEALERTS] Donation auto-grant skipped/failed: %s', memealerts_result.get('error'))
        if result:
            logger.info(f"[DONATION DROPS] {donor_name}: {result['reward']} ({result['quality']})")
            from utils.websocket_helper import broadcast_drops_event
            await broadcast_drops_event(result)
            response_payload = {'success': True, 'message': 'Drops processed.', 'data': result}
            response_payload['donation_event'] = {
                'provider': donation_event.provider,
                'event_id': donation_event.event_id,
                'amount_original': donation_event.amount_original,
                'currency_original': donation_event.currency_original,
                'amount_rub': donation_event.amount_rub,
                'rate_source': donation_event.rate_source,
                'rate_timestamp': donation_event.rate_timestamp.isoformat(),
            }
            if memealerts_result and memealerts_result.get('handled'):
                response_payload['memealerts'] = memealerts_result
            if youtube_result:
                response_payload['youtube'] = youtube_result
            return response_payload
        else:
            response_payload = {'success': True, 'processed': False, 'message': 'No matching drops result was produced.'}
            response_payload['donation_event'] = {
                'provider': donation_event.provider,
                'event_id': donation_event.event_id,
                'amount_original': donation_event.amount_original,
                'currency_original': donation_event.currency_original,
                'amount_rub': donation_event.amount_rub,
                'rate_source': donation_event.rate_source,
                'rate_timestamp': donation_event.rate_timestamp.isoformat(),
            }
            if memealerts_result and memealerts_result.get('handled'):
                response_payload['memealerts'] = memealerts_result
            if youtube_result:
                response_payload['youtube'] = youtube_result
            return response_payload
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error processing DonationAlerts webhook')
        raise HTTPException(status_code=500, detail='Internal server error.')
