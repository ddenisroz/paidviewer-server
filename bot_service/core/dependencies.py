# core/dependencies.py
"""
Dependency injection helpers for FastAPI.

Provides centralized dependency management:
- services are created once and reused
- dependencies are easy to replace in tests
- explicit wiring replaces hidden globals
"""
from functools import lru_cache
from typing import Generator

from sqlalchemy.orm import Session

from models.base import SessionLocal


# === Database ===

def get_db() -> Generator[Session, None, None]:
    """Return a database session for a request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# === Service Factories ===

@lru_cache()
def get_whitelist_service():
    """Singleton WhitelistService."""
    from services.admin.whitelist_service import WhitelistService
    return WhitelistService()


@lru_cache()
def get_blocked_bots_service():
    """Singleton BlockedBotsService."""
    from services.admin.blocked_bots_service import BlockedBotsService
    return BlockedBotsService()


@lru_cache()
def get_user_management_service():
    """Singleton UserManagementService."""
    from services.admin.user_management_service import UserManagementService
    return UserManagementService()


@lru_cache()
def get_bot_control_service():
    """Singleton BotControlService."""
    from services.admin.bot_control_service import BotControlService
    return BotControlService()


@lru_cache()
def get_logs_service():
    """Singleton LogsService."""
    from services.admin.logs_service import LogsService
    return LogsService()


# === Dependency Injection Helpers ===

class ServiceContainer:
    """
    Service container used by tests.
    Allows swapping services with mocks.
    
    Usage:
        # Example usage in tests.
        container = ServiceContainer()
        container.whitelist_service = MockWhitelistService()
        app.dependency_overrides[get_whitelist_service] = lambda: container.whitelist_service
    """
    
    def __init__(self):
        self._whitelist_service = None
        self._blocked_bots_service = None
        self._user_management_service = None
        self._bot_control_service = None
        self._logs_service = None
    
    @property
    def whitelist_service(self):
        if self._whitelist_service is None:
            self._whitelist_service = get_whitelist_service()
        return self._whitelist_service
    
    @whitelist_service.setter
    def whitelist_service(self, value):
        self._whitelist_service = value
    
    @property
    def blocked_bots_service(self):
        if self._blocked_bots_service is None:
            self._blocked_bots_service = get_blocked_bots_service()
        return self._blocked_bots_service
    
    @blocked_bots_service.setter
    def blocked_bots_service(self, value):
        self._blocked_bots_service = value
    
    @property
    def user_management_service(self):
        if self._user_management_service is None:
            self._user_management_service = get_user_management_service()
        return self._user_management_service
    
    @user_management_service.setter
    def user_management_service(self, value):
        self._user_management_service = value
    
    @property
    def bot_control_service(self):
        if self._bot_control_service is None:
            self._bot_control_service = get_bot_control_service()
        return self._bot_control_service
    
    @bot_control_service.setter
    def bot_control_service(self, value):
        self._bot_control_service = value
    
    @property
    def logs_service(self):
        if self._logs_service is None:
            self._logs_service = get_logs_service()
        return self._logs_service
    
    @logs_service.setter
    def logs_service(self, value):
        self._logs_service = value


# Shared service container used in tests.
_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Get the service container."""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container():
    """Reset the service container for tests."""
    global _container
    _container = None
    # Clear lru_cache state as part of the reset.
    get_whitelist_service.cache_clear()
    get_blocked_bots_service.cache_clear()
    get_user_management_service.cache_clear()
    get_bot_control_service.cache_clear()
    get_logs_service.cache_clear()
