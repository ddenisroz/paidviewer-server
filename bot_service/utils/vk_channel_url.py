from typing import Optional


def normalize_vk_channel_url(channel_url: Optional[str]) -> Optional[str]:
    if not channel_url:
        return channel_url
    value = str(channel_url).strip()
    if not value:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://live.vkvideo.ru/{value}"


def extract_vk_channel_slug(channel_url: Optional[str]) -> Optional[str]:
    if not channel_url:
        return channel_url
    value = str(channel_url).strip()
    if not value:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        value = value.rstrip("/").split("/")[-1]
    # Strip query/fragment just in case malformed values were stored
    value = value.split("?", 1)[0].split("#", 1)[0].split("&", 1)[0]
    return value


def get_vk_channel_candidates(channel_url: Optional[str]) -> list[str]:
    full = normalize_vk_channel_url(channel_url)
    slug = extract_vk_channel_slug(channel_url)
    candidates = []
    # Prefer slug first: for many VK API methods this is the most reliable/fast format.
    for item in [slug, full]:
        if item and item not in candidates:
            candidates.append(item)
    return candidates
