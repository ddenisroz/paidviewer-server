# repositories/filtered_word_repository.py
"""
Repository for Filtered Words.
Follows Clean Architecture - abstracts all database access for FilteredWord.
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import FilteredWord


class FilteredWordRepository(BaseRepository[FilteredWord]):
    """Repository for FilteredWord CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(FilteredWord, db)
    
    def get_by_user_id(self, user_id: int) -> List[FilteredWord]:
        """Get all filtered words for a user."""
        return self.db.query(FilteredWord).filter(
            FilteredWord.user_id == user_id,
            FilteredWord.is_active
        ).all()
    
    def get_words_list(self, user_id: int) -> List[Dict[str, Any]]:
        """Get filtered words as list of dicts."""
        words = self.get_by_user_id(user_id)
        
        return [
            {
                "id": w.id,
                "word": w.word,
                "platform": w.platform,
                "created_at": w.created_at.isoformat() if w.created_at else None
            }
            for w in words
        ]
    
    def add_word(
        self,
        word: str,
        platform: str = "all",
        user_id: int = None,
    ) -> Optional[FilteredWord]:
        """Add a new filtered word. Returns None if word already exists."""
        if not user_id:
            raise ValueError("user_id is required")

        # Check for existing word
        query = self.db.query(FilteredWord).filter(
            FilteredWord.word == word.lower(),
            FilteredWord.platform == platform,
            FilteredWord.is_active,
            FilteredWord.user_id == user_id,
        )
        
        if query.first():
            return None  # Word already exists
        
        new_word = FilteredWord(
            user_id=user_id,
            word=word.lower(),
            platform=platform
        )
        self.db.add(new_word)
        self.db.commit()
        self.db.refresh(new_word)
        return new_word
    
    def remove_word(
        self,
        word_id: int,
        user_id: int = None,
    ) -> bool:
        """Remove a filtered word. Returns True if successful."""
        if not user_id:
            return False

        query = self.db.query(FilteredWord).filter(
            FilteredWord.id == word_id,
            FilteredWord.user_id == user_id,
        )
        
        word = query.first()
        if not word:
            return False
        
        word.is_active = False  # Soft delete
        self.db.commit()
        return True
