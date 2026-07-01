"""
VK Live API Integration (Refactored)
Facade class inheriting from modular components.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from api.vk.vk_auth import VKAuth
from api.vk.vk_stream import VKStream
from api.vk.vk_rewards import VKRewards
from core.database import get_db
from auth.auth import get_current_user, get_current_user_optional
from services.stream_info_service import StreamInfoService
logger = logging.getLogger(__name__)

class VKLiveAPI(VKRewards, VKStream, VKAuth):
    """
    Main VK Live API class acting as a facade.
    Inherits methods from:
    - VKAuth: Authentication and User Info
    - VKStream: Stream management and Categories
    - VKRewards: Channel Points and Rewards
    
    Order of inheritance matters:
    VKRewards and VKStream rely on VKAuth (or VKBase), which is at the end of MRO relative to specific methods.
    Since they don't override each other's methods, the order here is flexible.
    """

    def __init__(self):
        super().__init__()
        self.live_base_url = self.BASE_URL
vk_api = VKLiveAPI()
router = APIRouter(prefix='/api/vk', tags=['vk'])

class UpdateCategoryRequest(BaseModel):
    categoryId: str

class UpdateTitleRequest(BaseModel):
    title: str

@router.post('/update-category')
async def update_vk_category(request: UpdateCategoryRequest, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Update VK Live stream category"""
    try:
        user_id = str(current_user.get('id'))
        session_id = current_user.get('session_id')
        category_id = request.categoryId
        logger.info(f'[REFRESH] Updating VK category for user {user_id} to {category_id}')
        result = await vk_api.update_stream_category(user_id, category_id, session_id)
        if result:
            return JSONResponse(content={'success': True, 'message': 'Operation completed.'})
        else:
            raise HTTPException(status_code=400, detail='Operation failed.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error updating VK category')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.post('/update-title')
async def update_vk_title(request: UpdateTitleRequest, current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Update VK Live stream title"""
    try:
        user_id = str(current_user.get('id'))
        session_id = current_user.get('session_id')
        title = request.title
        logger.info(f"[REFRESH] Updating VK title for user {user_id} to '{title}'")
        result = await vk_api.update_stream_title(user_id, title, session_id)
        if result:
            return JSONResponse(content={'success': True, 'message': 'Operation completed.'})
        else:
            raise HTTPException(status_code=400, detail='Operation failed.')
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error updating VK title')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/categories')
async def get_vk_categories(search: str='', current_user: dict=Depends(get_current_user_optional), db: Session=Depends(get_db)):
    """Get VK Live categories list"""
    try:
        user_id = current_user.get('id') if current_user else None
        session_id = current_user.get('session_id') if current_user else None
        logger.info(f"[VK CATEGORIES] Fetching for user {user_id} with search: '{search}'")
        from repositories.user_token_repository import UserTokenRepository
        token_repo = UserTokenRepository(db)
        user_token = None
        if user_id:
            user_token = token_repo.get_by_user_and_platform(user_id, 'vk')
        if not user_token or not user_token.access_token:
            user_token = token_repo.get_first_by_platform('vk')
        if not user_token or not user_token.access_token:
            logger.warning('[ERROR] [VK CATEGORIES] No VK token available')
            raise HTTPException(status_code=503, detail='No VK token found')
        token_owner_id = str(user_token.user_id)
        categories = await vk_api.get_categories(search=search, user_id=token_owner_id, session_id=session_id)
        logger.info(f'[OK] [VK CATEGORIES] Found {len(categories)} categories')
        return JSONResponse(content={'success': True, 'categories': categories}, status_code=200)
    except HTTPException:
        raise
    except Exception:
        logger.exception('[ERROR] [VK CATEGORIES] Error')
        raise HTTPException(status_code=500, detail='Internal server error')

@router.get('/stream-info')
async def get_vk_stream_info(current_user: dict=Depends(get_current_user), db: Session=Depends(get_db)):
    """Get VK Live stream info using the shared normalized contract."""
    try:
        user_id = current_user.get('id')
        session_id = current_user.get('session_id')
        stream_info = await StreamInfoService(db).get_stream_info(user_id, "vk", session_id)
        return JSONResponse(content={"data": stream_info})
    except HTTPException:
        raise
    except Exception:
        logger.exception('Error getting VK stream info')
        raise HTTPException(status_code=500, detail='Internal server error')
