"""File upload validators for runtime services."""

import logging
import os
from typing import Tuple

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

try:
    import magic

    MAGIC_AVAILABLE = True
except ImportError:
    logger.warning("python-magic not installed. Magic number validation disabled.")
    MAGIC_AVAILABLE = False

MAX_VOICE_FILE_SIZE_MB = 5
MAX_REWARD_SOUND_FILE_SIZE_MB = 2
MAX_UPLOAD_FILE_SIZE_MB = 50

ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/x-wav",
    "audio/x-mpeg",
    "audio/ogg",
    "audio/webm",
    "audio/aac",
    "audio/flac",
}

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}


def validate_file_magic_number(file_path: str, allowed_types: set) -> Tuple[bool, str]:
    """Validate the real file type by magic number signature."""

    if not MAGIC_AVAILABLE:
        logger.warning("[WARN] Magic number validation skipped (python-magic not installed)")
        return True, ""

    try:
        if not os.path.exists(file_path):
            return False, "File not found"

        mime = magic.from_file(file_path, mime=True)
        if mime not in allowed_types:
            logger.warning(
                "[BLOCKED] [SECURITY] Invalid file magic number detected: %s, file: %s",
                mime,
                os.path.basename(file_path),
            )
            return False, f"Invalid file content type: {mime}. File may be malicious."

        logger.info("[OK] Valid file magic number: %s", mime)
        return True, ""
    except Exception as exc:
        logger.error("[ERROR] Error checking magic number: %s", exc)
        return False, f"Error validating file: {exc}"


class FileValidator:
    """Validator helpers for uploaded files."""

    @staticmethod
    def validate_audio_metadata(filename: str, content_type: str) -> Tuple[bool, str]:
        """Validate audio metadata without depending on UploadFile internals."""

        try:
            if content_type not in ALLOWED_AUDIO_TYPES:
                logger.warning("Invalid audio file type: %s", content_type)
                allowed_types = ", ".join(sorted(ALLOWED_AUDIO_TYPES))
                return False, f"Unsupported format. Allowed: {allowed_types}"

            if filename:
                _, ext = os.path.splitext(filename)
                ext = ext.lower()
                allowed_extensions = {".wav", ".mp3", ".ogg", ".webm", ".aac", ".flac", ".mpeg"}
                if ext not in allowed_extensions:
                    return False, f"Unsupported file extension: {ext}"

            return True, ""
        except Exception as exc:
            logger.error("Error validating audio metadata: %s", exc)
            return False, f"Validation error: {exc}"

    @staticmethod
    def validate_audio_file(file: UploadFile, max_size_mb: int = MAX_VOICE_FILE_SIZE_MB) -> Tuple[bool, str]:
        """Validate an uploaded audio file wrapper."""

        return FileValidator.validate_audio_metadata(file.filename, file.content_type)

    @staticmethod
    def validate_size_limit(size: int, max_size_mb: int) -> Tuple[bool, str]:
        """Validate a file size in bytes against a megabyte limit."""

        try:
            max_size_bytes = max_size_mb * 1024 * 1024
            if size > max_size_bytes:
                size_mb = size / (1024 * 1024)
                return False, f"File size ({size_mb:.2f} MB) exceeds the limit ({max_size_mb} MB)"

            return True, ""
        except Exception as exc:
            logger.error("Error validating size: %s", exc)
            return False, f"Size validation error: {exc}"

    @staticmethod
    def validate_file_size(file: UploadFile, max_size_mb: int = MAX_VOICE_FILE_SIZE_MB) -> Tuple[bool, str]:
        """Validate file size for an UploadFile wrapper."""

        if file.size is None:
            return True, ""
        return FileValidator.validate_size_limit(file.size, max_size_mb)

    @staticmethod
    def validate_image_file(file: UploadFile) -> Tuple[bool, str]:
        """Validate an uploaded image file."""

        try:
            if file.content_type not in ALLOWED_IMAGE_TYPES:
                allowed_types = ", ".join(sorted(ALLOWED_IMAGE_TYPES))
                return False, f"Unsupported format. Allowed: {allowed_types}"

            if file.filename:
                _, ext = os.path.splitext(file.filename)
                ext = ext.lower()
                allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
                if ext not in allowed_extensions:
                    return False, f"Unsupported file extension: {ext}"

            return True, ""
        except Exception as exc:
            logger.error("Error validating image file: %s", exc)
            return False, f"File validation error: {exc}"

    @staticmethod
    def validate_filename(filename: str, max_length: int = 255) -> Tuple[bool, str]:
        """Validate a filename for storage safety."""

        try:
            if not filename:
                return False, "Filename cannot be empty"

            if len(filename) > max_length:
                return False, f"Filename is too long (max {max_length} characters)"

            dangerous_chars = {"/", "\\", "..", "\x00", "\n", "\r"}
            for char in dangerous_chars:
                if char in filename:
                    return False, f"Filename contains a forbidden character sequence: {char!r}"

            return True, ""
        except Exception as exc:
            logger.error("Error validating filename: %s", exc)
            return False, f"Filename validation error: {exc}"


def validate_voice_file(file: UploadFile) -> str:
    """Perform the full validation flow for a voice file upload."""

    is_valid, error = FileValidator.validate_filename(file.filename)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_audio_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_file_size(file, MAX_VOICE_FILE_SIZE_MB)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    return "OK"


def validate_sound_file(file: UploadFile) -> str:
    """Perform the full validation flow for a reward sound upload."""

    is_valid, error = FileValidator.validate_filename(file.filename)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_audio_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_file_size(file, MAX_REWARD_SOUND_FILE_SIZE_MB)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    return "OK"


def validate_image_upload(file: UploadFile, max_size_mb: int = 10) -> str:
    """Perform the full validation flow for an image upload."""

    is_valid, error = FileValidator.validate_filename(file.filename)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_image_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    is_valid, error = FileValidator.validate_file_size(file, max_size_mb)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    return "OK"
