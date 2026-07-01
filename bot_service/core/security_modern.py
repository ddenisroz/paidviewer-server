# bot_service/core/security_modern.py
"""
Modern security helpers built on established third-party libraries.

Replaces ad-hoc implementations with maintained solutions.
"""
import logging
import secrets
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# Security libraries
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import HTTPException, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse

from core.config import settings

logger = logging.getLogger(__name__)


# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)

# JWT setup
security = HTTPBearer()

class ModernSecurityManager:
    """Modern security manager built on established libraries."""

    def __init__(self):
        self.secret_key = settings.secret_key
        self.algorithm = settings.algorithm
        self.access_token_expire_minutes = 30  # Default 30 minutes

        logger.info("[AUTH] Modern Security Manager initialized with professional libraries")


    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token.
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_jwt_token(self, token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify JWT token and optionally enforce token type.

        `expected_type` matches payload field `type` or legacy `token_type`.
        """
        if not token or not isinstance(token, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload: Dict[str, Any] = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            if expected_type:
                token_type = payload.get("type") or payload.get("token_type")
                if token_type != expected_type:
                    logger.warning(
                        "JWT token type mismatch: expected=%s got=%s",
                        expected_type,
                        token_type,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token type",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            return payload
        except JWTError as e:
            logger.error(f"JWT verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def verify_token(self, token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
        """Backward-compatible JWT verification API."""
        return self.verify_jwt_token(token, expected_type=expected_type)

    def generate_session_id(self) -> str:
        """
        Generate a secure session ID.
        """
        return secrets.token_urlsafe(32)

    def generate_csrf_token(self) -> str:
        """
        Generate a CSRF token.
        """
        return secrets.token_urlsafe(32)

    def verify_csrf_token(self, token: str, session_token: str) -> bool:
        """
        Verify a CSRF token.
        """
        # Simple comparison is enough for the current flow.
        return token == session_token

# Global instance
modern_security_manager = ModernSecurityManager()

# Rate limiting decorators
def rate_limit(requests_per_minute: str):
    """Decorator for rate limiting."""
    return limiter.limit(requests_per_minute)

def login_rate_limit():
    """Decorator for login rate limiting."""
    return limiter.limit(settings.rate_limit_login)

# FastAPI helpers
def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """
    Return the current user ID from a JWT token.
    """
    token = credentials.credentials
    payload = modern_security_manager.verify_token(token)
    user_id: int = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    return user_id

def get_current_user_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """
    Check whether the current user has admin rights.
    """
    token = credentials.credentials
    payload = modern_security_manager.verify_token(token)
    is_admin: bool = payload.get("is_admin", False)
    return is_admin

# Rate limit error handler
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Handle rate limit errors.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": f"Rate limit exceeded: {exc.detail}"}
    )

logger.info("[AUTH] Modern Security Manager initialized with JWT")
