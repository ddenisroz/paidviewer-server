# bot_service/api/proxy_api.py
"""Proxy endpoints for external resources (7TV emotes, etc.)."""

import logging
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

ALLOWED_DOMAINS = [
    "7tv.io",
    "api.7tv.app",
    "cdn.7tv.app",
    "emotes.7tv.app",
    "media.7tv.app",
]

CACHE_CONTROL = "public, max-age=86400"  # 24 hours
METADATA_CACHE_CONTROL = "public, max-age=900"  # 15 minutes
TRANSPARENT_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
IMAGE_EXTENSIONS = (".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp")


def _is_image_proxy_path(resource_path: str) -> bool:
    return resource_path.lower().endswith(IMAGE_EXTENSIONS)


def _proxy_response_headers(*, is_image: bool) -> dict[str, str]:
    return {
        "Cache-Control": CACHE_CONTROL if is_image else METADATA_CACHE_CONTROL,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET",
        "Access-Control-Allow-Headers": "*",
    }


@router.get("/7tv/{path:path}")
async def proxy_7tv(path: str):
    """
    Proxy requests to 7TV API/CDN.

    Path format: cdn.7tv.app/emotes/... or api.7tv.app/v3/...
    """
    try:
        normalized_path = path.lstrip("/")
        if not normalized_path or "/" not in normalized_path:
            raise HTTPException(status_code=400, detail="Invalid proxy path format")

        host, resource_path = normalized_path.split("/", 1)
        if host not in ALLOWED_DOMAINS:
            raise HTTPException(status_code=403, detail="Domain not allowed")

        if not resource_path:
            raise HTTPException(status_code=400, detail="Invalid resource path")
        if len(resource_path) > 2048:
            raise HTTPException(status_code=400, detail="Resource path is too long")

        safe_resource_path = quote(resource_path, safe="/._-~")
        url = f"https://{host}/{safe_resource_path}"

        logger.debug("[PROXY] Proxying 7TV request: %s", url)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        expects_image = _is_image_proxy_path(resource_path)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=False)
            redirects_followed = 0
            while 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                if not location:
                    break
                redirect_url = urljoin(str(response.url), location)
                redirect_host = urlparse(redirect_url).hostname or ""
                if redirect_host not in ALLOWED_DOMAINS:
                    raise HTTPException(status_code=502, detail="Upstream redirect is not allowed")
                redirects_followed += 1
                if redirects_followed > 3:
                    raise HTTPException(status_code=502, detail="Too many upstream redirects")
                response = await client.get(redirect_url, headers=headers, follow_redirects=False)

        if response.status_code in {404, 410} and expects_image:
            logger.warning(
                "[PROXY] 7TV asset unavailable, returning transparent fallback path=%s status=%s",
                path,
                response.status_code,
            )
            return Response(
                content=TRANSPARENT_GIF,
                media_type="image/gif",
                headers=_proxy_response_headers(is_image=True),
            )

        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "image/webp")
        content_type_lower = content_type.lower()
        is_image = content_type_lower.startswith("image/")
        is_json = content_type_lower.startswith("application/json")
        if not (is_image or is_json):
            raise HTTPException(status_code=502, detail="Unexpected upstream content type")

        return Response(
            content=response.content,
            media_type=content_type,
            headers=_proxy_response_headers(is_image=is_image),
        )

    except httpx.TimeoutException:
        logger.error("[PROXY] Timeout proxying 7TV request: %s", path)
        raise HTTPException(status_code=504, detail="Request timeout")
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.warning("[PROXY] Upstream 7TV status=%s path=%s", status_code, path)
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Upstream resource was not found")
        raise HTTPException(status_code=502, detail="Proxy upstream request failed")
    except httpx.RequestError:
        logger.exception("[PROXY] Error proxying 7TV request: %s", path)
        raise HTTPException(status_code=502, detail="Proxy upstream request failed")
    except HTTPException:
        raise
    except Exception:
        logger.exception("[PROXY] Unexpected error proxying 7TV request: %s", path)
        raise HTTPException(status_code=500, detail="Internal proxy error")
