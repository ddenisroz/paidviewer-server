"""MemeAlerts API endpoints for grants, settings, and automation."""
from typing import Literal, Optional, cast
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from core.database import get_db
from core.config import settings
from auth.auth import get_current_user, get_current_user_optional
from repositories.user_token_repository import UserTokenRepository
from services.memealerts_service import MemeAlertsService
from core.token_encryption import encrypt_token, decrypt_token
import logging
import jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memealerts", tags=["memealerts"])

MEMEALERTS_API_BASE = "https://memealerts.com"
_MEMEALERTS_ALLOWED_AUTH_HOSTS = {"memealerts.com", "www.memealerts.com"}
_MEMEALERTS_SUPPORTED_AUTH_PROVIDERS = ("twitch", "google", "vk")
MemeAlertsAuthProvider = Literal["twitch", "google", "vk"]
_MEMEALERTS_AUTH_SCOPE_PREFIX = "auth_provider:"


def _normalize_memealerts_provider(provider: object | None) -> MemeAlertsAuthProvider:
    raw_provider = provider if isinstance(provider, str) else None
    normalized = str(raw_provider or "twitch").strip().lower()
    if normalized not in _MEMEALERTS_SUPPORTED_AUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported MemeAlerts provider")
    return cast(MemeAlertsAuthProvider, normalized)


def _normalize_optional_memealerts_provider(provider: object | None) -> Optional[MemeAlertsAuthProvider]:
    raw_provider = provider if isinstance(provider, str) else None
    normalized = str(raw_provider or "").strip().lower()
    if not normalized:
        return None
    if normalized not in _MEMEALERTS_SUPPORTED_AUTH_PROVIDERS:
        return None
    return cast(MemeAlertsAuthProvider, normalized)


def _extract_saved_auth_provider(scopes: object) -> Optional[MemeAlertsAuthProvider]:
    if not isinstance(scopes, list):
        return None
    for item in scopes:
        if not isinstance(item, str):
            continue
        if not item.startswith(_MEMEALERTS_AUTH_SCOPE_PREFIX):
            continue
        return _normalize_optional_memealerts_provider(item.removeprefix(_MEMEALERTS_AUTH_SCOPE_PREFIX))
    return None


def _build_memealerts_token_scopes(provider: Optional[str], token_scope: object) -> list[str]:
    scopes: list[str] = []
    normalized_provider = _normalize_optional_memealerts_provider(provider)
    if normalized_provider:
        scopes.append(f"{_MEMEALERTS_AUTH_SCOPE_PREFIX}{normalized_provider}")
    if token_scope is not None:
        scopes.append(f"scope:{token_scope}")
    return scopes


def _resolve_memealerts_callback_url(provider: str | None = None) -> str:
    base_candidates = [
        str(getattr(settings, "frontend_url", "") or "").strip().rstrip("/"),
        str(getattr(settings, "backend_url", "") or "").strip().rstrip("/"),
    ]
    for base_url in base_candidates:
        if _is_safe_absolute_callback_url(base_url):
            callback_url = f"{base_url}/memealerts/callback"
            normalized_provider = str(provider or "").strip().lower()
            if normalized_provider:
                callback_url = f"{callback_url}?{urlencode({'provider': normalized_provider})}"
            if _is_safe_absolute_callback_url(callback_url):
                return callback_url
    raise HTTPException(status_code=500, detail="Failed to resolve MemeAlerts callback URL")


def _is_safe_absolute_callback_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if any(ch in url for ch in ("\r", "\n", "\t")):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def _is_safe_memealerts_auth_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if any(ch in url for ch in ("\r", "\n", "\t")):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    return (parsed.netloc or "").lower() in _MEMEALERTS_ALLOWED_AUTH_HOSTS


def _build_memealerts_connect_payload(provider: str | None) -> dict:
    normalized_provider = _normalize_memealerts_provider(provider)
    callback_url = _resolve_memealerts_callback_url(normalized_provider)
    provider_auth_path = f"/api/auth/{normalized_provider}"
    direct_auth_url = f"{MEMEALERTS_API_BASE}{provider_auth_path}?{urlencode({'return_url': callback_url})}"
    proxy_auth_url = f"/api/memealerts/proxy{provider_auth_path}?{urlencode({'return_url': callback_url})}"
    if not _is_safe_memealerts_auth_url(direct_auth_url):
        logger.error("Unsafe MemeAlerts auth URL generated for provider=%s", normalized_provider)
        raise HTTPException(status_code=500, detail="Failed to generate secure auth URL")
    return {
        "success": True,
        "provider": normalized_provider,
        "auth_url": proxy_auth_url,
        "direct_auth_url": direct_auth_url,
        "proxy_auth_url": proxy_auth_url,
        "callback_url": callback_url,
        "flow": "provider_popup_callback",
    }


def decode_memealerts_token(token: str) -> dict:
    """
    Decode MemeAlerts JWT token without signature verification.
    Use claims only as fallback hints, never as an authorization source.
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        logger.exception("Failed to decode MemeAlerts token")
        raise ValueError("Invalid token format")


def _extract_memealerts_streamer_id(decoded: dict, trusted_fallback: Optional[str] = None) -> Optional[str]:
    """Pick the actual MemeAlerts streamer id from JWT claims."""
    return (
        decoded.get("streamer_id")
        or decoded.get("streamerId")
        or decoded.get("id")
        or decoded.get("_id")
        or decoded.get("user_id")
        or decoded.get("uid")
        or decoded.get("sub")
        or trusted_fallback
        or decoded.get("tid")
    )


class PlatformRewardSettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    reward_id: Optional[str] = None
    reward_title: Optional[str] = None
    coins_amount: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    reward_cost: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    local_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    platform: Optional[Literal["twitch", "vk"]] = None
    cooldown_seconds: Optional[int] = Field(default=None, ge=0, le=86_400)


class DonationAutoSettingsPatch(BaseModel):
    enabled: Optional[bool] = None
    coins_per_currency: Optional[float] = Field(default=None, ge=0.01, le=1_000_000)
    min_donation_amount: Optional[float] = Field(default=None, ge=0.01, le=1_000_000)


class MemeAlertsSettingsPatch(BaseModel):
    twitch: Optional[PlatformRewardSettingsPatch] = None
    vk: Optional[PlatformRewardSettingsPatch] = None
    points_rewards: Optional[list[PlatformRewardSettingsPatch]] = None
    donation_auto: Optional[DonationAutoSettingsPatch] = None


class CreatePointsRewardRequest(BaseModel):
    local_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    platform: Literal["twitch", "vk"]
    title: str = Field(default="MemeCoins", min_length=1, max_length=80)
    cost: int = Field(default=500, ge=1, le=1_000_000)
    coins_amount: int = Field(default=10, ge=1, le=1_000_000)
    cooldown_seconds: int = Field(default=0, ge=0, le=86_400)


class AttachPointsRewardRequest(BaseModel):
    local_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    platform: Literal["twitch", "vk"]
    reward_id: str = Field(min_length=1, max_length=128)
    coins_amount: int = Field(default=10, ge=1, le=1_000_000)


class TogglePointsRewardRequest(BaseModel):
    enabled: bool


class ConnectMemeAlertsRequest(BaseModel):
    access_token: str = Field(min_length=16, max_length=8192)
    refresh_token: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    streamer_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    auth_provider: Optional[MemeAlertsAuthProvider] = None


class GrantCoinsRequest(BaseModel):
    userId: Optional[str] = Field(default=None, min_length=1, max_length=128)
    nickname: Optional[str] = Field(default=None, min_length=1, max_length=128)
    value: int = Field(ge=1, le=1_000_000)


@router.get("/status")
async def get_memealerts_status(
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Check MemeAlerts connection status"""
    try:
        if not user or not user.get('id'):
            return {"success": True, "connected": False}

        user_id = user.get('id')
        token_repo = UserTokenRepository(db)
        token = token_repo.get_by_user_and_platform(user_id, "memealerts")

        if token and token.access_token:
            # Try to decode token to get streamer info
            try:
                access_token = decrypt_token(token.access_token)
                decoded = decode_memealerts_token(access_token) if access_token else {}
                streamer_id = _extract_memealerts_streamer_id(decoded, token.platform_user_id)
                return {
                    "success": True, 
                    "connected": True,
                    "streamer_id": streamer_id,
                    "platform_user_id": token.platform_user_id,
                    "auth_provider": _extract_saved_auth_provider(token.scopes),
                    "token_id": decoded.get("tid"),
                    "connected_at": token.created_at.isoformat() if token.created_at else None,
                    "updated_at": token.updated_at.isoformat() if token.updated_at else None,
                }
            except ValueError:
                if token.platform_user_id:
                    return {
                        "success": True,
                        "connected": True,
                        "streamer_id": token.platform_user_id,
                        "platform_user_id": token.platform_user_id,
                        "auth_provider": _extract_saved_auth_provider(token.scopes),
                        "token_id": None,
                        "connected_at": token.created_at.isoformat() if token.created_at else None,
                        "updated_at": token.updated_at.isoformat() if token.updated_at else None,
                    }
                return {
                    "success": True,
                    "connected": False,
                    "reason": "MemeAlerts token must be reconnected",
                }
        
        return {"success": True, "connected": False}
    except Exception:
        logger.exception("Error getting MemeAlerts status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/connect-url")
async def get_memealerts_connect_url(
    provider: str = Query(default="twitch"),
    user: dict = Depends(get_current_user),
):
    """
    Build the primary MemeAlerts provider auth URL with a same-origin callback page.
    """
    try:
        _ = user
        return _build_memealerts_connect_payload(provider)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error building MemeAlerts connect URL")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/connect/start")
async def start_memealerts_connect(
    provider: str = Query(default="twitch"),
    user: dict = Depends(get_current_user),
):
    """Resolve a provider-aware MemeAlerts auth URL for popup startup."""
    try:
        _ = user
        return _build_memealerts_connect_payload(provider)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error starting MemeAlerts connect flow")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/connect-redirect")
async def redirect_to_memealerts_connect(
    provider: str = Query(default="twitch"),
    user: dict = Depends(get_current_user),
):
    """
    Browser-first entrypoint for MemeAlerts auth.
    Keeps the click as a direct navigation instead of async JS choreography.
    """
    payload = _build_memealerts_connect_payload(provider)
    auth_url = str(payload.get("proxy_auth_url") or payload.get("auth_url") or "").strip()
    if not auth_url:
        raise HTTPException(status_code=500, detail="Failed to resolve MemeAlerts auth URL")
    return RedirectResponse(url=auth_url, status_code=307)


@router.get("/settings")
async def get_memealerts_settings(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Load MemeAlerts automation settings."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)
        settings = service.get_settings(user_id)
        return {"success": True, "settings": settings}
    except Exception:
        logger.exception("Error getting MemeAlerts settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/settings")
async def save_memealerts_settings(
    payload: MemeAlertsSettingsPatch,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save MemeAlerts automation settings."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)

        patch: dict = {}
        points_patch: dict = {}
        if payload.twitch is not None:
            points_patch["twitch"] = payload.twitch.model_dump(exclude_unset=True)
        if payload.vk is not None:
            points_patch["vk"] = payload.vk.model_dump(exclude_unset=True)
        if points_patch:
            patch["points_reward"] = points_patch
        if payload.points_rewards is not None:
            patch["points_rewards"] = [
                item.model_dump(exclude_unset=True)
                for item in payload.points_rewards[:3]
            ]
        if payload.donation_auto is not None:
            patch["donation_auto"] = payload.donation_auto.model_dump(exclude_unset=True)

        settings = service.save_settings(user_id, patch)
        return {"success": True, "settings": settings}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid settings payload")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error saving MemeAlerts settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rewards/create")
async def create_memealerts_points_reward(
    payload: CreatePointsRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create Twitch/VK reward that grants MemeCoins by supporter nickname."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)
        result = await service.create_points_reward(
            user_id=user_id,
            local_id=payload.local_id,
            platform=payload.platform,
            title=payload.title,
            cost=payload.cost,
            coins_amount=payload.coins_amount,
            cooldown_seconds=payload.cooldown_seconds,
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid reward parameters")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error creating MemeAlerts points reward")
        raise HTTPException(status_code=500, detail=str(exc) or "Internal server error")


@router.post("/rewards/attach")
async def attach_memealerts_points_reward(
    payload: AttachPointsRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach an existing Twitch/VK reward that grants MemeCoins by supporter nickname."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)
        result = await service.attach_points_reward(
            user_id=user_id,
            local_id=payload.local_id,
            platform=payload.platform,
            reward_id=payload.reward_id,
            coins_amount=payload.coins_amount,
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid reward parameters")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error attaching MemeAlerts points reward")
        raise HTTPException(status_code=500, detail=str(exc) or "Internal server error")


@router.patch("/rewards/{local_id}")
async def toggle_memealerts_points_reward(
    local_id: str,
    payload: TogglePointsRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable or disable one configured MemeAlerts platform reward."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)
        settings = await service.update_points_reward_enabled(
            user_id=user_id,
            local_id=local_id,
            enabled=payload.enabled,
        )
        return {"success": True, "settings": settings}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc) or "Reward not found")
    except Exception:
        logger.exception("Error toggling MemeAlerts points reward")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/rewards/{local_id}")
async def delete_memealerts_points_reward(
    local_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete one configured MemeAlerts platform reward and remove it from settings."""
    try:
        user_id = user.get("id")
        service = MemeAlertsService(db)
        settings = await service.delete_points_reward(user_id=user_id, local_id=local_id)
        return {"success": True, "settings": settings}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc) or "Reward not found")
    except Exception as exc:
        logger.exception("Error deleting MemeAlerts points reward")
        raise HTTPException(status_code=500, detail=str(exc) or "Internal server error")


@router.post("/connect")
async def connect_memealerts(
    token_data: ConnectMemeAlertsRequest = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save MemeAlerts token obtained from popup OAuth flow.
    Expects: { access_token: string, refresh_token?: string }
    """
    try:
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")

        access_token = token_data.access_token
        refresh_token = token_data.refresh_token
        hinted_streamer_id = str(token_data.streamer_id or "").strip() or None
        auth_provider = _normalize_optional_memealerts_provider(token_data.auth_provider)

        if not access_token:
            raise HTTPException(status_code=400, detail="access_token is required")

        # Keep existing DB streamer_id as a fallback, but prefer current token
        # claims because older local rows may have stored the token id (`tid`).
        existing = UserTokenRepository(db).get_by_user_and_platform(user_id, "memealerts")
        trusted_streamer_id = existing.platform_user_id if existing and existing.platform_user_id else None

        # Decode token without signature verification only for fallback claim extraction.
        # MemeAlerts may return different claim names depending on flow/version.
        decoded = {}
        try:
            decoded = decode_memealerts_token(access_token)
        except ValueError:
            logger.warning("MemeAlerts token is not a decodable JWT; validation requires an existing streamer id")

        claimed_streamer_id = _extract_memealerts_streamer_id(decoded)
        streamer_id = claimed_streamer_id or hinted_streamer_id or trusted_streamer_id
        token_scope = decoded.get("scope")

        if not streamer_id:
            raise HTTPException(
                status_code=400,
                detail="MemeAlerts token does not include a streamer id. Reconnect through MemeAlerts and try again.",
            )

        service = MemeAlertsService(db)
        try:
            await service.validate_access_token(access_token, str(streamer_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        if trusted_streamer_id:
            logger.info("MemeAlerts connect: preserving existing trusted streamer_id for user %s", user_id)
        elif hinted_streamer_id:
            logger.info(
                "MemeAlerts connect: using streamer_id from popup payload for user %s",
                user_id,
            )
        else:
            logger.info(
                "MemeAlerts token validated for streamer_id=%s, scope=%s, auth_provider=%s",
                streamer_id,
                token_scope,
                auth_provider or "unknown",
            )

        # Store token in database
        token_repo = UserTokenRepository(db)
        token_repo.upsert(
            user_id=user_id,
            platform="memealerts",
            access_token=encrypt_token(access_token),
            refresh_token=encrypt_token(refresh_token) if refresh_token else None,
            platform_user_id=str(streamer_id),
            scopes=_build_memealerts_token_scopes(auth_provider, token_scope),
        )

        logger.info(f"[OK] MemeAlerts connected for user {user_id}, streamer_id={streamer_id}")
        return {"success": True, "connected": True, "streamer_id": streamer_id}
    
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error connecting MemeAlerts")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect_memealerts(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove MemeAlerts token"""
    try:
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        token_repo = UserTokenRepository(db)
        token_repo.delete_by_user_and_platform(user_id, "memealerts")
        
        logger.info(f"[OK] MemeAlerts disconnected for user {user_id}")
        return {"success": True, "connected": False}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error disconnecting MemeAlerts")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/grant")
async def grant_coins(
    grant_data: GrantCoinsRequest = Body(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Grant MemeCoins to a user.
    Expects: { userId?: string, nickname?: string, value: number }
    """
    try:
        user_id = user.get('id')
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        target_user_id = (grant_data.userId or "").strip()
        nickname = (grant_data.nickname or "").strip()
        amount = grant_data.value
        if not target_user_id and not nickname:
            raise HTTPException(status_code=400, detail="userId or nickname is required")

        service = MemeAlertsService(db)
        result = await service.grant_coins(
            user_id=user_id,
            nickname_or_id=target_user_id or nickname,
            amount=amount,
            platform="dashboard",
            channel_name="dashboard",
            issued_by=str(user.get("username") or user_id),
            source="ui",
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": result.get("error") or "MemeAlerts grant failed",
                    "detail": result.get("detail"),
                    "status_code": result.get("status_code"),
                },
            )

        logger.info(f"[OK] MemeAlerts grant successful: {result}")
        return {"success": True, "data": result}

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error granting coins")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history")
async def get_memealerts_history(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get MemeAlerts grant/purchase history from MemeAlerts API."""
    try:
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        service = MemeAlertsService(db)
        result = await service.fetch_history(user_id=user_id, limit=limit)
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error loading MemeAlerts history")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/balances")
async def get_memealerts_balances(
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get locally known MemeAlerts balances by successful grants."""
    try:
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        service = MemeAlertsService(db)
        return await service.fetch_balances(user_id=user_id, limit=limit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error loading MemeAlerts balances")
        raise HTTPException(status_code=500, detail="Internal server error")

