# repositories/local_tts_repository.py
"""
Repository for Local TTS Endpoint.
Follows Clean Architecture - abstracts all database access for LocalTTSEndpoint.
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from repositories.base_repository import BaseRepository
from models.tts import LocalTTSEndpoint
from core.database import WhitelistedChannel, User
from services.tts.provider_utils import normalize_local_tts_endpoint_url


class LocalTTSRepository(BaseRepository[LocalTTSEndpoint]):
    """Repository for LocalTTSEndpoint CRUD operations."""
    
    def __init__(self, db: Session):
        super().__init__(LocalTTSEndpoint, db)
    
    def get_by_user_id(self, user_id: int, provider: str = "f5") -> Optional[LocalTTSEndpoint]:
        """Get local TTS endpoint by user ID."""
        return self.db.query(LocalTTSEndpoint).filter(
            LocalTTSEndpoint.user_id == user_id,
            LocalTTSEndpoint.provider == provider,
        ).first()
    
    def get_active(self, user_id: int, provider: str = "f5") -> Optional[LocalTTSEndpoint]:
        """Get active local TTS endpoint for an authenticated user."""
        if not user_id:
            return None

        return self.db.query(LocalTTSEndpoint).filter(
            LocalTTSEndpoint.is_active,
            LocalTTSEndpoint.provider == provider,
            LocalTTSEndpoint.user_id == user_id,
        ).first()

    def get_healthy(self, user_id: int, provider: str = "f5") -> Optional[LocalTTSEndpoint]:
        """Get healthy and active local TTS endpoint."""
        endpoint = self.get_active(user_id, provider=provider)
        if endpoint and endpoint.is_healthy:
            return endpoint
        return None
    
    def create_or_update(
        self,
        endpoint_url: str,
        api_key: Optional[str] = None,
        use_local: bool = False,
        user_id: int = None,
        provider: str = "f5",
    ) -> LocalTTSEndpoint:
        """Create or update local TTS endpoint for an authenticated user."""
        normalized_endpoint_url = normalize_local_tts_endpoint_url(endpoint_url)

        if not user_id:
            raise ValueError("user_id is required")

        endpoint = self.get_by_user_id(user_id, provider=provider)

        if endpoint:
            endpoint.endpoint_url = normalized_endpoint_url
            if api_key is not None:
                endpoint.api_key = api_key
            endpoint.use_local = use_local
        else:
            endpoint = LocalTTSEndpoint(
                user_id=user_id,
                provider=provider,
                endpoint_url=normalized_endpoint_url,
                api_key=api_key,
                use_local=use_local
            )
            self.db.add(endpoint)
        
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint
    
    def update_health_status(
        self,
        endpoint: LocalTTSEndpoint,
        is_healthy: bool,
        tts_version: Optional[str] = None,
        gpu_info: Optional[Dict[str, Any]] = None
    ) -> LocalTTSEndpoint:
        """Update health status after health check."""
        from core.datetime_utils import utcnow_naive
        
        endpoint.is_healthy = is_healthy
        endpoint.last_health_check = utcnow_naive()
        
        if is_healthy:
            endpoint.health_check_failures = 0
            if tts_version:
                endpoint.tts_version = tts_version
            if gpu_info:
                endpoint.gpu_info = gpu_info
        else:
            endpoint.health_check_failures += 1
        
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get User by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def is_user_whitelisted(self, user: User, login_platform: str) -> bool:
        """Check if user is whitelisted for local TTS."""
        if login_platform == 'twitch' and user.twitch_username:
            return self.db.query(WhitelistedChannel).filter(
                WhitelistedChannel.channel_name == user.twitch_username.lower(),
                WhitelistedChannel.platform == 'twitch'
            ).first() is not None
        elif login_platform == 'vk' and user.vk_username:
            return self.db.query(WhitelistedChannel).filter(
                WhitelistedChannel.channel_name == user.vk_username.lower(),
                WhitelistedChannel.platform == 'vk'
            ).first() is not None
        return False
    
    def toggle_use_local(self, endpoint: LocalTTSEndpoint) -> LocalTTSEndpoint:
        """Toggle use_local flag."""
        endpoint.use_local = not endpoint.use_local
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint

    def set_use_local(self, endpoint: LocalTTSEndpoint, use_local: bool) -> LocalTTSEndpoint:
        """Mirror compatibility use_local flag without treating it as routing source of truth."""
        endpoint.use_local = use_local
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint
    
    def disable_local(self, endpoint: LocalTTSEndpoint) -> LocalTTSEndpoint:
        """Disable local TTS (set use_local to False)."""
        endpoint.use_local = False
        self.db.commit()
        return endpoint

