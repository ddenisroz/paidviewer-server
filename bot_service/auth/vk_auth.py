"""
VK Live authentication endpoints.
"""
import asyncio
import base64
import httpx
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from core.database import get_db
from core.session_manager import session_manager
from core.config import settings
from core.datetime_utils import utcnow_naive
from core.log_sanitizer import mask_session_id
from auth.auth import get_current_user_optional
from auth.oauth_handler import oauth_handler, OAuthUserData
from constants import Platform
import secrets
from core.security_modern import limiter

logger = logging.getLogger(__name__)

router = APIRouter()

# VK Live OAuth settings from centralized configuration
VK_CLIENT_ID = settings.vk_client_id
VK_CLIENT_SECRET = settings.vk_client_secret
VK_REDIRECT_URI = settings.vk_redirect_uri
FRONTEND_URL = settings.frontend_url
VK_AUTH_BASE_URL = settings.vk_auth_base_url
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
VK_OAUTH_NOT_CONFIGURED_DETAIL = {
    "code": "integration_not_configured",
    "platform": "vk",
    "message": "VK Live OAuth is not configured",
}


async def _vk_request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Perform a VK OAuth request with a short retry on transient network errors."""
    last_error: Optional[httpx.RequestError] = None
    verify = kwargs.pop("verify", None)
    client_kwargs: Dict[str, Any] = {
        "trust_env": False,
        "timeout": 30.0,
    }
    if verify is not None:
        client_kwargs["verify"] = verify

    for attempt in range(1, 3):
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                return await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning(
                "VK OAuth network error on attempt %s for %s: %s",
                attempt,
                url,
                exc,
            )
            if attempt < 2:
                await asyncio.sleep(0.75 * attempt)

    assert last_error is not None
    raise last_error

@router.get("/auth/vk")
@limiter.limit(settings.rate_limit_login)
async def vk_auth(request: Request):
    """Start the full VK Live OAuth flow."""
    if not VK_CLIENT_ID or not VK_REDIRECT_URI:
        logger.warning("VK OAuth requested before integration was configured")
        raise HTTPException(status_code=503, detail=VK_OAUTH_NOT_CONFIGURED_DETAIL)

    from constants import OAUTH_SCOPES

    scopes = OAUTH_SCOPES["vk"]
    logger.info(f"VK OAuth requested with scopes: {scopes}")

    # Generate a CSRF protection state token.
    state = secrets.token_urlsafe(16)

    auth_url = f"{VK_AUTH_BASE_URL}?" + urlencode({
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "response_type": "code",
        "scope": scopes,
        "state": state,
    })

    logger.info("VK Live auth URL generated")

    response = RedirectResponse(url=auth_url)
    # Persist the state in a cookie for callback validation.
    response.set_cookie(
        key="oauth_state_vk",
        value=state,
        max_age=600,  # 10 minutes
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    return response

@router.get("/api/auth/vk/login")
@router.get("/auth/vk/login")
@limiter.limit(settings.rate_limit_login)
async def login_vk(request: Request):
    """Frontend-compatible entrypoint for VK login."""
    if not VK_CLIENT_ID or not VK_REDIRECT_URI:
        logger.warning("VK OAuth requested before integration was configured")
        raise HTTPException(status_code=503, detail=VK_OAUTH_NOT_CONFIGURED_DETAIL)

    from constants import OAUTH_SCOPES

    scopes = OAUTH_SCOPES["vk"]
    logger.info(f"VK OAuth requested with scopes: {scopes}")

    # Generate a CSRF protection state token.
    state = secrets.token_urlsafe(16)

    auth_url = f"{VK_AUTH_BASE_URL}?" + urlencode({
        "client_id": VK_CLIENT_ID,
        "redirect_uri": VK_REDIRECT_URI,
        "response_type": "code",
        "scope": scopes,
        "state": state,
    })

    logger.info("VK Live API login URL generated")
    from fastapi.responses import RedirectResponse
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state_vk",
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.is_production
    )
    return response

@router.get("/api/auth/vk/callback")
@router.get("/auth/vk/callback")
@limiter.limit("20/minute")
async def vk_callback(request: Request, db: Session = Depends(get_db), code: str = None, state: str = None, error: str = None, error_description: str = None, current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)):

    logger.info("[VK] OAuth callback received")
    is_linking = current_user is not None

    # Handle explicit authorization cancellation from the provider.
    if error:
        error_code = oauth_handler.normalize_provider_error(error)
        logger.warning("VK OAuth provider returned error=%s mapped_to=%s description=%s", error, error_code, error_description)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, error_code, is_linking))

    # Ensure that the provider returned an authorization code.
    if not code:
        logger.error("No authorization code received from VK")
        raise HTTPException(status_code=400, detail="No authorization code received from VK. Please try again.")

    # CSRF state validation.
    expected_state = request.cookies.get("oauth_state_vk")
    if not state or state != expected_state:
        logger.warning("VK OAuth CSRF state mismatch")
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "invalid_state", is_linking))

    if not all([VK_CLIENT_ID, VK_CLIENT_SECRET, VK_REDIRECT_URI]):
        logger.error(f"VK credentials not configured. VK_CLIENT_ID: {'[OK]' if VK_CLIENT_ID else '[X]'}, VK_CLIENT_SECRET: {'[OK]' if VK_CLIENT_SECRET else '[X]'}")
        raise HTTPException(status_code=503, detail=VK_OAUTH_NOT_CONFIGURED_DETAIL)

    logger.info("VK credentials loaded")
    logger.info("VK authorization code received")

    try:
        # Step 1: exchange the authorization code for tokens.

        # Prepare the Basic Auth header for the VK Live API.
        credentials = f"{VK_CLIENT_ID}:{VK_CLIENT_SECRET}"
        base64_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64_credentials}"
        }

        payload = {
            "grant_type": "authorization_code",
            "redirect_uri": VK_REDIRECT_URI,
            "code": code
        }

        logger.info("Requesting VK token")
        token_response = await _vk_request_with_retry(
            "POST",
            "https://api.live.vkvideo.ru/oauth/server/token",
            data=payload,
            headers=headers
        )

        logger.info(f"Token exchange response status: {token_response.status_code}")

        if token_response.status_code != 200:
            logger.error(f"VK token exchange failed. Status: {token_response.status_code}")
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "provider_rejected", is_linking))

        token_data = token_response.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = utcnow_naive() + timedelta(seconds=expires_in)

        # Read scopes from the token response.
        scope_string = token_data.get("scope", "")
        logger.info(f"[VK SCOPES] Raw scope string from API: '{scope_string}'")

        # Fall back to the requested scopes if the response does not include them.
        if not scope_string or scope_string == "":
            logger.warning("[VK SCOPES] VK API returned empty scope! Using requested scopes as fallback")
            from constants import OAUTH_SCOPES
            scopes = OAUTH_SCOPES["vk"].split(",")
            logger.info(f"[VK SCOPES] Using fallback scopes: {scopes}")
        else:
            scopes = scope_string.split(",")
            logger.info(f"[VK SCOPES] Parsed scopes: {scopes}")

        # Log the actual token lifetime for diagnostics.
        logger.info(f"[VK AUTH] Token expires_in: {expires_in} seconds ({expires_in / 3600:.1f} hours)")

        # Step 2: fetch the current user profile.
        logger.info("Attempting to get user info with token...")

        user_info = None
        ssl_verify = settings.is_production
        endpoint = "https://apidev.live.vkvideo.ru/v1/current_user"
        try:
            logger.info(f"Fetching VK user info from dev API: {endpoint}")
            user_info_response = await _vk_request_with_retry(
                "GET",
                endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                verify=ssl_verify
            )
            logger.info(f"User info response status: {user_info_response.status_code}")

            if user_info_response.status_code == 200:
                data = user_info_response.json()
                if isinstance(data, dict) and "data" in data and "user" in data["data"]:
                    user_info = data["data"]["user"]
                    channel_url = None
                    channel_obj = data["data"].get("channel") or {}
                    if isinstance(channel_obj, dict):
                        channel_url = channel_obj.get("url")
                        if not channel_url:
                            channel_url = channel_obj.get("channel_url")
                    if not channel_url:
                        channels = data["data"].get("channels")
                        if isinstance(channels, list) and channels:
                            first_channel = channels[0]
                            if isinstance(first_channel, dict):
                                channel_url = first_channel.get("url") or first_channel.get("channel_url")
                    if not channel_url:
                        user_channel = user_info.get("channel") if isinstance(user_info, dict) else None
                        if isinstance(user_channel, dict):
                            channel_url = user_channel.get("url") or user_channel.get("channel_url")
                    if not channel_url and isinstance(user_info, dict):
                        channel_url = user_info.get("channel_url")
                    user_info['channel_url'] = channel_url
                    logger.info(f"Successfully got user info: user_id={user_info.get('id')}, channel_url={channel_url}")
            else:
                logger.error(f"Failed to get user info, status: {user_info_response.status_code}")
        except httpx.RequestError:
            raise
        except Exception as e:
            logger.error(f"Error getting user info: {e}", exc_info=True)

        # Fallback: prod API can include channel URL even when dev API omits it.
        if user_info and not user_info.get("channel_url"):
            try:
                prod_endpoint = "https://api.live.vkvideo.ru/v1/current_user"
                logger.info(f"Retrying VK user info from prod API: {prod_endpoint}")
                prod_response = await _vk_request_with_retry(
                    "GET",
                    prod_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                logger.info(f"Prod user info response status: {prod_response.status_code}")
                if prod_response.status_code == 200:
                    prod_data = prod_response.json()
                    if isinstance(prod_data, dict) and "data" in prod_data:
                        prod_channel_url = None
                        prod_channel = prod_data["data"].get("channel") or {}
                        if isinstance(prod_channel, dict):
                            prod_channel_url = prod_channel.get("url") or prod_channel.get("channel_url")
                        if not prod_channel_url:
                            prod_channels = prod_data["data"].get("channels")
                            if isinstance(prod_channels, list) and prod_channels:
                                first_channel = prod_channels[0]
                                if isinstance(first_channel, dict):
                                    prod_channel_url = first_channel.get("url") or first_channel.get("channel_url")
                        if not prod_channel_url:
                            prod_user = prod_data["data"].get("user") if isinstance(prod_data.get("data"), dict) else None
                            if isinstance(prod_user, dict):
                                prod_user_channel = prod_user.get("channel")
                                if isinstance(prod_user_channel, dict):
                                    prod_channel_url = prod_user_channel.get("url") or prod_user_channel.get("channel_url")
                                if not prod_channel_url:
                                    prod_channel_url = prod_user.get("channel_url")
                        if prod_channel_url:
                            user_info["channel_url"] = prod_channel_url
                            logger.info(f"[OK] Extracted channel URL from prod API: {prod_channel_url}")
            except httpx.RequestError:
                raise
            except Exception as e:
                logger.warning(f"[WARN] Failed to fetch prod user info: {e}")

        if not user_info:
            logger.error("Could not fetch user info from VK Live API")
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "provider_rejected", is_linking))

        platform_user_id = str(user_info.get("id"))
        avatar_url = user_info.get("avatar_url")

        # Build the normalized user payload.
        # Extract the VK channel slug from the returned channel URL.
        # VK Live API returns channel.url like "https://live.vkvideo.ru/yourchy".
        channel_url = user_info.get('channel_url')
        channel_name = None
        if channel_url:
            try:
                candidate = channel_url.rstrip('/').split('/')[-1]
                if candidate and " " not in candidate:
                    channel_name = candidate
                    logger.info(f"[OK] Extracted channel name from URL: {channel_name} (from {channel_url})")
                else:
                    logger.warning(f"[WARN] Invalid VK channel slug from URL: {channel_url}")
            except Exception as e:
                logger.error(f"[ERROR] Failed to extract channel name from URL {channel_url}: {e}")

        # Display name for UI (not for channel routing).
        vk_display_name = (
            user_info.get("nick") or
            user_info.get("login") or
            user_info.get("username") or
            user_info.get("screen_name") or
            channel_name
        )
        if not vk_display_name:
            vk_display_name = f"vk{platform_user_id}"
            logger.warning("[WARN] VK API returned user_info without display name")

        oauth_user_data = OAuthUserData(
            platform_user_id=platform_user_id,
            avatar_url=avatar_url,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
            username=vk_display_name,  # Display name for UI
            channel_name=channel_name  # Channel slug for bot routing
        )

        # Use the shared OAuth handler and auto-connect the bot when a channel slug is present.
        oauth_result = await oauth_handler.handle_oauth_callback(
            request=request,
            db=db,
            platform=Platform.VK,
            user_data=oauth_user_data,
            current_user=current_user,
            auto_connect_bot=bool(channel_name)
        )

        # Build the final redirect response.
        return oauth_handler.create_oauth_response(oauth_result)

    except httpx.RequestError as e:
        logger.error(f"VK auth network error: {e}", exc_info=True)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "provider_unreachable", is_linking))
    except HTTPException as e:
        logger.warning("VK OAuth callback failed with HTTP %s: %s", e.status_code, e.detail)
        if e.status_code >= 500:
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "internal_error", is_linking))
        raise
    except Exception as e:
        logger.error(f"VK auth error: {e}", exc_info=True)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.VK, "internal_error", is_linking))

@router.get("/auth/vk/status")
async def vk_auth_status(user: dict = Depends(get_current_user_optional)):
    """Check VK integration status based on the shared session."""
    if not user:
        return {"authenticated": False, "integrations": {}}

    return {
        "authenticated": True,
        "user_id": user.get("id"),
        "integrations": user.get("integrations", {})
    }

@router.post("/auth/vk/logout")
async def vk_logout(request: Request, response: Response):
    """Log out from the shared session."""
    session_id = request.cookies.get("session_id")
    if session_id:
        # Read user data before terminating the session.
        user_data = session_manager.validate_session(session_id)
        if user_data:
            user_id = user_data.get('user_id') or user_data.get('id')

            # Disconnect bots from the user's channels.
            try:
                from startup.bot_registry import get_bot_registry
                registry = get_bot_registry()
                bot_instance = registry.twitch_bot
                vk_live_bot_instance = registry.vk_bot

                # Disconnect the Twitch bot.
                twitch_username = user_data.get('twitch_username')
                if twitch_username and bot_instance:
                    try:
                        await bot_instance.part_channels([twitch_username])
                        logger.info(f"[OK] Twitch bot disconnected from {twitch_username}")
                    except Exception as e:
                        logger.error(f"[ERROR] Error disconnecting Twitch bot: {e}")

                # Disconnect the VK Live bot.
                vk_channel = user_data.get('vk_channel_name')
                if vk_channel and vk_live_bot_instance:
                    try:
                        await vk_live_bot_instance.disconnect_from_channel(vk_channel)
                        logger.info(f"[OK] VK Live bot disconnected from {vk_channel}")
                    except Exception as e:
                        logger.error(f"[ERROR] Error disconnecting VK Live bot: {e}")

                logger.info(f"Disconnected bots for user {user_id} on VK logout")
            except Exception as e:
                logger.error(f"[ERROR] Error disconnecting bots during logout: {e}")

            # Note: do not delete integration tokens on logout.
            # Platform tokens (Twitch, VK, DonationAlerts) are expected to persist
            # across sessions so the user can log in again without losing integrations.
            # Dedicated endpoints are responsible for full integration removal.
        else:
            logger.warning(
                "Could not get user data for session %s during VK logout",
                mask_session_id(session_id),
            )

        session_manager.terminate_session(session_id, "logout")
        response.delete_cookie("session_id")

    return {"message": "Logged out successfully"}
