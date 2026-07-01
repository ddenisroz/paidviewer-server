# core/project_paths.py
"""
Centralized project path management for portable runtime behavior
"""
from pathlib import Path

def get_project_root() -> Path:
    """
    Resolve the project root directory.
    Searches for .git or pyproject.toml to detect the repository root.
    """
    current_file = Path(__file__).resolve()

    # Walk up the directory tree until a project root marker is found.
    for parent in current_file.parents:
        # Check known project root markers.
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists() or (parent / "README.md").exists():
            return parent

    # Fallback to the directory two levels above bot_service.
    return current_file.parent.parent.parent

def get_bot_service_root() -> Path:
    """Return the bot_service root directory."""
    return Path(__file__).parent.parent

def get_frontend_root() -> Path:
    """Return the frontend root directory."""
    return get_project_root() / "frontend"

def get_temp_dir() -> Path:
    """Return the temporary-files directory."""
    return get_bot_service_root() / "temp"

def get_data_dir() -> Path:
    """Return the application-data directory."""
    return get_bot_service_root() / "data"

def get_logs_dir() -> Path:
    """Return the logs directory."""
    return get_bot_service_root() / "logs"

def get_backups_dir() -> Path:
    """Return the backups directory."""
    return get_bot_service_root() / "backups"

def ensure_directories():
    """Create required directories if they do not exist."""
    directories = [
        get_temp_dir(),
        get_data_dir(),
        get_logs_dir(),
        get_backups_dir(),
        get_temp_dir() / "tts_audio",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# Shared path shortcuts for runtime code.
PROJECT_ROOT = get_project_root()
BOT_SERVICE_ROOT = get_bot_service_root()
FRONTEND_ROOT = get_frontend_root()
TEMP_DIR = get_temp_dir()
DATA_DIR = get_data_dir()
LOGS_DIR = get_logs_dir()
BACKUPS_DIR = get_backups_dir()

# Ensure required directories exist on import.
ensure_directories()

