"""DonationAlerts OAuth integration."""

import logging
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth.auth import get_current_user_optional
from core.config import settings
from core.database import UserToken, get_db
from core.datetime_utils import utcnow_naive
from core.security_modern import limiter
from core.token_encryption import encrypt_token

logger = logging.getLogger(__name__)

router = APIRouter()
_DONATIONALERTS_ALLOWED_AUTH_HOSTS = {"www.donationalerts.com", "donationalerts.com"}
_DONATIONALERTS_SCOPES = "oauth-user-show oauth-donation-subscribe oauth-donation-index"
_DONATIONALERTS_AUTH_ERROR_PATH = "/dashboard/media?tab=memealerts&platform=donationalerts&auth_error="

def _is_safe_donationalerts_auth_url(url: str) -> bool:
    if not isinstance(url, str) or any(ch in url for ch in ("\r", "\n", "\t")):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme == "https" and (parsed.netloc or "").lower() in _DONATIONALERTS_ALLOWED_AUTH_HOSTS


def _build_donationalerts_auth_url(state: str) -> str:
    client_id = settings.donationalerts_client_id
    redirect_uri = settings.donationalerts_redirect_uri
    if not client_id or not redirect_uri:
        logger.error("DonationAlerts integration is not configured")
        raise HTTPException(status_code=503, detail="DonationAlerts integration is not configured")

    auth_url = "https://www.donationalerts.com/oauth/authorize?" + urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _DONATIONALERTS_SCOPES,
        "state": state,
    })
    if not _is_safe_donationalerts_auth_url(auth_url):
        logger.error("Unsafe DonationAlerts auth URL generated")
        raise HTTPException(status_code=500, detail="Failed to generate secure auth URL")
    return auth_url


def _mask_config_value(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


def _donationalerts_error_redirect(error_code: str) -> str:
    return f"{settings.frontend_url}{_DONATIONALERTS_AUTH_ERROR_PATH}{error_code}"


def _donationalerts_success_redirect() -> str:
    return f"{settings.frontend_url}/dashboard/media?tab=memealerts&platform=donationalerts&da_connected=true"


async def _preflight_donationalerts_authorize(auth_url: str) -> str | None:
    """
    DonationAlerts returns raw JSON for invalid authorize requests before our callback
    can run. Probe once so the app can show a local Russian error instead.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=5.0),
            follow_redirects=False,
            headers={
                "Accept": "application/json,text/html,*/*",
                "User-Agent": "PaidViewerTools/DonationAlerts-OAuth-Preflight",
            },
        ) as client:
            response = await client.get(auth_url)
    except httpx.HTTPError as exc:
        logger.warning(
            "DonationAlerts authorize preflight skipped: %s redirect_uri=%s client_id_len=%s secret_len=%s",
            exc.__class__.__name__,
            settings.donationalerts_redirect_uri,
            len(str(settings.donationalerts_client_id or "")),
            len(str(settings.donationalerts_client_secret or "")),
        )
        return None

    if response.status_code < 400:
        return None

    body: object
    error_code: str | None = None
    try:
        body = response.json()
        if isinstance(body, dict):
            raw_error = body.get("error") or body.get("message")
            error_code = str(raw_error) if raw_error else None
    except ValueError:
        body = (response.text or "")[:500]

    auth_error = "invalid_client" if error_code == "invalid_client" else "provider_rejected"
    logger.error(
        "DonationAlerts authorize preflight failed: status=%s error=%s body=%s redirect_uri=%s client_id_len=%s client_id_mask=%s secret_len=%s",
        response.status_code,
        error_code,
        body,
        settings.donationalerts_redirect_uri,
        len(str(settings.donationalerts_client_id or "")),
        _mask_config_value(settings.donationalerts_client_id),
        len(str(settings.donationalerts_client_secret or "")),
    )
    return auth_error


def _redirect_with_state_cleanup(url: str) -> RedirectResponse:
    response = RedirectResponse(url=url)
    response.delete_cookie(
        key="oauth_state_da",
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return response


if not settings.donationalerts_client_id:
    if settings.is_development:
        logger.info("DONATIONALERTS_CLIENT_ID not configured - DonationAlerts integration disabled")
    else:
        logger.warning("DONATIONALERTS_CLIENT_ID not configured - DonationAlerts integration disabled")

if not settings.donationalerts_client_secret:
    if settings.is_development:
        logger.info("DONATIONALERTS_CLIENT_SECRET not configured - DonationAlerts integration disabled")
    else:
        logger.warning("DONATIONALERTS_CLIENT_SECRET not configured - DonationAlerts integration disabled")


@router.get("/auth/donationalerts/login")
@limiter.limit(settings.rate_limit_login)
async def donationalerts_login(
    request: Request,
    current_user: dict = Depends(get_current_user_optional),
):
    """Start DonationAlerts OAuth for an authenticated app user."""
    user_id = current_user.get("id") if current_user else None
    if not user_id or user_id <= 0:
        return RedirectResponse(url=f"{settings.frontend_url}/login?auth_error=not_authenticated")

    state = secrets.token_urlsafe(16)
    auth_url = _build_donationalerts_auth_url(state)
    logger.info(
        "DonationAlerts OAuth login redirect prepared: redirect_uri=%s client_id_len=%s client_id_mask=%s secret_len=%s scope=%s",
        settings.donationalerts_redirect_uri,
        len(str(settings.donationalerts_client_id or "")),
        _mask_config_value(settings.donationalerts_client_id),
        len(str(settings.donationalerts_client_secret or "")),
        _DONATIONALERTS_SCOPES,
    )
    auth_error = await _preflight_donationalerts_authorize(auth_url)
    if auth_error:
        return RedirectResponse(url=_donationalerts_error_redirect(auth_error))

    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state_da",
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return response


@router.get("/auth/donationalerts/callback")
@limiter.limit("20/minute")
async def donationalerts_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user_optional),
):
    """DonationAlerts OAuth callback."""
    logger.info(
        "[NOTIFY] DonationAlerts callback received: path=%s has_code=%s has_error=%s",
        request.url.path,
        bool(code),
        bool(error),
    )

    expected_state = request.cookies.get("oauth_state_da")
    if not state or not expected_state or state != expected_state:
        logger.warning(
            "DonationAlerts OAuth CSRF state mismatch: has_state=%s has_expected_state=%s",
            bool(state),
            bool(expected_state),
        )
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("invalid_state"))

    if error:
        logger.warning("DonationAlerts OAuth cancelled: %s - %s", error, error_description)
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("cancelled"))

    if not code:
        logger.error("No authorization code received from DonationAlerts")
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("no_code"))

    client_id = settings.donationalerts_client_id
    client_secret = settings.donationalerts_client_secret
    redirect_uri = settings.donationalerts_redirect_uri
    if not all([client_id, client_secret, redirect_uri]):
        logger.error("DonationAlerts credentials not configured")
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("not_configured"))

    user_id = current_user.get("id") if current_user else None
    if not user_id or user_id <= 0:
        logger.info("DonationAlerts callback without authenticated session")
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("not_authenticated"))

    try:
        logger.info("DonationAlerts callback for user %s", user_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            token_response = await client.post(
                "https://www.donationalerts.com/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            if token_response.status_code != 200:
                error_data = (
                    token_response.json()
                    if token_response.headers.get("content-type") == "application/json"
                    else token_response.text
                )
                error_code = error_data.get("error") if isinstance(error_data, dict) else None
                auth_error = "invalid_client" if error_code == "invalid_client" else "token_exchange"
                logger.error(
                    "DonationAlerts token exchange failed: status=%s error=%s body=%s redirect_uri=%s client_id_len=%s secret_len=%s",
                    token_response.status_code,
                    error_code,
                    error_data,
                    redirect_uri,
                    len(str(client_id)),
                    len(str(client_secret)),
                )
                return _redirect_with_state_cleanup(url=_donationalerts_error_redirect(auth_error))

            token_data = token_response.json()
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            if not access_token:
                logger.error("DonationAlerts token response did not contain access token")
                return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("no_access_token"))

            logger.info("[OK] DonationAlerts access token received for user %s", user_id)

            user_info_response = await client.get(
                "https://www.donationalerts.com/api/v1/user/oauth",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if user_info_response.status_code != 200:
                logger.error("Failed to get user info: %s", user_info_response.status_code)
                return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("user_info"))

            user_info = user_info_response.json()
            da_user_id = str(user_info.get("data", {}).get("id"))
            da_username = user_info.get("data", {}).get("name")
            logger.info("DonationAlerts user: %s (ID: %s)", da_username, da_user_id)

            existing_token = db.query(UserToken).filter(
                UserToken.user_id == user_id,
                UserToken.platform == "donationalerts",
            ).first()

            if existing_token:
                existing_token.access_token = encrypt_token(access_token)
                if refresh_token:
                    existing_token.refresh_token = encrypt_token(refresh_token)
                existing_token.platform_user_id = da_user_id
                existing_token.is_active = True
                existing_token.updated_at = utcnow_naive()
                logger.info("[OK] Updated DonationAlerts token for user %s", user_id)
            else:
                db.add(
                    UserToken(
                        user_id=user_id,
                        session_id=None,
                        platform="donationalerts",
                        platform_user_id=da_user_id,
                        access_token=encrypt_token(access_token),
                        refresh_token=encrypt_token(refresh_token) if refresh_token else None,
                        avatar_url=None,
                        scopes=["oauth-user-show", "oauth-donation-subscribe", "oauth-donation-index"],
                    )
                )
                logger.info("[OK] Created DonationAlerts token for user %s", user_id)

            db.commit()
            logger.info("[OK] DonationAlerts integration completed for user %s", user_id)
            return _redirect_with_state_cleanup(url=_donationalerts_success_redirect())

    except HTTPException as exc:
        logger.error("DonationAlerts callback HTTP error: %s", exc.detail)
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("callback"))
    except Exception as exc:
        logger.error("Error in DonationAlerts callback: %s", exc, exc_info=True)
        return _redirect_with_state_cleanup(url=_donationalerts_error_redirect("callback"))

