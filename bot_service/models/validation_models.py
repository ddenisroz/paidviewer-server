"""
Enhanced Pydantic Models with Comprehensive Validation
Provides detailed validation for all API requests
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
import re
from validators.input_validators import (
    sanitize_stream_title,
    sanitize_tts_message,
    sanitize_voice_name,
    sanitize_input,
    validate_username,
    validate_command_name,
)


class BaseValidationModel(BaseModel):
    """Base model with common validation rules"""

    class Config:
        # Forbid extra fields
        extra = "forbid"
        # Validate on assignment
        validate_assignment = True
        # Use enum values
        use_enum_values = True


# ============================================================================
# STREAM MANAGEMENT MODELS
# ============================================================================

class StreamTitleUpdateRequest(BaseValidationModel):
    """Request to update stream title"""
    title: str = Field(
        ...,
        min_length=1,
        max_length=140,
        description="Stream title (1-140 characters)"
    )
    platform: Optional[str] = Field(
        'both',
        regex=r'^(twitch|vk|both)$',
        description="Target platform"
    )

    @validator('title')
    def sanitize_title(cls, v):
        """Sanitize and validate title"""
        sanitized = sanitize_stream_title(v)
        if not sanitized:
            raise ValueError('Title cannot be empty after sanitization')
        if len(sanitized) > 140:
            raise ValueError('Title too long (max 140 characters)')
        return sanitized


class StreamCategoryUpdateRequest(BaseValidationModel):
    """Request to update stream category"""
    category_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Category ID from platform"
    )
    category_name: Optional[str] = Field(
        None,
        max_length=200,
        description="Category name (optional)"
    )
    platform: str = Field(
        ...,
        regex=r'^(twitch|vk)$',
        description="Target platform"
    )

    @validator('category_id')
    def validate_category_id(cls, v, values):
        """Validate category ID format"""
        platform = values.get('platform')

        if platform == 'vk':
            # VK uses UUID format
            uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            if not re.match(uuid_pattern, v, re.IGNORECASE):
                raise ValueError('Invalid VK category ID format (must be UUID)')
        elif platform == 'twitch':
            # Twitch uses numeric IDs
            if not v.isdigit():
                raise ValueError('Invalid Twitch category ID format (must be numeric)')

        return v


# ============================================================================
# TTS MODELS
# ============================================================================

class TtsSettingsUpdateRequest(BaseValidationModel):
    """Request to update TTS settings"""
    enabled: Optional[bool] = None
    volume: Optional[int] = Field(None, ge=0, le=100, description="Volume (0-100)")
    speed: Optional[float] = Field(None, ge=0.5, le=2.0, description="Speed (0.5-2.0)")
    voice_id: Optional[int] = Field(None, gt=0, description="Voice ID")
    max_message_length: Optional[int] = Field(
        None,
        ge=50,
        le=250,
        description="Max message length (50-250)"
    )
    min_donation_amount: Optional[float] = Field(
        None,
        ge=0,
        description="Minimum donation amount"
    )

    @validator('volume', 'speed', 'max_message_length', 'min_donation_amount')
    def validate_numeric_fields(cls, v, field):
        """Ensure numeric fields are within bounds"""
        if v is not None and field.field_info.ge is not None and v < field.field_info.ge:
            raise ValueError(f'{field.name} must be >= {field.field_info.ge}')
        if v is not None and field.field_info.le is not None and v > field.field_info.le:
            raise ValueError(f'{field.name} must be <= {field.field_info.le}')
        return v


class TtsPlatformSettingsRequest(BaseValidationModel):
    """Request to update platform-specific TTS settings"""
    enabled_platforms: List[str] = Field(
        ...,
        description="List of enabled platforms"
    )

    @validator('enabled_platforms')
    def validate_platforms(cls, v):
        """Validate platform list"""
        valid_platforms = {'twitch', 'vk'}
        if not all(p in valid_platforms for p in v):
            raise ValueError(f'Invalid platforms. Must be in {valid_platforms}')
        return v


class TtsAudioSettingsRequest(BaseValidationModel):
    """Request to update TTS audio settings"""
    website_volume: int = Field(..., ge=0, le=100, description="Website volume (0-100)")
    obs_volume: int = Field(..., ge=0, le=100, description="OBS volume (0-100)")
    speed: Optional[float] = Field(None, ge=0.5, le=2.0, description="Speed (0.5-2.0)")


class TtsMessageRequest(BaseValidationModel):
    """Request to synthesize TTS message"""
    text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Text to synthesize (1-500 characters)"
    )
    voice_id: Optional[int] = Field(None, gt=0, description="Voice ID")
    speed: Optional[float] = Field(1.0, ge=0.5, le=2.0, description="Speed (0.5-2.0)")

    @validator('text')
    def sanitize_text(cls, v):
        """Sanitize TTS message"""
        sanitized = sanitize_tts_message(v)
        if not sanitized:
            raise ValueError('Message cannot be empty after sanitization')
        if len(sanitized) > 500:
            raise ValueError('Message too long (max 500 characters)')
        return sanitized


class VoiceUploadRequest(BaseValidationModel):
    """Request to upload custom voice"""
    voice_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Voice name (1-50 characters)"
    )
    reference_text: Optional[str] = Field(
        None,
        max_length=500,
        description="Reference text for voice cloning"
    )

    @validator('voice_name')
    def sanitize_name(cls, v):
        """Sanitize voice name"""
        sanitized = sanitize_voice_name(v)
        if not sanitized:
            raise ValueError('Voice name cannot be empty after sanitization')
        return sanitized

    @validator('reference_text')
    def sanitize_reference(cls, v):
        """Sanitize reference text"""
        if v:
            return sanitize_input(v, max_length=500)
        return v


class FilteredWordRequest(BaseValidationModel):
    """Request to add filtered word"""
    word: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Word to filter (1-100 characters)"
    )
    platform: str = Field(
        'all',
        regex=r'^(twitch|vk|all)$',
        description="Target platform"
    )
    is_regex: Optional[bool] = Field(False, description="Is regex pattern")
    replacement: Optional[str] = Field(
        None,
        max_length=100,
        description="Replacement text"
    )

    @validator('word')
    def sanitize_word(cls, v):
        """Sanitize and validate word"""
        sanitized = v.strip().lower()
        if not sanitized:
            raise ValueError('Word cannot be empty')
        return sanitized

    @validator('replacement')
    def sanitize_replacement(cls, v):
        """Sanitize replacement text"""
        if v:
            return sanitize_input(v, max_length=100)
        return v


class BlockUserRequest(BaseValidationModel):
    """Request to block user from TTS"""
    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Username to block"
    )
    platform: str = Field(
        ...,
        regex=r'^(twitch|vk)$',
        description="Platform"
    )
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Block reason"
    )
    permanent: Optional[bool] = Field(True, description="Permanent block")

    @validator('username')
    def validate_username_field(cls, v):
        """Validate username"""
        return validate_username(v)

    @validator('reason')
    def sanitize_reason(cls, v):
        """Sanitize reason"""
        if v:
            return sanitize_input(v, max_length=200)
        return v


# ============================================================================
# DROPS MODELS
# ============================================================================

class DropsConfigUpdateRequest(BaseValidationModel):
    """Request to update drops configuration"""
    enabled: Optional[bool] = None
    channel_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        regex=r'^[a-zA-Z0-9_]+$',
        description="Channel name"
    )
    platform: Optional[str] = Field(
        None,
        regex=r'^(twitch|vk)$',
        description="Platform"
    )
    probabilities: Optional[Dict[str, float]] = Field(
        None,
        description="Rarity probabilities"
    )
    cooldown_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Cooldown in seconds (0-86400)"
    )

    @validator('probabilities')
    def validate_probabilities(cls, v):
        """Validate probability distribution"""
        if v is None:
            return v

        required_keys = {'common', 'rare', 'epic', 'legendary'}
        if not required_keys.issubset(v.keys()):
            raise ValueError(f'Missing required probability keys: {required_keys}')

        # Validate each probability
        for key, prob in v.items():
            if not isinstance(prob, (int, float)):
                raise ValueError(f'Probability for {key} must be a number')
            if prob < 0 or prob > 100:
                raise ValueError(f'Probability for {key} must be between 0 and 100')

        # Validate sum
        total = sum(v.values())
        if abs(total - 100) > 0.01:
            raise ValueError(f'Probabilities must sum to 100 (got {total})')

        return v


class DropsRewardRequest(BaseValidationModel):
    """Request to create/update drops reward"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Reward name (1-100 characters)"
    )
    rarity: str = Field(
        ...,
        regex=r'^(common|rare|epic|legendary|mythical)$',
        description="Reward rarity"
    )
    value: Optional[float] = Field(None, ge=0, description="Reward value")
    is_active: Optional[bool] = Field(True, description="Is reward active")

    @validator('name')
    def sanitize_name(cls, v):
        """Sanitize reward name"""
        sanitized = sanitize_input(v, max_length=100)
        if not sanitized:
            raise ValueError('Reward name cannot be empty')
        return sanitized


# ============================================================================
# COMMAND MODELS
# ============================================================================

class CommandCreateRequest(BaseValidationModel):
    """Request to create custom command"""
    command_name: str = Field(
        ...,
        min_length=1,
        max_length=25,
        regex=r'^[a-zA-Z0-9_]+$',
        description="Command name (alphanumeric and underscore only)"
    )
    response_text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Command response (1-500 characters)"
    )
    cooldown_seconds: Optional[int] = Field(
        0,
        ge=0,
        le=3600,
        description="Cooldown in seconds (0-3600)"
    )
    is_enabled: Optional[bool] = Field(True, description="Is command enabled")

    @validator('command_name')
    def validate_command(cls, v):
        """Validate command name"""
        return validate_command_name(v)

    @validator('response_text')
    def sanitize_response(cls, v):
        """Sanitize response text"""
        sanitized = sanitize_input(v, max_length=500)
        if not sanitized:
            raise ValueError('Response text cannot be empty')
        return sanitized


# ============================================================================
# REWARD MODELS (Channel Points)
# ============================================================================

class RewardCreateRequest(BaseValidationModel):
    """Request to create channel points reward"""
    title: str = Field(
        ...,
        min_length=1,
        max_length=45,
        description="Reward title (1-45 characters)"
    )
    description: Optional[str] = Field(
        '',
        max_length=200,
        description="Reward description (max 200 characters)"
    )
    cost: int = Field(
        ...,
        ge=1,
        le=1000000000,
        description="Reward cost in points"
    )
    repair_timeout: Optional[int] = Field(
        0,
        ge=0,
        le=86400,
        description="Cooldown in seconds (0-86400)"
    )
    max_uses_count: Optional[int] = Field(
        0,
        ge=0,
        description="Max total uses (0 = unlimited)"
    )
    max_uses_count_per_user: Optional[int] = Field(
        0,
        ge=0,
        description="Max uses per user (0 = unlimited)"
    )
    is_message_required: Optional[bool] = Field(
        False,
        description="Require user message"
    )
    global_cooldown_seconds: Optional[int] = Field(
        0,
        ge=0,
        le=86400,
        description="Global cooldown (0-86400)"
    )

    @validator('title')
    def sanitize_title(cls, v):
        """Sanitize reward title"""
        sanitized = sanitize_input(v, max_length=45)
        if not sanitized:
            raise ValueError('Title cannot be empty')
        return sanitized

    @validator('description')
    def sanitize_description(cls, v):
        """Sanitize reward description"""
        if v:
            return sanitize_input(v, max_length=200)
        return v


# ============================================================================
# USER SETTINGS MODELS
# ============================================================================

class UserSettingsUpdateRequest(BaseValidationModel):
    """Request to update user settings"""
    display_name: Optional[str] = Field(
        None,
        max_length=50,
        regex=r"^[a-zA-Z\u0400-\u04FF0-9\s_-]*$",
        description="Display name"
    )
    notifications_enabled: Optional[bool] = None
    theme: Optional[str] = Field(
        None,
        regex=r'^(light|dark|auto)$',
        description="UI theme"
    )
    language: Optional[str] = Field(
        None,
        regex=r'^(ru|en)$',
        description="Interface language"
    )

    @validator('display_name')
    def sanitize_display_name(cls, v):
        """Sanitize display name"""
        if v:
            return sanitize_input(v, max_length=50)
        return v

# ============================================================================
# YOUTUBE MODELS
# ============================================================================

class YouTubeSettingsUpdateRequest(BaseValidationModel):
    """Request to update YouTube settings"""
    enabled: Optional[bool] = None
    max_queue_size: Optional[int] = Field(
        None,
        ge=1,
        le=100,
        description="Max queue size (1-100)"
    )
    max_video_duration: Optional[int] = Field(
        None,
        ge=60,
        le=3600,
        description="Max video duration in seconds (60-3600)"
    )
    auto_play: Optional[bool] = None
    volume: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Volume (0-100)"
    )


# ============================================================================
# ERROR REPORTING MODELS
# ============================================================================

class FrontendErrorReport(BaseValidationModel):
    """Frontend error report"""
    type: str = Field(
        ...,
        regex=r'^(react_error|route_error|feature_error|api_error|unknown)$',
        description="Error type"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Error message"
    )
    stack: Optional[str] = Field(
        None,
        max_length=5000,
        description="Error stack trace"
    )
    url: Optional[str] = Field(
        None,
        max_length=500,
        description="URL where error occurred"
    )
    user_agent: Optional[str] = Field(
        None,
        max_length=500,
        description="User agent string"
    )

    @validator('message', 'stack')
    def sanitize_error_fields(cls, v, field):
        """Sanitize error fields"""
        if v:
            max_len = field.field_info.max_length
            return sanitize_input(v, max_length=max_len)
        return v

