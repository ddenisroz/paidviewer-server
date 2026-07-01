# bot_service/api/obs_integration_api.py
"""OBS Integration API - manages OBS tokens for users.

Clean Architecture: uses UserRepository for data access.
"""
from typing import Literal

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from auth.auth import get_current_user, create_jwt_token
from core.security_modern import limiter
from core.config import settings
from core.connection_manager import get_connection_manager
from services.memory_websocket_manager import get_memory_websocket_manager
from repositories.user_repository import UserRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["obs-integration"])


class RegenerateTtsObsLinksRequest(BaseModel):
    target: Literal["dock", "source", "both"] = "both"


def _build_tts_dock_url(token: str) -> str:
    return f"{settings.frontend_url}/tts/obs-dock?dock_token={token}"


def _build_tts_source_url(token: str) -> str:
    return f"{settings.frontend_url}/tts-obs/{token}"


def _build_youtube_obs_url(token: str) -> str:
    return f"{settings.frontend_url}/youtube-obs/{token}"


def get_or_create_obs_token(db: Session, user_id: int, regenerate: bool = False) -> str:
    """Get existing or create new OBS token for user."""
    user_repo = UserRepository(db)
    user_record = user_repo.get_by_id(user_id)

    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_record and user_record.obs_token and not regenerate:
        return user_record.obs_token
    
    obs_token = create_jwt_token(user_id)
    
    user_repo.update_obs_token(user_id, obs_token)
    
    return obs_token


def get_or_create_tts_obs_token(
    db: Session,
    user_id: int,
    *,
    field_name: Literal["tts_dock_token", "tts_source_token"],
    token_type: Literal["tts_dock", "tts_source"],
    regenerate: bool = False,
) -> str:
    """Get or create a dedicated TTS OBS dock/source token."""
    user_repo = UserRepository(db)
    user_record = user_repo.get_by_id(user_id)
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found")

    existing_token = getattr(user_record, field_name, None)
    if existing_token and not regenerate:
        return existing_token

    token = create_jwt_token(user_id, token_type=token_type)
    user_repo.update_tts_obs_token(user_id, field_name, token)
    return token


def _build_tts_obs_links_response(db: Session, user_id: int) -> dict:
    dock_token = get_or_create_tts_obs_token(
        db,
        user_id,
        field_name="tts_dock_token",
        token_type="tts_dock",
    )
    source_token = get_or_create_tts_obs_token(
        db,
        user_id,
        field_name="tts_source_token",
        token_type="tts_source",
    )

    connection_manager = get_connection_manager()
    dock_connected = get_memory_websocket_manager().has_user_connection_for_role(user_id, "tts_player")
    source_connected = source_token in connection_manager.obs_connections
    return {
        "dock_token": dock_token,
        "source_token": source_token,
        "dock_url": _build_tts_dock_url(dock_token),
        "source_url": _build_tts_source_url(source_token),
        "dock_connected": dock_connected,
        "source_connected": source_connected,
        "has_token": bool(dock_token and source_token),
        # Legacy keys stay for old frontend/client builds.
        "obs_token": source_token,
    }


@router.get("/tts/obs-links")
@limiter.limit("60/minute")
async def get_tts_obs_links(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get dedicated OBS dock/source links for TTS."""
    try:
        return _build_tts_obs_links_response(db, user["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting TTS OBS links")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tts/obs-links/regenerate")
@limiter.limit("60/minute")
async def regenerate_tts_obs_links(
    payload: RegenerateTtsObsLinksRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate one or both dedicated TTS OBS tokens."""
    try:
        if payload.target in {"dock", "both"}:
            get_or_create_tts_obs_token(
                db,
                user["id"],
                field_name="tts_dock_token",
                token_type="tts_dock",
                regenerate=True,
            )
        if payload.target in {"source", "both"}:
            get_or_create_tts_obs_token(
                db,
                user["id"],
                field_name="tts_source_token",
                token_type="tts_source",
                regenerate=True,
            )
        return _build_tts_obs_links_response(db, user["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error regenerating TTS OBS links")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tts/obs-url")
@limiter.limit("60/minute")
async def get_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the existing OBS URL."""
    try:
        return _build_tts_obs_links_response(db, user["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting OBS URL")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/youtube/obs-url")
@limiter.limit("60/minute")
async def get_youtube_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the stable YouTube OBS URL for the current user."""
    try:
        obs_token = get_or_create_obs_token(db, user["id"])
        return {
            "youtube_obs_url": _build_youtube_obs_url(obs_token),
            "obs_token": obs_token,
            "has_token": bool(obs_token),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting YouTube OBS URL")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")



@router.post("/tts/generate-obs-url")
@limiter.limit("60/minute")
async def generate_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate an OBS WebSocket URL."""
    try:
        get_or_create_obs_token(db, user['id'])
        return _build_tts_obs_links_response(db, user["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating OBS URL")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/youtube/generate-obs-url")
@limiter.limit("60/minute")
async def generate_youtube_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a YouTube OBS WebSocket URL."""
    try:
        obs_token = get_or_create_obs_token(db, user['id'])
        return {"youtube_obs_url": _build_youtube_obs_url(obs_token), "obs_token": obs_token}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error generating YouTube OBS URL")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tts/regenerate-obs-url")
@limiter.limit("60/minute")
async def regenerate_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Regenerate the OBS URL."""
    try:
        get_or_create_obs_token(db, user['id'], regenerate=True)
        get_or_create_tts_obs_token(
            db,
            user["id"],
            field_name="tts_dock_token",
            token_type="tts_dock",
            regenerate=True,
        )
        get_or_create_tts_obs_token(
            db,
            user["id"],
            field_name="tts_source_token",
            token_type="tts_source",
            regenerate=True,
        )
        return _build_tts_obs_links_response(db, user["id"])
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error regenerating OBS URL")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/youtube/regenerate-obs-url")
@limiter.limit("60/minute")
async def regenerate_youtube_obs_url(request: Request, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Regenerate the YouTube OBS WebSocket URL."""
    try:
        obs_token = get_or_create_obs_token(db, user['id'], regenerate=True)
        return {"youtube_obs_url": _build_youtube_obs_url(obs_token), "obs_token": obs_token}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error regenerating YouTube OBS URL")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
