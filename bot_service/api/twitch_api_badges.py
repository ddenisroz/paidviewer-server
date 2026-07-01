"""
API endpoints for retrieving Twitch badges.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from services.twitch_badges_service import get_global_badges, get_channel_badges
from core.config import settings
import logging
from cachetools import TTLCache
router = APIRouter()
logger = logging.getLogger(__name__)
_app_token_cache = TTLCache(maxsize=1, ttl=3600)
_CACHE_KEY = 'app_access_token'

async def get_cached_app_token() -> str:
    """
    Get an app access token with caching.
    
    Returns:
        access_token: Twitch App Access Token
        
    Raises:
        HTTPException: Raised when the token cannot be fetched.
    """
    if _CACHE_KEY in _app_token_cache:
        logger.debug('[OK] [CACHE HIT] Using cached App Access Token')
        return _app_token_cache[_CACHE_KEY]
    logger.debug('[ERROR] [CACHE MISS] Fetching new App Access Token')
    client_id = settings.twitch_client_id
    client_secret = settings.twitch_client_secret
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail='Twitch credentials not configured')
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post('https://id.twitch.tv/oauth2/token', params={'client_id': client_id, 'client_secret': client_secret, 'grant_type': 'client_credentials'}) as response:
            if response.status == 200:
                token_data = await response.json()
                access_token = token_data['access_token']
                _app_token_cache[_CACHE_KEY] = access_token
                logger.info('[OK] [CACHE] Stored new App Access Token (TTL: 3600s)')
                return access_token
            else:
                error_text = await response.text()
                logger.error(f'Failed to get App Access Token: {response.status} - {error_text}')
                raise HTTPException(status_code=500, detail='Failed to get App Access Token')

@router.get('/badges/global')
async def get_twitch_global_badges() -> JSONResponse:
    """
    Get the mapping of global Twitch badges (public endpoint).
    """
    try:
        client_id = settings.twitch_client_id
        access_token = await get_cached_app_token()
        badges = await get_global_badges(client_id, access_token)
        return JSONResponse(content={'success': True, 'badges': badges})
    except HTTPException:
        raise
    except Exception:
        logger.exception('[ERROR] Error fetching global badges')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/badges/channel/{identifier}')
async def get_twitch_channel_badges(identifier: str) -> JSONResponse:
    """
    Get the mapping of badges for a specific channel (public endpoint).
    Accepts either broadcaster_id (number) or username (string).
    """
    try:
        client_id = settings.twitch_client_id
        if not client_id:
            logger.error('Twitch credentials not configured')
            return JSONResponse(content={'success': True, 'badges': {}})
        access_token = await get_cached_app_token()
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            broadcaster_id = identifier
            if not identifier.isdigit():
                logger.info(f"Converting username '{identifier}' to broadcaster_id...")
                headers = {'Authorization': f'Bearer {access_token}', 'Client-Id': client_id}
                async with session.get('https://api.twitch.tv/helix/users', headers=headers, params={'login': identifier.lower()}) as user_response:
                    if user_response.status == 200:
                        user_data = await user_response.json()
                        if user_data.get('data') and len(user_data['data']) > 0:
                            broadcaster_id = user_data['data'][0]['id']
                            logger.info(f"[OK] Converted username '{identifier}' to broadcaster_id: {broadcaster_id}")
                        else:
                            logger.warning(f"User '{identifier}' not found on Twitch")
                            return JSONResponse(content={'success': True, 'badges': {}})
                    else:
                        error_text = await user_response.text()
                        logger.error(f'Failed to get user info: {user_response.status} - {error_text}')
                        return JSONResponse(content={'success': True, 'badges': {}})
            badges = await get_channel_badges(broadcaster_id, client_id, access_token)
            return JSONResponse(content={'success': True, 'badges': badges})
    except HTTPException:
        raise
    except Exception:
        logger.exception('[ERROR] Error fetching channel badges')
        return JSONResponse(content={'success': True, 'badges': {}})
