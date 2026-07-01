"""Twitch OAuth authorization flow."""
import asyncio
import httpx
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from core.database import get_db
from core.datetime_utils import utcnow_naive
from core.config import settings
from auth.auth import get_current_user_optional
from auth.oauth_handler import oauth_handler, OAuthUserData
from constants import Platform
from core.security_modern import limiter
logger = logging.getLogger(__name__)
router = APIRouter()
TWITCH_CLIENT_ID = settings.twitch_client_id
TWITCH_CLIENT_SECRET = settings.twitch_client_secret
TWITCH_REDIRECT_URI = settings.twitch_redirect_uri
FRONTEND_URL = settings.frontend_url
TWITCH_OAUTH_NOT_CONFIGURED_DETAIL = {
    "code": "integration_not_configured",
    "platform": "twitch",
    "message": "Twitch OAuth is not configured",
}


async def _twitch_request_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """Perform a Twitch OAuth request with a short retry on network errors."""
    last_error: Optional[httpx.RequestError] = None
    for attempt in range(1, 3):
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
                return await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            last_error = exc
            logger.warning(
                "Twitch OAuth network error on attempt %s for %s: %s",
                attempt,
                url,
                exc,
            )
            if attempt < 2:
                await asyncio.sleep(0.75 * attempt)

    assert last_error is not None
    raise last_error

@router.get('/api/auth/twitch/login')
@router.get('/auth/twitch/login')
@limiter.limit(settings.rate_limit_login)
async def login_twitch(request: Request):
    """Twitch OAuth login entrypoint."""
    try:
        if not TWITCH_CLIENT_ID or not TWITCH_REDIRECT_URI:
            logger.warning('Twitch OAuth requested before integration was configured')
            raise HTTPException(status_code=503, detail=TWITCH_OAUTH_NOT_CONFIGURED_DETAIL)
        from constants import OAUTH_SCOPES
        scopes = OAUTH_SCOPES['twitch']
        logger.info(f'Twitch OAuth requested with scopes: {scopes}')
        import secrets
        state = secrets.token_urlsafe(16)
        auth_url = 'https://id.twitch.tv/oauth2/authorize?' + urlencode({
            'client_id': TWITCH_CLIENT_ID,
            'redirect_uri': TWITCH_REDIRECT_URI,
            'response_type': 'code',
            'scope': scopes,
            'state': state,
        })
        logger.info('Twitch OAuth login URL generated')
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url=auth_url)
        response.set_cookie(key='oauth_state', value=state, max_age=600, httponly=True, samesite='lax', secure=settings.is_production)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error generating Twitch login URL: {e}')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/api/auth/twitch/callback')
@router.get('/auth/twitch/callback')
@limiter.limit('20/minute')
async def twitch_callback(request: Request, db: Session=Depends(get_db), code: str=None, state: str=None, error: str=None, error_description: str=None, current_user: Optional[Dict[str, Any]]=Depends(get_current_user_optional)):
    """Handle the Twitch OAuth callback."""
    logger.info('Twitch callback received')
    is_linking = current_user is not None
    if error:
        error_code = oauth_handler.normalize_provider_error(error)
        logger.warning("Twitch OAuth provider returned error=%s mapped_to=%s description=%s", error, error_code, error_description)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, error_code, is_linking))
    if not code:
        logger.error('No authorization code received from Twitch')
        raise HTTPException(status_code=400, detail='No authorization code received from Twitch')
    expected_state = request.cookies.get('oauth_state')
    if not state or state != expected_state:
        logger.warning('Twitch OAuth CSRF state mismatch')
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'invalid_state', is_linking))
    if not all([TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_REDIRECT_URI]):
        logger.warning('Twitch callback received before integration was configured')
        raise HTTPException(status_code=503, detail=TWITCH_OAUTH_NOT_CONFIGURED_DETAIL)
    logger.info('Twitch authorization code received')
    try:
        token_response = await _twitch_request_with_retry(
            'POST',
            'https://id.twitch.tv/oauth2/token',
            params={
                'client_id': TWITCH_CLIENT_ID,
                'client_secret': TWITCH_CLIENT_SECRET,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': TWITCH_REDIRECT_URI
            }
        )
        logger.info(f'Twitch token response status: {token_response.status_code}')
        if token_response.status_code != 200:
            logger.error(f'Twitch token exchange failed. Status: {token_response.status_code}')
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'provider_rejected', is_linking))

        token_data = token_response.json()
        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        expires_in = token_data.get('expires_in', 3600)
        logger.info(f'[TWITCH AUTH] Token expires_in: {expires_in} seconds ({expires_in / 3600:.1f} hours)')
        expires_at = utcnow_naive() + timedelta(seconds=expires_in)
        scopes = token_data.get('scope', [])
        logger.info(f'Token exchange successful. Scopes: {scopes}')

        headers = {'Authorization': f'Bearer {access_token}', 'Client-ID': TWITCH_CLIENT_ID}
        user_response = await _twitch_request_with_retry('GET', 'https://api.twitch.tv/helix/users', headers=headers)
        logger.info(f'Twitch user response status: {user_response.status_code}')
        if user_response.status_code != 200:
            logger.error(f'Failed to get Twitch user info. Status: {user_response.status_code}')
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'provider_rejected', is_linking))

        user_data_response = user_response.json()
        user_info = user_data_response.get('data', [{}])[0]
        platform_user_id = user_info.get('id')
        username = user_info.get('login')
        avatar_url = user_info.get('profile_image_url')
        if not platform_user_id:
            logger.error('No user ID in Twitch response')
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'provider_rejected', is_linking))

        logger.info(f'Twitch user: {username} ({platform_user_id})')
        oauth_user_data = OAuthUserData(platform_user_id=platform_user_id, avatar_url=avatar_url, access_token=access_token, refresh_token=refresh_token, expires_at=expires_at, scopes=scopes, username=username)
        oauth_result = await oauth_handler.handle_oauth_callback(request=request, db=db, platform=Platform.TWITCH, user_data=oauth_user_data, current_user=current_user, auto_connect_bot=True)
        return oauth_handler.create_oauth_response(oauth_result)
    except httpx.RequestError as e:
        logger.error(f'Twitch auth network error: {e}', exc_info=True)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'provider_unreachable', is_linking))
    except HTTPException as e:
        logger.warning("Twitch OAuth callback failed with HTTP %s: %s", e.status_code, e.detail)
        if e.status_code >= 500:
            return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'internal_error', is_linking))
        raise
    except Exception as e:
        logger.error(f'Twitch auth error: {e}', exc_info=True)
        return RedirectResponse(url=oauth_handler.get_error_redirect_url(Platform.TWITCH, 'internal_error', is_linking))
