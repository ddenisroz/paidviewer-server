# bot_service/tests/conftest.py
"""
Pytest Configuration and Fixtures

Provides reusable fixtures for testing:
- Database setup/teardown
- Test client
- Authenticated users
- Mock data
"""

import pytest
import os
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from pathlib import Path

TEST_TMP_ROOT = Path(__file__).parent / ".pytest_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

# Set testing environment
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["TWITCH_CLIENT_ID"] = "test_client_id"
os.environ["TWITCH_CLIENT_SECRET"] = "test_client_secret"
os.environ["VK_TOKEN"] = "test_vk_token"
os.environ["OPENAI_API_KEY"] = "test_openai_key"
os.environ["DEBUG"] = "true"
os.environ["TOKEN_ENCRYPTION_KEY"] = "2bD0gYfJwRo_-esxNUFDXL9uBeb5GsyhQOdE31jj4n4="
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["TEMP"] = str(TEST_TMP_ROOT)
os.environ["TMP"] = str(TEST_TMP_ROOT)
os.environ["ENV_FILE"] = str(Path(__file__).with_name(".env.test"))

# Add bot_service to path
import sys

BOT_SERVICE_ROOT = Path(__file__).parent.parent
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

from core.database import Base, get_db  # noqa: E402
from main import app  # noqa: E402
from models import User, UserToken, TTSUserSettings, YouTubeQueue, DropsConfig  # noqa: E402
from services.advanced_rate_limiter import advanced_rate_limiter  # noqa: E402

# Test database setup
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_test_rate_limiter():
    """Сбрасывает глобальный in-memory rate limiter между тестами."""
    advanced_rate_limiter.reset_state()
    yield
    advanced_rate_limiter.reset_state()


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """
    Alias for db fixture for backward compatibility.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """
    Create a fresh database for each test.

    This ensures test isolation - each test gets a clean database.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """
    Create a test client with database override.

    Usage:
        def test_endpoint(client):
            response = client.get("/api/endpoint")
            assert response.status_code == 200
    """

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Override session_manager's validate_session to use test database
    from core.session_manager import session_manager

    original_validate = session_manager.validate_session

    def test_validate_session(session_id: str):
        """Test version of validate_session that uses test database"""
        if not session_id or len(session_id) < 10:
            return None

        try:
            # Query test database directly
            from models.user import UserSession as UserSessionModel, User as UserModel

            session = (
                db.query(UserSessionModel)
                .filter_by(session_id=session_id, is_active=True)
                .first()
            )
            if not session:
                return None

            user = db.query(UserModel).filter_by(id=session.user_id).first()
            if not user:
                return None

            login_platform = None
            if session.device_info and isinstance(session.device_info, dict):
                login_platform = session.device_info.get("platform")

            return {
                "user_id": user.id,
                "id": user.id,
                "session_id": session_id,
                "is_admin": user.role == "admin",
                "is_blocked": user.is_blocked,
                "blocked_reason": user.blocked_reason,
                "blocked_at": user.blocked_at,
                "integrations": {},
                "login_platform": login_platform,
            }
        except Exception as e:
            import traceback

            print(f"[TEST] validate_session error: {e}")
            traceback.print_exc()
            return None

    session_manager.validate_session = test_validate_session

    # Override user_cache.get() to use test database
    from core.user_cache import user_cache

    original_user_cache_get = user_cache.get

    def test_user_cache_get(user_id: int, db_session=None):
        """Test version of user_cache.get that uses test database"""
        # Always use test database, ignore cache
        from models.user import User as UserModel

        user = db.query(UserModel).filter_by(id=user_id).first()
        if not user:
            return None

        return {
            "id": user.id,
            "role": user.role,
            "is_admin": user.role == "admin",
            "is_active": user.is_active,
            "is_blocked": user.is_blocked,
            "blocked_reason": user.blocked_reason,
            "twitch_username": user.twitch_username,
            "vk_username": user.vk_username,
            "vk_channel_name": user.vk_channel_name,
            "donationalerts_user_id": user.donationalerts_user_id,
            "twitch_is_broadcaster": user.twitch_is_broadcaster,
            "twitch_is_moderator": user.twitch_is_moderator,
            "twitch_is_vip": user.twitch_is_vip,
            "twitch_is_subscriber": user.twitch_is_subscriber,
            "vk_is_owner": user.vk_is_owner,
            "vk_is_moderator": user.vk_is_moderator,
        }

    user_cache.get = test_user_cache_get

    with TestClient(app) as test_client:
        yield test_client

    # Restore original functions
    session_manager.validate_session = original_validate
    user_cache.get = original_user_cache_get
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session) -> User:
    """
    Create a test user.

    Returns:
        User object with basic settings
    """
    user = User(
        twitch_username="test_user",
        role="user",
        is_active=True,
        tts_enabled=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_session(db: Session, test_user: User) -> str:
    """
    Create a test session for a user.

    Returns:
        Session ID string
    """
    from core.datetime_utils import utcnow_naive
    from models.user import UserSession as UserSessionModel
    import uuid

    # Create session directly in test database
    session_id = str(uuid.uuid4())

    new_session = UserSessionModel(
        user_id=test_user.id,
        session_id=session_id,
        device_info={"platform": "test"},
        is_active=True,
        created_at=utcnow_naive(),
        last_activity=utcnow_naive(),
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return session_id


@pytest.fixture
def admin_user(db: Session) -> User:
    """
    Create an admin user.

    Returns:
        User object with admin privileges
    """
    user = User(
        twitch_username="admin_user",
        role="admin",  # This is the key field for admin access
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user_token(db: Session, test_user: User) -> str:
    """
    Create a JWT token for a regular test user.

    Returns:
        JWT token string
    """
    from core.security_modern import modern_security_manager

    token = modern_security_manager.create_access_token(
        {
            "user_id": test_user.id,
            "sub": str(test_user.id),
            "is_admin": False,
        }
    )
    return token


@pytest.fixture
def test_admin_token(db: Session, admin_user: User) -> str:
    """
    Create a JWT token for an admin user.

    Returns:
        JWT token string for admin access
    """
    from core.security_modern import modern_security_manager

    token = modern_security_manager.create_access_token(
        {
            "user_id": admin_user.id,
            "sub": str(admin_user.id),
            "is_admin": True,
        }
    )
    return token


def _bootstrap_csrf(client: TestClient) -> None:
    """Fetch CSRF cookie and attach matching header for state-changing requests."""
    client.get("/api/auth/status")
    csrf_token = client.cookies.get("csrf_token")
    if csrf_token:
        client.headers.update({"X-CSRF-Token": csrf_token})


@pytest.fixture
def authenticated_client(
    client: TestClient, test_user: User, db: Session
) -> TestClient:
    """
    Create an authenticated test client.

    Usage:
        def test_protected_endpoint(authenticated_client):
            response = authenticated_client.get("/api/protected")
            assert response.status_code == 200
    """
    # Create session in database
    from core.database import UserSession
    from core.datetime_utils import utcnow_naive
    import uuid

    session_id = str(uuid.uuid4())

    # Create session in database with proper timestamps
    new_session = UserSession(
        user_id=test_user.id,
        session_id=session_id,
        device_info={"platform": "twitch"},
        is_active=True,
        created_at=utcnow_naive(),
        last_activity=utcnow_naive(),
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Set cookie
    client.cookies.set("session_id", session_id)
    _bootstrap_csrf(client)

    return client


@pytest.fixture
def admin_client(client: TestClient, admin_user: User, db: Session) -> TestClient:
    """
    Create an authenticated admin client.

    Usage:
        def test_admin_endpoint(admin_client):
            response = admin_client.get("/api/admin/users")
            assert response.status_code == 200
    """
    # Create session in database
    from core.database import UserSession
    from core.datetime_utils import utcnow_naive
    import uuid

    session_id = str(uuid.uuid4())

    # Create session in database with proper timestamps
    new_session = UserSession(
        user_id=admin_user.id,
        session_id=session_id,
        device_info={"platform": "twitch"},
        is_active=True,
        created_at=utcnow_naive(),
        last_activity=utcnow_naive(),
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Set cookie
    client.cookies.set("session_id", session_id)
    _bootstrap_csrf(client)

    return client


@pytest.fixture
def user_with_token(db: Session, test_user: User) -> tuple[User, UserToken]:
    """
    Create a user with an OAuth token.

    Returns:
        Tuple of (User, UserToken)
    """
    token = UserToken(
        user_id=test_user.id,
        platform="twitch",
        platform_user_id="12345",
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        scopes="chat:read chat:write",
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return test_user, token


@pytest.fixture
def user_with_tts(db: Session, test_user: User) -> tuple[User, TTSUserSettings]:
    """
    Create a user with TTS settings.

    Returns:
        Tuple of (User, TTSUserSettings)
    """
    test_user.tts_enabled = True

    tts_settings = TTSUserSettings(
        user_id=test_user.id,
        platform="twitch",
        voice_id=1,
        volume=1.0,
        speed=1.0,
    )
    db.add(tts_settings)
    db.commit()
    db.refresh(tts_settings)
    return test_user, tts_settings


@pytest.fixture
def youtube_queue_items(db: Session, test_user: User) -> list[YouTubeQueue]:
    """
    Create test YouTube queue items.

    Returns:
        List of YouTubeQueue objects
    """
    items = [
        YouTubeQueue(
            user_id=test_user.id,
            video_id="video1",
            title="Test Video 1",
            status="pending",
        ),
        YouTubeQueue(
            user_id=test_user.id,
            video_id="video2",
            title="Test Video 2",
            status="pending",
        ),
        YouTubeQueue(
            user_id=test_user.id,
            video_id="video3",
            title="Test Video 3",
            status="playing",
        ),
    ]

    for item in items:
        db.add(item)

    db.commit()

    for item in items:
        db.refresh(item)

    return items


@pytest.fixture
def drops_config(db: Session, test_user: User) -> DropsConfig:
    """
    Create test drops configuration.

    Returns:
        DropsConfig object
    """
    config = DropsConfig(
        user_id=test_user.id,
        enabled=True,
        cost=100,
        cooldown_seconds=300,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


# Mock fixtures for external services


@pytest.fixture
def mock_twitch_api(monkeypatch):
    """
    Mock Twitch API calls.

    Usage:
        def test_twitch_integration(mock_twitch_api):
            # Twitch API calls will be mocked
            pass
    """

    class MockTwitchAPI:
        def get_user(self, user_id: str):
            return {
                "id": user_id,
                "login": "test_user",
                "display_name": "Test User",
            }

        def get_stream(self, user_id: str):
            return {
                "id": "stream123",
                "user_id": user_id,
                "game_name": "Just Chatting",
                "viewer_count": 100,
            }

    return MockTwitchAPI()


@pytest.fixture
def mock_vk_api(monkeypatch):
    """
    Mock VK API calls.

    Usage:
        def test_vk_integration(mock_vk_api):
            # VK API calls will be mocked
            pass
    """

    class MockVKAPI:
        def get_user(self, user_id: str):
            return {
                "id": user_id,
                "first_name": "Test",
                "last_name": "User",
            }

        def get_stream(self, user_id: str):
            return {
                "id": "stream123",
                "owner_id": user_id,
                "title": "Test Stream",
                "viewers": 50,
            }

    return MockVKAPI()


@pytest.fixture
def mock_tts_service(monkeypatch):
    """
    Mock TTS service calls.

    Usage:
        def test_tts(mock_tts_service):
            # TTS service calls will be mocked
            pass
    """

    class MockTTSService:
        async def synthesize(self, text: str, voice_id: int):
            return {
                "audio_url": "http://example.com/audio.mp3",
                "duration": 5.0,
            }

    return MockTTSService()


# Utility functions for tests


def create_test_user(db: Session, **kwargs) -> User:
    """
    Helper function to create a test user with custom attributes.

    Usage:
        user = create_test_user(db, twitch_username="custom_user", is_admin=True)
    """
    defaults = {
        "twitch_username": "test_user",
        "is_admin": False,
        "is_active": True,
    }
    defaults.update(kwargs)

    user = User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def assert_response_success(response, expected_status: int = 200):
    """
    Assert that response is successful.

    Usage:
        response = client.get("/api/endpoint")
        assert_response_success(response)
    """
    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "success" in data or response.status_code < 400


def assert_response_error(response, expected_status: int = 400):
    """
    Assert that response is an error.

    Usage:
        response = client.get("/api/invalid")
        assert_response_error(response, 404)
    """
    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}"
    )
