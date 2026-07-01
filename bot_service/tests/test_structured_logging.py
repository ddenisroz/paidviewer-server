import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from core import structured_logging
from services.tts_handler_service import _safe_log_text_preview


def _workspace_log_path() -> Path:
    path = Path("tmp") / f"structured-logging-{uuid4().hex}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_create_file_log_handler_uses_plain_file_handler_on_windows_dev(monkeypatch):
    monkeypatch.setattr(structured_logging, "_should_use_plain_file_handler", lambda: True)

    log_path = _workspace_log_path()
    handler = structured_logging._create_file_log_handler(log_path, logging.WARNING)

    try:
        assert handler is not None
        assert handler.__class__ is logging.FileHandler
    finally:
        handler.close()
        try:
            log_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_create_file_log_handler_uses_rotation_outside_windows_dev(monkeypatch):
    monkeypatch.setattr(structured_logging, "_should_use_plain_file_handler", lambda: False)

    log_path = _workspace_log_path()
    handler = structured_logging._create_file_log_handler(log_path, logging.WARNING)

    try:
        assert handler is not None
        assert isinstance(handler, RotatingFileHandler)
    finally:
        handler.close()
        try:
            log_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def test_safe_log_text_preview_escapes_cyrillic_without_losing_content():
    preview = _safe_log_text_preview("ёжик привет", limit=6)

    assert "\\u0451" in preview
    assert "\\u0436" in preview
    assert preview.endswith("...")
