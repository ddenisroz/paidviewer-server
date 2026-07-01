# bot_service/api/commands.py
"""
Commands API.
Following Clean Architecture - only routing, no business logic.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from starlette.requests import Request

from auth.auth import get_current_user, get_current_user_optional
from core.database import get_db
from core.security_modern import limiter
from services.command_service import CommandService
from utils.enhanced_logger import commands_logger, log_request, log_response
from validators.input_validators import sanitize_input

logger = logging.getLogger("bot_service")

router = APIRouter(prefix="/api/commands", tags=["commands"])


class CommandCreate(BaseModel):
    """Payload for creating a custom command."""

    command_name: str
    response_text: str
    platforms: str = "twitch,vk"
    allowed_roles: str = "all"
    cooldown_seconds: int = 0
    is_enabled: bool = True
    extra_settings: Optional[Dict[str, Any]] = None

    @field_validator("command_name")
    @classmethod
    def sanitize_command_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Command name cannot be empty")
        return sanitize_input(value.strip().lstrip("!"), max_length=50)

    @field_validator("response_text")
    @classmethod
    def sanitize_response_text(cls, value: str) -> str:
        return sanitize_input(value, max_length=500)


class CommandUpdate(BaseModel):
    """Payload for updating a command."""

    command_name: Optional[str] = None
    alias: Optional[str] = None
    is_enabled: Optional[bool] = None
    platforms: Optional[str] = None
    allowed_roles: Optional[str] = None
    cooldown_seconds: Optional[int] = None
    response_text: Optional[str] = None
    extra_settings: Optional[Dict[str, Any]] = None

    @field_validator("response_text")
    @classmethod
    def sanitize_response_text(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            return sanitize_input(value, max_length=500)
        return value

    @field_validator("command_name", "alias")
    @classmethod
    def sanitize_optional_trigger(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.strip().lstrip("!")
        if not cleaned:
            return ""
        return sanitize_input(cleaned, max_length=50)


class CommandOverrideCreate(BaseModel):
    """Payload for creating a user override for a global command."""

    command_name: str
    alias: Optional[str] = None
    platforms: Optional[str] = None
    allowed_roles: Optional[str] = None
    cooldown_seconds: Optional[int] = None
    is_enabled: Optional[bool] = True
    extra_settings: Optional[Dict[str, Any]] = None


class CommandResponse(BaseModel):
    """Response schema with command details."""

    id: int
    command_name: str
    response_text: str
    platforms: str
    allowed_roles: str
    cooldown_seconds: int
    is_enabled: bool
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def get_command_service() -> CommandService:
    return CommandService()


def _command_error_message(status_code: int) -> str:
    if status_code == 404:
        return "Command not found"
    if status_code == 403:
        return "Insufficient permissions"
    return "Invalid command data"


def _is_not_found_error(error_text: str) -> bool:
    normalized = error_text.lower()
    return any(
        marker in normalized
        for marker in (
            "not found",
            "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d",
            "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430",
        )
    )


def _is_forbidden_error(error_text: str) -> bool:
    normalized = error_text.lower()
    return any(
        marker in normalized
        for marker in (
            "forbidden",
            "permission",
            "\u043d\u0435\u0442 \u043f\u0440\u0430\u0432",
            "\u043d\u0435\u043b\u044c\u0437\u044f",
        )
    )


@router.get("/")
async def get_commands(
    current_user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    user_id = current_user.get("id") if current_user else None
    log_request("/api/commands", "GET", None, user_id)
    commands_logger.info(
        "Getting commands for %s",
        "anonymous request" if not user_id or user_id == -1 else f"user {user_id}",
    )

    try:
        service = get_command_service()
        result = service.get_all_commands_for_user(user_id, db)
        log_response("/api/commands", 200, result)
        return result
    except HTTPException:
        raise
    except Exception:
        commands_logger.exception("[X] Error getting commands")
        log_response("/api/commands", 500, {"error": "Internal server error"})
        raise HTTPException(status_code=500, detail="Failed to load commands")


@router.get("")
async def get_commands_no_slash(
    current_user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return await get_commands(current_user, db)


@router.get("/history")
async def get_commands_history(
    platform: Optional[str] = None,
    command_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage history for user commands."""
    try:
        service = get_command_service()
        return service.get_command_history(
            user_id=current_user["id"],
            platform=platform,
            command_type=command_type,
            search=search,
            limit=limit,
            db=db,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error loading command history")
        raise HTTPException(status_code=500, detail="Failed to load command history")


@router.post("/")
@limiter.limit("20/minute")
async def create_command(
    request: Request,
    command_data: CommandCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = get_command_service()
        result = service.create_custom_command(
            user_id=current_user["id"],
            command_name=command_data.command_name,
            response_text=command_data.response_text,
            platforms=command_data.platforms,
            allowed_roles=command_data.allowed_roles,
            cooldown_seconds=command_data.cooldown_seconds,
            is_enabled=command_data.is_enabled,
            extra_settings=command_data.extra_settings,
            db=db,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Invalid command data")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating command")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create command")


@router.put("/{command_id}")
@limiter.limit("30/minute")
async def update_command(
    request: Request,
    command_id: int,
    command_data: CommandUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = get_command_service()
        result = service.update_command(
            command_id=command_id,
            user_id=current_user["id"],
            update_data=command_data.model_dump(exclude_unset=True),
            db=db,
        )
        return result
    except ValueError as exc:
        error_text = str(exc)
        status_code = 404 if _is_not_found_error(error_text) else 403 if _is_forbidden_error(error_text) else 400
        raise HTTPException(status_code=status_code, detail=error_text or _command_error_message(status_code))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating command")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update command")


@router.post("/override")
@limiter.limit("20/minute")
async def create_command_override(
    request: Request,
    override_data: CommandOverrideCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = get_command_service()
        result = service.create_command_override(
            user_id=current_user["id"],
            command_name=override_data.command_name,
            alias=override_data.alias,
            platforms=override_data.platforms,
            allowed_roles=override_data.allowed_roles,
            cooldown_seconds=override_data.cooldown_seconds,
            is_enabled=override_data.is_enabled,
            extra_settings=override_data.extra_settings,
            db=db,
        )
        return result
    except ValueError as exc:
        status_code = 404 if _is_not_found_error(str(exc)) else 400
        raise HTTPException(status_code=status_code, detail=str(exc) or _command_error_message(status_code))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating override")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create command override")


@router.delete("/{command_id}")
@limiter.limit("30/minute")
async def delete_command(
    request: Request,
    command_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service = get_command_service()
        result = service.delete_command(
            command_id=command_id,
            user_id=current_user["id"],
            db=db,
        )
        return result
    except ValueError as exc:
        status_code = 404 if _is_not_found_error(str(exc)) else 403
        raise HTTPException(status_code=status_code, detail=_command_error_message(status_code))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting command")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete command")

