import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from core.internal_service_auth import TTSAuthConfigError, build_tts_auth_headers, build_tts_httpx_client_kwargs
from repositories.user_repository import UserRepository
from services.tts.provider_utils import (
    ProviderRoutingError,
    get_synthesis_upstream_url,
    get_voice_management_upstream_url,
    should_route_provider_via_gateway,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


def _tts_auth_headers(
    provider: str = "f5",
    *,
    upstream: str = "voice",
    use_gateway: bool | None = None,
    strict: bool = True,
) -> dict:
    try:
        return build_tts_auth_headers(
            provider=provider,
            upstream=upstream,  # type: ignore[arg-type]
            use_gateway=use_gateway,
            strict=strict,
        )
    except TTSAuthConfigError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "tts_upstream_auth_not_configured",
                "message": str(error),
            },
        ) from error


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin" or bool(user.get("is_admin", False))


@router.post("/bot-service/restart")
async def restart_bot_service(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restart bot connections (admin only)."""
    try:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin access required")

        logger.info("[REFRESH] [ADMIN] Bot service restart requested by user %s", user.get("id"))

        from startup.bot_registry import get_bot_registry

        registry = get_bot_registry()
        bot_instance = registry.twitch_bot
        vk_live_bot_instance = registry.vk_bot

        restart_results = {
            "twitch": {"status": "not_available", "message": "Bot is not active"},
            "vk": {"status": "not_available", "message": "Bot is not active"},
        }

        if bot_instance:
            try:
                logger.info("[REFRESH] [ADMIN] Restarting Twitch bot...")
                channels = list(bot_instance.connected_channels) if bot_instance.connected_channels else []

                for channel in channels:
                    try:
                        await bot_instance.part_channels([channel.name])
                    except Exception:
                        logger.exception("Error parting channel %s", channel.name)

                await asyncio.sleep(2)

                user_repo = UserRepository(db)
                active_twitch_users = user_repo.get_active_with_twitch_token()

                reconnected = 0
                for user_record in active_twitch_users:
                    if user_record.twitch_username:
                        try:
                            success = await bot_instance.join_channel(user_record.twitch_username)
                            if success:
                                reconnected += 1
                        except Exception:
                            logger.exception("Error rejoining %s", user_record.twitch_username)

                restart_results["twitch"] = {
                    "status": "restarted",
                    "message": f"Reconnected {reconnected} channel(s)",
                    "reconnected_channels": reconnected,
                }
                logger.info("[OK] [ADMIN] Twitch bot restarted, reconnected to %s channels", reconnected)
            except Exception:
                logger.exception("Error restarting Twitch bot")
                restart_results["twitch"] = {
                    "status": "error",
                    "message": "Twitch bot restart failed",
                }

        if vk_live_bot_instance:
            try:
                logger.info("[REFRESH] [ADMIN] Restarting VK bot...")

                user_repo = UserRepository(db)
                active_vk_users = user_repo.get_active_with_vk_token()

                reconnected = 0
                for user_record in active_vk_users:
                    if user_record.vk_channel_name:
                        try:
                            await vk_live_bot_instance.disconnect_from_channel(user_record.vk_channel_name)
                            await asyncio.sleep(1)
                            success = await vk_live_bot_instance.connect_to_channel(
                                user_record.vk_channel_name,
                                user_record.vk_access_token,
                            )
                            if success:
                                reconnected += 1
                        except Exception:
                            logger.exception("Error reconnecting VK channel %s", user_record.vk_channel_name)

                restart_results["vk"] = {
                    "status": "restarted",
                    "message": f"Reconnected {reconnected} channel(s)",
                    "reconnected_channels": reconnected,
                }
                logger.info("[OK] [ADMIN] VK bot restarted, reconnected to %s channels", reconnected)
            except Exception:
                logger.exception("Error restarting VK bot")
                restart_results["vk"] = {
                    "status": "error",
                    "message": "VK bot restart failed",
                }

        return {
            "success": True,
            "message": "Restart completed",
            "results": restart_results,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error restarting bot service")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tts/restart")
async def restart_tts_engine(
    user: dict = Depends(get_current_user),
):
    """Restart/check TTS engine availability (admin only)."""
    try:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin access required")

        logger.info("[REFRESH] [ADMIN] TTS engine restart requested by user %s", user.get("id"))
        try:
            tts_service_url = get_synthesis_upstream_url("f5").rstrip("/")
        except ProviderRoutingError as error:
            raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
        use_gateway = should_route_provider_via_gateway("f5")
        headers = _tts_auth_headers("f5", upstream="synthesis", use_gateway=use_gateway, strict=False)

        try:
            async with httpx.AsyncClient(timeout=5.0, **build_tts_httpx_client_kwargs()) as client:
                response = await client.get(f"{tts_service_url}/health", headers=headers)
                if response.status_code != 200:
                    raise HTTPException(status_code=502, detail=f"TTS unhealthy (status={response.status_code})")

                return {
                    "success": True,
                    "message": "TTS service healthcheck is OK",
                    "status": "healthy",
                    "note": "For full restart use infrastructure restart (e.g. docker-compose restart tts_service).",
                }
        except httpx.RequestError:
            logger.exception("Error checking TTS service")
            raise HTTPException(status_code=502, detail="TTS service offline or unreachable")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error restarting TTS engine")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tts/system/status")
async def get_tts_system_status(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy TTS system status from TTS service (admin only)."""
    try:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin access required")

        _ = db
        try:
            tts_service_url = get_voice_management_upstream_url("f5").rstrip("/")
        except ProviderRoutingError as error:
            raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
        headers = _tts_auth_headers("f5", upstream="voice")

        async with httpx.AsyncClient(timeout=10.0, **build_tts_httpx_client_kwargs()) as client:
            response = await client.get(f"{tts_service_url}/api/admin/system/status", headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "TTS system status request failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise HTTPException(status_code=response.status_code, detail="Failed to fetch TTS system status")

            return response.json()

    except HTTPException:
        raise
    except Exception:
        logger.exception("Get TTS system status error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tts/system/restart")
async def restart_tts_system(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Proxy TTS system restart to TTS service (admin only)."""
    try:
        if not _is_admin(user):
            raise HTTPException(status_code=403, detail="Admin access required")

        _ = db
        try:
            tts_service_url = get_voice_management_upstream_url("f5").rstrip("/")
        except ProviderRoutingError as error:
            raise HTTPException(status_code=400, detail={"code": str(error), "message": str(error)}) from error
        headers = _tts_auth_headers("f5", upstream="voice")

        async with httpx.AsyncClient(timeout=10.0, **build_tts_httpx_client_kwargs()) as client:
            response = await client.post(f"{tts_service_url}/api/admin/system/restart", headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "TTS system restart request failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise HTTPException(status_code=response.status_code, detail="Failed to restart TTS system")

            return response.json()

    except HTTPException:
        raise
    except Exception:
        logger.exception("Restart TTS system error")
        raise HTTPException(status_code=500, detail="Internal server error")

