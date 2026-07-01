# features/drops/drops_models.py
"""
Pydantic models for Drops/Lootbox feature.
Extracted from drops_api.py for cleaner architecture.
"""
from typing import Optional
from pydantic import BaseModel, Field


class DropsConfigCreate(BaseModel):
    """Payload for creating a Drops configuration."""
    channel_name: str = Field(..., min_length=1, max_length=100)
    platform: str = Field(..., pattern="^(twitch|vk)$")
    streak_enabled: bool = True
    donation_enabled: bool = True
    mythical_enabled: bool = False
    
    # Streak thresholds
    streak_days_common: int = Field(1, ge=1, le=365)
    streak_days_rare: int = Field(3, ge=1, le=365)
    streak_days_epic: int = Field(7, ge=1, le=365)
    streak_days_legendary: int = Field(14, ge=1, le=365)
    
    # Donation thresholds  
    donation_min_amount: float = Field(50.0, ge=0.01, le=1000000)
    donation_rare_amount: float = Field(100.0, ge=0.01, le=1000000)
    donation_epic_amount: float = Field(500.0, ge=0.01, le=1000000)
    donation_legendary_amount: float = Field(1000.0, ge=0.01, le=1000000)
    
    # Mythical settings
    mythical_min_interval_hours: int = Field(2, ge=0, le=24)
    mythical_max_interval_hours: int = Field(8, ge=0, le=24)
    mythical_window_duration_minutes: int = Field(5, ge=1, le=60)
    mythical_donation_amount: float = Field(2000.0, ge=0.01, le=1000000)


class DropsConfigUpdate(BaseModel):
    """Payload for updating a Drops configuration."""
    streak_enabled: Optional[bool] = None
    donation_enabled: Optional[bool] = None
    mythical_enabled: Optional[bool] = None
    
    streak_days_common: Optional[int] = Field(None, ge=1, le=365)
    streak_days_rare: Optional[int] = Field(None, ge=1, le=365)
    streak_days_epic: Optional[int] = Field(None, ge=1, le=365)
    streak_days_legendary: Optional[int] = Field(None, ge=1, le=365)
    
    donation_min_amount: Optional[float] = Field(None, ge=0.01, le=1000000)
    donation_rare_amount: Optional[float] = Field(None, ge=0.01, le=1000000)
    donation_epic_amount: Optional[float] = Field(None, ge=0.01, le=1000000)
    donation_legendary_amount: Optional[float] = Field(None, ge=0.01, le=1000000)
    
    mythical_min_interval_hours: Optional[int] = Field(None, ge=0, le=24)
    mythical_max_interval_hours: Optional[int] = Field(None, ge=0, le=24)
    mythical_window_duration_minutes: Optional[int] = Field(None, ge=1, le=60)
    mythical_donation_amount: Optional[float] = Field(None, ge=0.01, le=1000000)
    
    # Widget settings
    widget_opening_duration_ms: Optional[int] = Field(None, ge=500, le=3000)
    widget_result_duration_ms: Optional[int] = Field(None, ge=2000, le=15000)
    widget_closing_duration_ms: Optional[int] = Field(None, ge=200, le=2000)


class DropsRewardCreate(BaseModel):
    """Payload for creating a Drops reward."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    quality_id: int = Field(..., ge=1)
    command_response: Optional[str] = Field(None, max_length=1000)
    drop_chance: float = Field(1.0, ge=0.0, le=100.0)
    reward_value: str = Field(default="", max_length=1000)
    image_url: Optional[str] = Field(None, max_length=1000)
    sound_volume: float = Field(1.0, ge=0.0, le=2.0)
    is_active: bool = True


class DropsRewardUpdate(BaseModel):
    """Payload for updating a Drops reward."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    quality_id: Optional[int] = Field(None, ge=1)
    command_response: Optional[str] = Field(None, max_length=1000)
    drop_chance: Optional[float] = Field(None, ge=0.0, le=100.0)
    reward_value: Optional[str] = Field(None, max_length=1000)
    image_url: Optional[str] = Field(None, max_length=1000)
    sound_volume: Optional[float] = Field(None, ge=0.0, le=2.0)
    is_active: Optional[bool] = None


class DropsOpenRequest(BaseModel):
    """Payload for opening a Drops reward."""
    drops_type: str = Field(..., pattern="^(streak|donation|mythical)$")
    viewer_id: str = Field(..., min_length=1, max_length=100)
    viewer_name: str = Field(..., min_length=1, max_length=100)
    donation_amount: Optional[float] = Field(None, ge=0.01)
    streak_days: Optional[int] = Field(None, ge=1)
    messages_count: Optional[int] = Field(None, ge=0)
