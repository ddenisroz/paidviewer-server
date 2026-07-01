"""TTS filter-management routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.auth import get_current_user
from core.database import get_db
from services.tts.tts_core import AddWordRequest
from services.tts.tts_service import TTSService

logger = logging.getLogger("bot_service")
filters_router = APIRouter(prefix="/api/tts", tags=["tts-filters"])


@filters_router.get("/filtered-words")
async def get_filtered_words(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the current list of TTS-filtered words."""
    try:
        tts_service = TTSService(db)
        words = await tts_service.get_filtered_words(current_user["id"])
        return {"success": True, "data": words}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting filtered words")
        raise HTTPException(status_code=500, detail="Internal server error.")


@filters_router.post("/filtered-words")
async def add_filtered_word(request: AddWordRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a word to the TTS filter."""
    try:
        tts_service = TTSService(db)
        success = await tts_service.add_filtered_word(current_user["id"], request.word, request.platform)
        if success:
            return {"success": True, "message": f"Word '{request.word}' was added to the filter."}
        raise HTTPException(status_code=400, detail="Word is already present in the filter.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error adding filtered word")
        raise HTTPException(status_code=500, detail="Internal server error.")


@filters_router.delete("/filtered-words/{word_id}")
async def delete_filtered_word(word_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove a word from the TTS filter."""
    try:
        tts_service = TTSService(db)
        success = await tts_service.remove_filtered_word(current_user["id"], word_id)
        if success:
            return {"success": True, "message": "Word removed from the filter."}
        raise HTTPException(status_code=404, detail="Word not found.")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting filtered word")
        raise HTTPException(status_code=500, detail="Internal server error.")


@filters_router.get("/filters")
async def get_filters_list(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the current user's TTS filter list."""
    try:
        tts_service = TTSService(db)
        words = await tts_service.get_filtered_words(current_user["id"])
        return {"success": True, "filters": words}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting filters")
        raise HTTPException(status_code=500, detail="Internal server error.")


@filters_router.post("/filters")
async def add_filter(request: AddWordRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Alias for adding a word to the filter."""
    return await add_filtered_word(request, current_user, db)


@filters_router.delete("/filters/{filter_id}")
async def remove_filter(filter_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Alias for removing a word from the filter."""
    return await delete_filtered_word(filter_id, current_user, db)
