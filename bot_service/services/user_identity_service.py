"""Utilities for authenticated user identity handling."""

from enum import Enum
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class UserType(Enum):
    AUTHENTICATED = "authenticated"


class UserIdentityService:
    """Helper methods for authenticated user identity and scoping."""

    @staticmethod
    def _require_user_id(user: Dict[str, Any]) -> int:
        if not isinstance(user, dict):
            raise ValueError("User payload must be a dict")

        user_id = user.get("id")
        if user_id in (None, "", False):
            raise ValueError("Authenticated user must have id")

        try:
            normalized_user_id = int(user_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Authenticated user must have numeric id") from exc

        if normalized_user_id <= 0:
            raise ValueError("Authenticated user must have positive id")

        return normalized_user_id

    @staticmethod
    def get_user_type(user: Dict[str, Any]) -> UserType:
        UserIdentityService._require_user_id(user)
        return UserType.AUTHENTICATED

    @staticmethod
    def get_user_identifier(user: Dict[str, Any]) -> str:
        return str(UserIdentityService._require_user_id(user))

    @staticmethod
    def get_database_filters(user: Dict[str, Any]) -> Dict[str, Any]:
        return {"user_id": UserIdentityService._require_user_id(user)}

    @staticmethod
    def create_settings_record_data(user: Dict[str, Any]) -> Dict[str, Any]:
        return {"user_id": UserIdentityService._require_user_id(user)}

    @staticmethod
    def get_websocket_user_id(user: Dict[str, Any]) -> str:
        return UserIdentityService.get_user_identifier(user)

    @staticmethod
    def get_rate_limit_id(user: Dict[str, Any]) -> str:
        return UserIdentityService.get_user_identifier(user)

    @staticmethod
    def get_tts_channel_name(user: Dict[str, Any]) -> str:
        return f"user_{UserIdentityService._require_user_id(user)}"

    @staticmethod
    def log_user_operation(operation: str, user: Dict[str, Any], **kwargs):
        log_data = {
            "operation": operation,
            "user_type": UserType.AUTHENTICATED.value,
            "identifier": UserIdentityService.get_user_identifier(user),
            **kwargs,
        }
        logger.info("User operation: %s", log_data)

    @staticmethod
    def validate_user_data(user: Dict[str, Any]) -> bool:
        try:
            UserIdentityService._require_user_id(user)
            return True
        except ValueError:
            return False
        except Exception:
            logger.exception("User data validation failed")
            return False

