# bot_service/api/dashboard_api.py
"""
Dashboard API batch endpoint for dashboard initialization.
Combines multiple requests into a single payload to improve performance.
Refactored to use DashboardService (Clean Architecture).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.database import get_db
from auth.auth import get_current_user_optional
from services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/init")
async def get_dashboard_init(
    current_user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
) -> JSONResponse:
    """
    Batch endpoint for dashboard initialization.
    
    Returns all required data in a single request:
    - user: current user data
    - integrations: Twitch, VK, and DonationAlerts status
    - tts: TTS settings
    - chat_history: latest 50 chat messages
    
    This replaces 4-6 separate requests during the initial dashboard load.
    """
    try:
        service = DashboardService(db)
        data = await service.get_dashboard_init_data(current_user)
        
        return JSONResponse(content=data)
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("[ERROR] [DASHBOARD] Error loading init data")
        raise HTTPException(status_code=500, detail="Internal server error")
