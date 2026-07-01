# bot_service/api/tts/synthesis_routes.py
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.project_paths import TEMP_DIR
from core.database import get_db
from auth.auth import get_current_user
from services.tts.tts_service import TTSService

logger = logging.getLogger('bot_service')

tts_router = APIRouter(prefix="/api/tts", tags=["tts"])

def get_tts_service(db: Session = Depends(get_db)) -> TTSService:
    return TTSService(db)

@tts_router.get("/audio/{filename}")
async def get_tts_audio(filename: str) -> FileResponse:
    """
    Serve synthesized TTS audio files from temp storage.
    """
    safe_name = Path(filename).name
    audio_path = TEMP_DIR / "tts_audio" / safe_name
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")

    media_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
    return FileResponse(path=audio_path, media_type=media_type, filename=safe_name)

@tts_router.post("/synthesize")
async def synthesize_text(
    request: Request,
    user: dict = Depends(get_current_user),
    service: TTSService = Depends(get_tts_service)
):
    """
    Experimental endpoint for synthesis via new Architecture.
    Delegates to TTSService.
    """
    try:
        data = await request.json()
        text = data.get("text")
        raw_voice = data.get("voice")
        voice = str(raw_voice).strip() if raw_voice is not None else None
        # Optional params
        channel = data.get("channel")
        platform = data.get("platform", "twitch")
        priority = data.get("priority", 1)

        if not text:
            raise HTTPException(status_code=400, detail="Text is required")

        result = await service.synthesize(
            text=text,
            user=user,
            voice=voice,
            channel=channel,
            platform=platform,
            priority=priority
        )

        if not result.get("success"):
            # Check for specific errors like Rate Limit
            if "Rate limit" in result.get("error", ""):
                 raise HTTPException(status_code=429, detail="Rate limit exceeded")
            raise HTTPException(status_code=500, detail="Internal server error")

        return result

    except HTTPException:
        raise
    except Exception:
        logger.exception("Synthesis error")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")



