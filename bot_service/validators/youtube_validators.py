"""YouTube URL validators and video_id extraction helpers."""

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# Regex patterns for common YouTube URL forms.
YOUTUBE_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})(?:&.*)?$",
    r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})(?:\?.*)?$",
    r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})(?:\?.*)?$",
    r"(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})(?:\?.*)?$",
]


def validate_youtube_url(url: str) -> Tuple[bool, str, str]:
    """Validate a YouTube URL and extract the video ID."""

    if not url or not isinstance(url, str):
        return False, "", "URL is empty or invalid"

    url = url.strip()
    if len(url) < 10:
        return False, "", "URL is too short"
    if len(url) > 500:
        return False, "", "URL is too long"

    if not any(domain in url.lower() for domain in ["youtube.com", "youtu.be"]):
        return False, "", "Not a YouTube URL"

    for pattern in YOUTUBE_PATTERNS:
        match = re.match(pattern, url)
        if not match:
            continue

        video_id = match.group(1)
        if len(video_id) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", video_id):
            logger.debug("[OK] Valid YouTube URL: %s -> %s", url, video_id)
            return True, video_id, ""
        return False, "", f"Invalid video ID format: {video_id}"

    return False, "", "Invalid YouTube URL format"


def is_valid_youtube_url(url: str) -> bool:
    """Return whether the provided URL is a valid YouTube URL."""

    is_valid, _, _ = validate_youtube_url(url)
    return is_valid


def extract_video_id(url: str) -> str:
    """Extract a YouTube video ID or return an empty string."""

    _, video_id, _ = validate_youtube_url(url)
    return video_id
