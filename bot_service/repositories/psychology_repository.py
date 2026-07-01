# bot_service/repositories/psychology_repository.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from core.database import PsychologyAnalysis
from repositories.base_repository import BaseRepository

class PsychologyRepository(BaseRepository[PsychologyAnalysis]):
    """
    Repository for PsychologyAnalysis entities.
    """
    def __init__(self, db: Session):
        super().__init__(PsychologyAnalysis, db)

    def get_recent_analysis(
        self, 
        target_username: str, 
        platform: str, 
        since: datetime
    ) -> Optional[PsychologyAnalysis]:
        """Get recent analysis for a user on a platform since a specific time."""
        return self.db.query(PsychologyAnalysis).filter(
            and_(
                PsychologyAnalysis.target_username == target_username,
                PsychologyAnalysis.platform == platform,
                PsychologyAnalysis.analysis_date >= since
            )
        ).order_by(desc(PsychologyAnalysis.analysis_date)).first()

    def add_analysis(
        self,
        target_user_id: int,
        target_username: str,
        platform: str,
        analyzed_by_user_id: int,
        analyzed_by_username: str,
        analysis_text: str,
        messages_count: int,
        ai_model_used: str = "HuggingFace DialoGPT"
    ) -> PsychologyAnalysis:
        """Create and save a new analysis record."""
        analysis = PsychologyAnalysis(
            target_user_id=target_user_id,
            target_username=target_username,
            platform=platform,
            analyzed_by_user_id=analyzed_by_user_id,
            analyzed_by_username=analyzed_by_username,
            analysis_text=analysis_text,
            messages_count=messages_count,
            ai_model_used=ai_model_used
        )
        return self.add(analysis)
