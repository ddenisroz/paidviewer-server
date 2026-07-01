"""
Reverse-proxy for memealerts.com.

Opens memealerts.com through our own origin so the popup can pass
access token data back to dashboard via postMessage.
"""

from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from auth.auth import get_current_user_optional
from core.database import get_db
from core.token_encryption import decrypt_token
from repositories.user_token_repository import UserTokenRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memealerts/proxy", tags=["memealerts-proxy"])

MEMEALERTS_ORIGIN = "https://memealerts.com"
MEMEALERTS_WWW_ORIGIN = "https://www.memealerts.com"
MEMEALERTS_SAFE_AUTH_RETURN_URL = f"{MEMEALERTS_ORIGIN}/auth/redirect"
PROXY_PREFIX = "/api/memealerts/proxy"
_ALLOWED_EXTERNAL_AUTH_REDIRECT_HOSTS = {
    "accounts.google.com",
    "id.twitch.tv",
    "oauth.vk.com",
    "id.vk.com",
    "login.vk.com",
}

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "content-encoding",
        "content-length",
        "host",
    }
)

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_PROXY_REQUEST_BODY_BYTES = 2 * 1024 * 1024

_INJECTED_SCRIPT = """
<script data-ma-proxy="1">
(function () {
  var handled = false;
  var inFlight = false;
  var lastAttemptKey = "";

  function normalizePossibleStreamerId(value) {
    if (value === null || value === undefined) return "";
    var text = String(value).trim();
    if (!text) return "";
    if (/^[a-f0-9]{24}$/i.test(text)) return text;
    if (/^\\d{1,32}$/.test(text)) return text;
    return "";
  }

  function isAuthStorageKey(key) {
    if (typeof key !== "string") return false;
    return /(token|auth|jwt|session|login)/i.test(key);
  }

  function isProfileStorageKey(key) {
    if (typeof key !== "string") return false;
    return /(user|profile|account|streamer|channel|viewer|me)/i.test(key);
  }

  function extractStreamerIdFromObject(value, depth) {
    if (!value || depth > 4) return "";

    if (Array.isArray(value)) {
      for (var idx = 0; idx < value.length && idx < 6; idx += 1) {
        var nestedArrayId = extractStreamerIdFromObject(value[idx], depth + 1);
        if (nestedArrayId) return nestedArrayId;
      }
      return "";
    }

    if (typeof value !== "object") return "";

    var directKeys = [
      "streamer_id",
      "streamerId",
      "tid",
      "user_id",
      "userId",
      "channel_id",
      "channelId",
      "broadcaster_id",
      "broadcasterId",
    ];
    for (var i = 0; i < directKeys.length; i += 1) {
      var directValue = normalizePossibleStreamerId(value[directKeys[i]]);
      if (directValue) return directValue;
    }

    var looksLikeProfile =
      !!value.username ||
      !!value.nickname ||
      !!value.displayName ||
      !!value.name ||
      !!value.email ||
      !!value.avatar ||
      !!value.channel;
    if (looksLikeProfile) {
      var profileId = normalizePossibleStreamerId(value.id);
      if (profileId) return profileId;
    }

    var nestedKeys = [
      "user",
      "profile",
      "account",
      "streamer",
      "channel",
      "viewer",
      "me",
      "auth",
      "data",
      "result",
    ];
    for (var j = 0; j < nestedKeys.length; j += 1) {
      var nestedValue = extractStreamerIdFromObject(value[nestedKeys[j]], depth + 1);
      if (nestedValue) return nestedValue;
    }

    return "";
  }

  function notifyClient(type, payload) {
    try {
      var data = payload || {};
      data.type = type;
    } catch (e) {}

    try {
      if (window.opener) {
        window.opener.postMessage(data, window.location.origin);
      }
    } catch (e) {}

    try {
      if ("BroadcastChannel" in window) {
        var channel = new BroadcastChannel("memealerts-auth");
        channel.postMessage(data);
        channel.close();
      }
    } catch (e) {}

    try {
      if (type === "memealerts_auth_state" || type === "memealerts_proxy_result") {
        var debugPayload = {
          type: type,
          state: data.state || undefined,
          source: data.source || undefined,
          status: data.status || undefined,
          ok: typeof data.ok === "boolean" ? data.ok : undefined,
          scanned_keys: data.scanned_keys || undefined,
          upstream_path: data.upstream_path || undefined,
          elapsed_ms: data.elapsed_ms || undefined,
          href_path: window.location.pathname,
        };
        var body = JSON.stringify(debugPayload);
        if (navigator.sendBeacon) {
          navigator.sendBeacon("/api/memealerts/proxy/debug", new Blob([body], { type: "application/json" }));
        } else {
          fetch("/api/memealerts/proxy/debug", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: body,
            keepalive: true,
          }).catch(function () {});
        }
      }
    } catch (e) {}
  }

  function pickToken(params) {
    var access =
      params.get("access_token") ||
      params.get("accessToken") ||
      params.get("token") ||
      params.get("auth_token") ||
      params.get("jwt") ||
      "";
    var streamerId =
      params.get("streamer_id") ||
      params.get("streamerId") ||
      params.get("tid") ||
      params.get("user_id") ||
      params.get("userId") ||
      params.get("channel_id") ||
      params.get("channelId") ||
      "";
    if (!access) return {};
    return {
      access_token: access,
      refresh_token: params.get("refresh_token") || params.get("refreshToken") || undefined,
      streamer_id: normalizePossibleStreamerId(streamerId) || undefined,
    };
  }

  function readUrlToken() {
    try {
      var url = new URL(window.location.href);
      var fromQuery = pickToken(url.searchParams);
      if (fromQuery.access_token) return fromQuery;

      var hash = (window.location.hash || "").replace(/^#/, "");
      if (!hash) return {};

      var hashParams = pickToken(new URLSearchParams(hash));
      if (hashParams.access_token) return hashParams;

      var queryIndex = hash.indexOf("?");
      if (queryIndex >= 0) {
        var hashQuery = hash.slice(queryIndex + 1);
        var fromHashQuery = pickToken(new URLSearchParams(hashQuery));
        if (fromHashQuery.access_token) return fromHashQuery;
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  function looksLikeToken(value) {
    if (typeof value !== "string") return false;
    var token = value.trim();
    if (!token) return false;
    if (token.split(".").length === 3) return true;
    return token.length >= 24;
  }

  function extractFromUnknown(rawValue, keyName) {
    if (typeof rawValue !== "string" || !rawValue) return {};

    var direct = rawValue.trim();
    var authKey = isAuthStorageKey(keyName || "");
    var profileKey = isProfileStorageKey(keyName || "");

    if (authKey && looksLikeToken(direct)) {
      return { access_token: direct };
    }

    try {
      var parsed = JSON.parse(direct);
      if (parsed && typeof parsed === "object") {
        var access =
          parsed.access_token ||
          parsed.accessToken ||
          parsed.auth_token ||
          parsed.authToken ||
          parsed.token ||
          parsed.jwt ||
          parsed.access ||
          parsed.bearer ||
          parsed.sessionToken ||
          "";
        if (looksLikeToken(access)) {
          return {
            access_token: access,
            refresh_token: parsed.refresh_token || parsed.refreshToken || undefined,
            streamer_id: extractStreamerIdFromObject(parsed, 0) || undefined,
          };
        }

        if (profileKey) {
          var profileStreamerId = extractStreamerIdFromObject(parsed, 0);
          if (profileStreamerId) {
            return { streamer_id: profileStreamerId };
          }
        }
      }
    } catch (e) {}

    try {
      var params = new URLSearchParams(direct.replace(/^[#?]/, ""));
      var fromParams = pickToken(params);
      if (fromParams.access_token) return fromParams;
    } catch (e) {}

    return {};
  }

  function readStorageToken() {
    try {
      var stores = [];
      try { stores.push({ name: "localStorage", store: localStorage }); } catch (e) {}
      try { stores.push({ name: "sessionStorage", store: sessionStorage }); } catch (e) {}
      var fallbackStreamerId = "";
      var scannedKeys = 0;
      for (var storeIdx = 0; storeIdx < stores.length; storeIdx += 1) {
        var profileStore = stores[storeIdx].store;
        for (var scanIdx = 0; scanIdx < profileStore.length; scanIdx += 1) {
          var scanKey = profileStore.key(scanIdx);
          if (!scanKey || !isProfileStorageKey(scanKey)) continue;
          scannedKeys += 1;
          var scanValue = profileStore.getItem(scanKey);
          var scanned = extractFromUnknown(scanValue || "", scanKey);
          if (scanned.streamer_id) {
            fallbackStreamerId = scanned.streamer_id;
            break;
          }
        }
        if (fallbackStreamerId) break;
      }

      var knownKeys = [
        "accessToken",
        "access_token",
        "token",
        "authToken",
        "jwt",
        "jwtToken",
        "id_token",
        "ma.auth.token",
        "memealerts.token",
        "memealerts.access_token",
        "memealerts.auth",
        "ma_token",
        "ma_access_token",
        "memealerts_access_token",
        "memealertsAccessToken",
        "auth.token",
        "auth.accessToken",
        "auth.access_token",
        "sessionToken",
        "session.token",
      ];
      for (var storeKnownIdx = 0; storeKnownIdx < stores.length; storeKnownIdx += 1) {
        var knownStore = stores[storeKnownIdx].store;
        for (var i = 0; i < knownKeys.length; i += 1) {
          var directValue = knownStore.getItem(knownKeys[i]);
          var extractedDirect = extractFromUnknown(directValue || "", knownKeys[i]);
          if (extractedDirect.access_token) {
            notifyClient("memealerts_auth_state", {
              state: "token_found",
              source: stores[storeKnownIdx].name + ":" + knownKeys[i],
            });
            return {
              access_token: extractedDirect.access_token,
              refresh_token:
                extractedDirect.refresh_token ||
                knownStore.getItem("refreshToken") ||
                knownStore.getItem("refresh_token") ||
                undefined,
              streamer_id: extractedDirect.streamer_id || fallbackStreamerId || undefined,
            };
          }
        }
      }

      var profileStreamerId = fallbackStreamerId;
      for (var storeFullIdx = 0; storeFullIdx < stores.length; storeFullIdx += 1) {
        var fullStore = stores[storeFullIdx].store;
        for (var idx = 0; idx < fullStore.length; idx += 1) {
          var key = fullStore.key(idx);
          if (!key) continue;
          if (!isAuthStorageKey(key) && !isProfileStorageKey(key)) continue;
          scannedKeys += 1;
          var value = fullStore.getItem(key);
          var extracted = extractFromUnknown(value || "", key);
          if (extracted.access_token) {
            notifyClient("memealerts_auth_state", {
              state: "token_found",
              source: stores[storeFullIdx].name + ":" + key,
            });
            return {
              access_token: extracted.access_token,
              refresh_token:
                extracted.refresh_token ||
                fullStore.getItem("refreshToken") ||
                fullStore.getItem("refresh_token") ||
                undefined,
              streamer_id: extracted.streamer_id || profileStreamerId || undefined,
            };
          }
          if (!profileStreamerId && extracted.streamer_id) {
            profileStreamerId = extracted.streamer_id;
          }
        }
      }
      if (tries === 1 || tries % 20 === 0) {
        notifyClient("memealerts_auth_state", {
          state: "storage_scanned",
          scanned_keys: scannedKeys,
        });
      }
      return {};
    } catch (e) {
      return {};
    }
  }

  function cleanupStorage() {
    try {
      var keys = [
        "accessToken",
        "access_token",
        "refreshToken",
        "refresh_token",
        "token",
        "authToken",
        "jwt",
        "jwtToken",
      ];
      for (var i = 0; i < keys.length; i += 1) {
        localStorage.removeItem(keys[i]);
      }
    } catch (e) {}
  }

  function readCookie(name) {
    try {
      var parts = document.cookie ? document.cookie.split("; ") : [];
      for (var i = 0; i < parts.length; i += 1) {
        var item = parts[i];
        var separator = item.indexOf("=");
        var key = separator >= 0 ? item.slice(0, separator) : item;
        if (decodeURIComponent(key) === name) {
          return decodeURIComponent(separator >= 0 ? item.slice(separator + 1) : "");
        }
      }
    } catch (e) {}
    return "";
  }

  function readCookieToken() {
    try {
      var rawCookie = document.cookie || "";
      if (!rawCookie) return {};
      var parts = rawCookie.split("; ");
      var names = [
        "accessToken",
        "access_token",
        "token",
        "authToken",
        "auth_token",
        "jwt",
        "jwtToken",
        "memealerts.token",
        "memealerts_access_token",
        "ma_access_token",
        "sessionToken",
      ];
      for (var i = 0; i < parts.length; i += 1) {
        var item = parts[i];
        var separator = item.indexOf("=");
        var rawKey = separator >= 0 ? item.slice(0, separator) : item;
        var key = decodeURIComponent(rawKey || "");
        if (!key) continue;
        if (names.indexOf(key) < 0 && !isAuthStorageKey(key)) continue;
        var rawValue = separator >= 0 ? item.slice(separator + 1) : "";
        var value = decodeURIComponent(rawValue || "");
        var extracted = extractFromUnknown(value, key);
        if (extracted.access_token) {
          notifyClient("memealerts_auth_state", {
            state: "token_found",
            source: "cookie:" + key,
          });
          return extracted;
        }
      }
    } catch (e) {}
    return {};
  }

  async function persistToken(payload) {
    try {
      var headers = { "Content-Type": "application/json" };
      var csrfToken = readCookie("csrf_token");
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
      var response = await fetch("/api/memealerts/connect", {
        method: "POST",
        credentials: "include",
        headers: headers,
        body: JSON.stringify({
          access_token: payload.access_token,
          refresh_token: payload.refresh_token,
          streamer_id: payload.streamer_id,
        }),
      });
      var data = null;
      try {
        data = await response.json();
      } catch (e) {}
      var ok = response.ok;
      if (data && typeof data.success === "boolean") {
        ok = ok && data.success;
      }
      return {
        ok: ok,
        status: response.status,
        detail: (data && (data.detail || data.error)) || "",
      };
    } catch (e) {
      return { ok: false, status: 0, detail: "" };
    }
  }

  async function processToken(payload, source) {
    if (handled || inFlight || !payload || !payload.access_token) return;
    var attemptKey = String(payload.access_token) + "|" + String(payload.streamer_id || "");
    if (attemptKey === lastAttemptKey) return;

    inFlight = true;
    lastAttemptKey = attemptKey;

    var persistResult = await persistToken(payload);
    notifyClient("memealerts_auth_state", {
      state: "connect_posted",
      ok: !!persistResult.ok,
      status: persistResult.status || 0,
      source: source || "unknown",
    });
    notifyClient("memealerts_proxy_result", {
      ok: !!persistResult.ok,
      status: persistResult.status || 0,
      detail: persistResult.detail || "",
      source: source || "unknown",
      streamer_id: payload.streamer_id || undefined,
    });

    if (persistResult.ok) {
      handled = true;
      cleanupStorage();
      setTimeout(function () {
        window.close();
      }, 350);
    }

    inFlight = false;
  }

  var tries = 0;
  var maxTries = 240;

  var initialToken = readUrlToken();
  if (initialToken.access_token) {
    processToken(initialToken, "url");
    return;
  }

  notifyClient("memealerts_auth_state", {
    state: "storage_scanned",
    source: "inject",
    scanned_keys: 0,
  });

  var interval = setInterval(function () {
    tries += 1;

    var fromUrl = readUrlToken();
    if (fromUrl.access_token) {
      clearInterval(interval);
      processToken(fromUrl, "url");
      return;
    }

    var fromCookie = readCookieToken();
    if (fromCookie.access_token) {
      clearInterval(interval);
      processToken(fromCookie, "cookie");
      return;
    }

    var fromStorage = readStorageToken();
    if (fromStorage.access_token) {
      clearInterval(interval);
      processToken(fromStorage, "storage");
      return;
    }

    if (tries >= maxTries) {
      clearInterval(interval);
    }
  }, 500);
})();
</script>
"""

_PATH_FIX_SCRIPT = """
<script data-ma-route-fix="1">
(function () {
  try {
    if (window.location.pathname.indexOf('/api/memealerts/proxy') === 0) {
      var next = '/' + (window.location.search || '') + (window.location.hash || '');
      history.replaceState({}, '', next);
    }
  } catch (e) {}
})();
</script>
"""


def _is_auth_proxy_path(path: str) -> bool:
    normalized = (path or "").lstrip("/")
    return normalized == "auth" or normalized == "api/auth" or normalized.startswith("auth/") or normalized.startswith(
        "api/auth/"
    )


def _rewrite_set_cookie(value: str, request: Request) -> str:
    # Convert upstream cookies to current host scope so browser keeps them
    # for subsequent proxy requests (anti-bot/session cookies).
    rewritten = re.sub(r";\s*Domain=[^;]+", "", value, flags=re.IGNORECASE)
    if request.url.scheme != "https":
        rewritten = re.sub(r";\s*Secure", "", rewritten, flags=re.IGNORECASE)
        rewritten = re.sub(r";\s*SameSite=None", "; SameSite=Lax", rewritten, flags=re.IGNORECASE)
    return rewritten


def _get_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_same_local_host(origin: str, request: Request) -> bool:
    origin_host = (urlparse(origin).hostname or "").lower()
    request_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    ).split(":", 1)[0].lower()
    return origin_host == request_host or origin_host in {"localhost", "127.0.0.1", "::1"}


def _resolve_proxy_public_base(request: Request) -> str:
    for header_name in ("referer", "origin"):
        origin = _get_origin(request.headers.get(header_name))
        if origin and _is_same_local_host(origin, request):
            return origin.rstrip("/")

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    if host and proto in {"http", "https"} and not any(ch in host for ch in "\r\n\t"):
        return f"{proto}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _normalize_query(path: str, query: list[tuple[str, str]] | None) -> list[tuple[str, str]] | None:
    return query


def _normalize_auth_query(
    path: str,
    query: list[tuple[str, str]] | None,
    *,
    proxy_return_url: str,
) -> list[tuple[str, str]] | None:
    if not query:
        query = []

    if not (path.startswith("auth/") or path.startswith("api/auth/")):
        return query

    normalized: list[tuple[str, str]] = []
    has_return_url = False
    proxy_origin = f"{urlparse(proxy_return_url).scheme}://{urlparse(proxy_return_url).netloc}"

    def _normalize_safe_return_url(raw_value: str) -> str | None:
        if not raw_value:
            return None

        parsed = urlparse(raw_value)
        scheme = (parsed.scheme or "").lower()

        # Relative path: keep on our origin only.
        if not scheme and not parsed.netloc:
            if raw_value.startswith("/") and not raw_value.startswith("//"):
                return f"{proxy_origin}{raw_value}"
            return None

        # Absolute URL: allow only same-origin callback.
        if scheme in {"http", "https"}:
            candidate_origin = f"{parsed.scheme}://{parsed.netloc}"
            if candidate_origin == proxy_origin:
                return raw_value

        return None

    for key, value in query:
        if key == "return_url":
            has_return_url = True
            safe_value = _normalize_safe_return_url(value)
            if safe_value:
                normalized.append((key, safe_value))
            else:
                logger.warning("[PROXY] Rejected unsafe return_url, forcing proxy callback")
                normalized.append((key, proxy_return_url))
        else:
            normalized.append((key, value))

    if not has_return_url:
        normalized.append(("return_url", proxy_return_url))

    return normalized


def _build_upstream_auth_fallback_query(
    path: str,
    query: list[tuple[str, str]] | None,
) -> list[tuple[str, str]] | None:
    if not query or not (path.startswith("auth/") or path.startswith("api/auth/")):
        return query

    normalized: list[tuple[str, str]] = []
    has_return_url = False
    for key, value in query:
        if key == "return_url":
            has_return_url = True
            normalized.append((key, MEMEALERTS_SAFE_AUTH_RETURN_URL))
        else:
            normalized.append((key, value))

    if not has_return_url:
        normalized.append(("return_url", MEMEALERTS_SAFE_AUTH_RETURN_URL))

    return normalized


def _extract_proxy_auth_callback_params(request: Request) -> dict[str, str]:
    """Extract callback values without logging token contents."""
    params = request.query_params
    access_token = (
        params.get("accessToken")
        or params.get("access_token")
        or params.get("token")
        or params.get("auth_token")
        or params.get("jwt")
        or ""
    ).strip()
    refresh_token = (params.get("refreshToken") or params.get("refresh_token") or "").strip()
    streamer_id = (
        params.get("streamerId")
        or params.get("streamer_id")
        or params.get("tid")
        or params.get("user_id")
        or params.get("userId")
        or ""
    ).strip()
    provider = (params.get("provider") or "").strip().lower()
    if provider not in {"twitch", "google", "vk"}:
        provider = "twitch"

    result = {"provider": provider}
    if access_token:
        result["accessToken"] = access_token
    if refresh_token:
        result["refreshToken"] = refresh_token
    if streamer_id:
        result["streamerId"] = streamer_id
    return result


def _is_proxy_auth_callback(path: str, request: Request) -> bool:
    normalized_path = (path or "").lstrip("/")
    if normalized_path != "auth/redirect":
        return False
    return bool(_extract_proxy_auth_callback_params(request).get("accessToken"))


def _redirect_proxy_auth_callback(request: Request) -> RedirectResponse:
    callback_params = _extract_proxy_auth_callback_params(request)
    logger.info(
        "[PROXY] MemeAlerts auth callback captured provider=%s access=%s refresh=%s streamer_id=%s",
        callback_params.get("provider"),
        bool(callback_params.get("accessToken")),
        bool(callback_params.get("refreshToken")),
        bool(callback_params.get("streamerId")),
    )
    target = f"/memealerts/callback?{urlencode(callback_params)}"
    return RedirectResponse(url=target, status_code=303)


def _normalize_upstream_path(path: str) -> str:
    return (path or "").lstrip("/")


def _build_upstream_url(path: str) -> str:
    normalized_path = _normalize_upstream_path(path)
    if normalized_path:
        return f"{MEMEALERTS_ORIGIN}/{normalized_path}"
    return f"{MEMEALERTS_ORIGIN}/"


async def _read_proxy_body_limited(request: Request, max_bytes: int) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError("payload_too_large")
    return bytes(data)


def _rewrite_body(body: bytes, content_type: str, proxy_prefix: str, *, path: str = "") -> bytes:
    if not content_type:
        return body

    ct_lower = content_type.lower()
    is_html = "html" in ct_lower
    is_js = "javascript" in ct_lower
    is_css = "css" in ct_lower

    if not (is_html or is_js or is_css):
        return body

    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return body

    text = text.replace("https://memealerts.com/", f"{proxy_prefix}/")
    text = text.replace("https://memealerts.com", proxy_prefix)
    text = text.replace("https://www.memealerts.com/", f"{proxy_prefix}/")
    text = text.replace("https://www.memealerts.com", proxy_prefix)

    text = re.sub(
        r'((?:src|href|action)\s*=\s*["\'])/(?!/|api/memealerts/proxy/)',
        rf"\1{proxy_prefix}/",
        text,
    )

    text = re.sub(
        r"""(["'])/api/(?!memealerts/proxy/)""",
        rf"\1{proxy_prefix}/api/",
        text,
    )

    text = re.sub(
        r"""(["'])/assets/(?!memealerts/proxy/)""",
        rf"\1{proxy_prefix}/assets/",
        text,
    )

    text = re.sub(
        r"""(["'])/socket\.io/(?!memealerts/proxy/)""",
        rf"\1{proxy_prefix}/socket.io/",
        text,
    )

    text = re.sub(
        r"""(url\(\s*["']?)/(?!/|api/memealerts/proxy/)""",
        rf"\1{proxy_prefix}/",
        text,
    )

    # Guard against repeated prefixing during rewrite passes.
    # Seen in production as:
    # /api/memealerts/proxy/api/memealerts/proxy/...
    double_proxy_prefix = f"{proxy_prefix}/api/memealerts/proxy"
    while double_proxy_prefix in text:
        text = text.replace(double_proxy_prefix, proxy_prefix)

    repeated_prefix = f"{proxy_prefix}{proxy_prefix}"
    while repeated_prefix in text:
        text = text.replace(repeated_prefix, proxy_prefix)

    if is_html and not _is_auth_proxy_path(path):
        if 'data-ma-route-fix="1"' not in text:
            if "<head>" in text:
                text = text.replace("<head>", f"<head>{_PATH_FIX_SCRIPT}", 1)
            else:
                text = f"{_PATH_FIX_SCRIPT}{text}"

    if is_html and 'data-ma-proxy="1"' not in text:
        logger.info("[PROXY] MemeAlerts auth script injected path=%s", path or "/")
        if "</body>" in text:
            text = text.replace("</body>", f"{_INJECTED_SCRIPT}</body>")
        elif "</html>" in text:
            text = text.replace("</html>", f"{_INJECTED_SCRIPT}</html>")
        else:
            text += _INJECTED_SCRIPT

    return text.encode("utf-8")


def _filter_headers(headers: httpx.Headers, *, is_response: bool = False) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in _HOP_BY_HOP:
            continue
        if is_response and lowered.startswith("access-control-"):
            continue
        if is_response and lowered in (
            "strict-transport-security",
            "content-security-policy",
            "content-security-policy-report-only",
            "x-frame-options",
        ):
            continue
        out[key] = value
    return out


def _looks_like_access_token(value: str) -> bool:
    token = (value or "").strip()
    if not token or any(ch in token for ch in ("\r", "\n", "\t", " ")):
        return False
    # JWT-like or opaque long token.
    return token.count(".") == 2 or len(token) >= 24


def _resolve_proxy_access_token(raw_stored_token: str | None) -> str | None:
    raw_value = (raw_stored_token or "").strip()
    if not raw_value:
        return None

    try:
        decrypted = (decrypt_token(raw_value) or "").strip()
    except Exception:
        # Legacy/plain tokens may still exist in DB; use only if token-like.
        if _looks_like_access_token(raw_value):
            logger.warning("[PROXY] Using legacy plain MemeAlerts token from storage")
            return raw_value
        logger.warning("[PROXY] Failed to decrypt MemeAlerts token; skipping auth header")
        return None

    if _looks_like_access_token(decrypted):
        return decrypted
    if decrypted:
        logger.warning("[PROXY] Decrypted MemeAlerts token has invalid format; skipping auth header")
        return None
    if _looks_like_access_token(raw_value):
        logger.warning("[PROXY] Empty decrypted token; using legacy plain token")
        return raw_value
    return None


def _is_allowed_external_auth_redirect(parsed) -> bool:
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").strip().lower()
    if scheme != "https" or not host:
        return False
    return host in _ALLOWED_EXTERNAL_AUTH_REDIRECT_HOSTS or any(
        host.endswith(suffix) for suffix in (".google.com", ".twitch.tv", ".vk.com", ".vk.ru")
    )


def _patch_memealerts_oauth_state_value(state: str, proxy_return_url: str) -> str:
    raw_state = (state or "").strip()
    if raw_state.startswith("{"):
        try:
            payload = json.loads(raw_state)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            payload["return_url"] = proxy_return_url
            return json.dumps(payload, separators=(",", ":"))
    return proxy_return_url


def _patch_external_auth_state_location(location: str, proxy_return_url: str) -> str:
    """Point third-party OAuth state back to our proxy without asking MemeAlerts to accept localhost upfront."""
    if not location or any(ch in location for ch in ("\r", "\n", "\t")):
        return location

    parsed = urlparse(location)
    if not _is_allowed_external_auth_redirect(parsed):
        return location

    query = parse_qsl(parsed.query, keep_blank_values=True)
    if not query:
        return location

    patched: list[tuple[str, str]] = []
    changed = False
    for key, value in query:
        if key == "state":
            patched.append((key, _patch_memealerts_oauth_state_value(value, proxy_return_url)))
            changed = True
        else:
            patched.append((key, value))

    if not changed:
        return location

    patched_query = urlencode(patched, doseq=True)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            patched_query,
            parsed.fragment,
        )
    )


def _sanitize_redirect_location(
    location: str,
    proxy_prefix: str,
    *,
    request: Request | None = None,
    allow_external_auth_redirects: bool = False,
) -> str:
    """Normalize upstream redirect targets to safe proxy-local locations."""
    if not location:
        return proxy_prefix
    if any(ch in location for ch in ("\r", "\n", "\t")):
        return proxy_prefix
    location = location.strip()
    if not location:
        return proxy_prefix

    # Always keep redirects inside proxy for upstream MemeAlerts domains.
    if location.startswith(f"{MEMEALERTS_ORIGIN}/"):
        return location.replace(f"{MEMEALERTS_ORIGIN}/", f"{proxy_prefix}/")
    if location.startswith(MEMEALERTS_ORIGIN):
        return location.replace(MEMEALERTS_ORIGIN, proxy_prefix)
    if location.startswith(f"{MEMEALERTS_WWW_ORIGIN}/"):
        return location.replace(f"{MEMEALERTS_WWW_ORIGIN}/", f"{proxy_prefix}/")
    if location.startswith(MEMEALERTS_WWW_ORIGIN):
        return location.replace(MEMEALERTS_WWW_ORIGIN, proxy_prefix)
    if location.startswith("/"):
        if location.startswith("/memealerts/callback") or location.startswith(f"{proxy_prefix}/auth/redirect"):
            return location
        return f"{proxy_prefix}{location}"

    parsed = urlparse(location)
    scheme = (parsed.scheme or "").lower()

    # Block script/data redirects from upstream.
    if scheme in {"javascript", "data"}:
        return proxy_prefix

    # Keep relative paths inside proxy.
    if not scheme and not parsed.netloc:
        return f"{proxy_prefix}/{location.lstrip('./')}"

    request_host = (
        (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(":", 1)[0]
        .strip()
        .lower()
        if request is not None
        else ""
    )
    redirect_host = (parsed.hostname or "").strip().lower()
    if request_host and redirect_host in {request_host, "localhost", "127.0.0.1", "::1"}:
        if parsed.path.startswith("/memealerts/callback") or parsed.path.startswith(f"{proxy_prefix}/auth/redirect"):
            return location

    if allow_external_auth_redirects and scheme == "https":
        if redirect_host in _ALLOWED_EXTERNAL_AUTH_REDIRECT_HOSTS or any(
            redirect_host.endswith(suffix) for suffix in (".google.com", ".twitch.tv", ".vk.com", ".vk.ru")
        ):
            return location

    # Allow only absolute redirects to upstream MemeAlerts hosts.
    if scheme in {"http", "https"} and parsed.netloc.lower() in {"memealerts.com", "www.memealerts.com"}:
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{proxy_prefix}{path}{query}{fragment}"

    # Any other absolute external target is treated as unsafe for proxy redirects.
    return proxy_prefix


@router.post("/debug")
async def memealerts_proxy_debug(request: Request) -> dict:
    """Receive non-secret diagnostics from the same-origin MemeAlerts proxy popup."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    safe_payload = {
        "type": str(payload.get("type") or "")[:64],
        "state": str(payload.get("state") or "")[:64],
        "source": str(payload.get("source") or "")[:160],
        "status": payload.get("status") if isinstance(payload.get("status"), int) else None,
        "ok": payload.get("ok") if isinstance(payload.get("ok"), bool) else None,
        "scanned_keys": payload.get("scanned_keys") if isinstance(payload.get("scanned_keys"), int) else None,
        "upstream_path": str(payload.get("upstream_path") or "")[:240],
        "elapsed_ms": payload.get("elapsed_ms") if isinstance(payload.get("elapsed_ms"), int) else None,
        "href_path": str(payload.get("href_path") or "")[:240],
    }
    logger.info("[PROXY] MemeAlerts auth debug %s", safe_payload)
    return {"ok": True}


@router.get("/", response_class=HTMLResponse)
async def proxy_root(
    request: Request,
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    return await _proxy(request, "", user=user, db=db)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_path(
    request: Request,
    path: str,
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if _is_proxy_auth_callback(path, request):
        return _redirect_proxy_auth_callback(request)

    canonical_path = _normalize_upstream_path(path)
    if canonical_path != (path or "").lstrip("/"):
        query_string = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(
            url=f"{PROXY_PREFIX}/{canonical_path}{query_string}",
            status_code=307,
        )
    return await _proxy(request, path, user=user, db=db)


async def _proxy(request: Request, path: str, *, user: dict | None = None, db: Session | None = None) -> Response:
    upstream_url = _build_upstream_url(path)
    proxy_prefix = PROXY_PREFIX
    request_started = time.monotonic()

    fwd_headers = _filter_headers(request.headers)
    fwd_headers["host"] = "memealerts.com"
    fwd_headers["origin"] = MEMEALERTS_ORIGIN
    fwd_headers["referer"] = f"{MEMEALERTS_ORIGIN}/"
    fwd_headers["accept-encoding"] = "identity"

    # When user is logged in on our side, attach stored MemeAlerts OAuth token
    # to proxied API calls. This enables API usage through browser context
    # without requiring separate MemeAlerts website session cookies.
    if path.startswith("api/") and db is not None:
        has_auth_header = any(key.lower() == "authorization" for key in fwd_headers.keys())
        if not has_auth_header:
            user_id = (user or {}).get("id") if isinstance(user, dict) else None
            if user_id:
                try:
                    token_repo = UserTokenRepository(db)
                    token = token_repo.get_by_user_and_platform(user_id, "memealerts")
                    if token and token.access_token:
                        access_token = _resolve_proxy_access_token(token.access_token)
                        if access_token:
                            fwd_headers["authorization"] = f"Bearer {access_token}"
                except Exception:
                    logger.exception("[PROXY] Failed to resolve stored MemeAlerts token for user_id=%s", user_id)

    try:
        body = await _read_proxy_body_limited(request, _MAX_PROXY_REQUEST_BODY_BYTES)
    except ValueError:
        return Response(content="Payload Too Large", status_code=413)
    except ClientDisconnect:
        logger.info("[PROXY] Client disconnected before request body was read")
        return Response(content=b"", status_code=499)
    query = list(request.query_params.multi_items()) if request.query_params else None
    has_explicit_return_url = bool(request.query_params.get("return_url"))
    query = _normalize_query(path, query)
    proxy_return_url = f"{_resolve_proxy_public_base(request)}{PROXY_PREFIX}/auth/redirect"
    query = _normalize_auth_query(path, query, proxy_return_url=proxy_return_url)
    upstream_query = _build_upstream_auth_fallback_query(path, query)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False, verify=True) as client:
            upstream_resp = await client.request(
                method=request.method,
                url=upstream_url,
                headers=fwd_headers,
                content=body if body else None,
                params=upstream_query,
            )
            # MemeAlerts auth hangs when return_url points to localhost. Ask
            # upstream for its own return URL, then patch OAuth state below so
            # the final callback lands back on our proxy.
            if _is_auth_proxy_path(path) and upstream_resp.status_code >= 400:
                logger.warning(
                    "[PROXY] Auth flow returned status=%s with safe upstream return_url (explicit=%s)",
                    upstream_resp.status_code,
                    has_explicit_return_url,
                )
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - request_started) * 1000)
        logger.warning(
            "[PROXY] MemeAlerts upstream timeout path=%s upstream=%s elapsed_ms=%s",
            path,
            upstream_url,
            elapsed_ms,
        )
        if _is_auth_proxy_path(path):
            detail = "MemeAlerts auth proxy timeout"
            html = f"""
<!doctype html>
<html><head><meta charset=\"utf-8\"><title>MemeAlerts</title></head>
<body>
<script>
(function() {{
  var payload = {{
    type: 'memealerts_auth_state',
    state: 'proxy_timeout',
    detail: {detail!r},
    upstream_path: {path!r},
    elapsed_ms: {elapsed_ms}
  }};
  try {{ if (window.opener) window.opener.postMessage(payload, window.location.origin); }} catch (e) {{}}
  try {{
    if ('BroadcastChannel' in window) {{
      var channel = new BroadcastChannel('memealerts-auth');
      channel.postMessage(payload);
      channel.postMessage({{
        type: 'memealerts_proxy_result',
        ok: false,
        status: 504,
        source: 'proxy-timeout',
        detail: {detail!r}
      }});
      channel.close();
    }}
  }} catch (e) {{}}
}})();
</script>
<p>MemeAlerts auth proxy timeout. Please close this window and try again.</p>
</body></html>
"""
            return HTMLResponse(content=html, status_code=504)
        return Response(content="Gateway Timeout", status_code=504)
    except httpx.RequestError:
        logger.exception("[PROXY] MemeAlerts upstream error")
        return Response(content="Bad Gateway", status_code=502)

    if upstream_resp.is_redirect:
        location = upstream_resp.headers.get("location", "")
        if _is_auth_proxy_path(path):
            location = _patch_external_auth_state_location(location, proxy_return_url)
        location = _sanitize_redirect_location(
            location,
            proxy_prefix,
            request=request,
            allow_external_auth_redirects=_is_auth_proxy_path(path),
        )

        upstream_set_cookies = upstream_resp.headers.get_list("set-cookie")
        resp_headers = _filter_headers(upstream_resp.headers, is_response=True)
        resp_headers["location"] = location
        resp_headers["cache-control"] = "no-store, no-cache, must-revalidate"
        resp_headers["pragma"] = "no-cache"
        resp_headers.pop("set-cookie", None)
        response = Response(content=b"", status_code=upstream_resp.status_code, headers=resp_headers)
        for cookie in upstream_set_cookies:
            response.headers.append("set-cookie", _rewrite_set_cookie(cookie, request))
        return response

    content_type = upstream_resp.headers.get("content-type", "")
    resp_body = _rewrite_body(upstream_resp.content, content_type, proxy_prefix, path=path)

    upstream_set_cookies = upstream_resp.headers.get_list("set-cookie")
    resp_headers = _filter_headers(upstream_resp.headers, is_response=True)
    resp_headers["content-length"] = str(len(resp_body))
    if "html" in content_type.lower():
        resp_headers["cache-control"] = "no-store, no-cache, must-revalidate"
        resp_headers["pragma"] = "no-cache"
    resp_headers.pop("set-cookie", None)

    response = Response(
        content=resp_body,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=content_type.split(";")[0].strip() if content_type else None,
    )
    for cookie in upstream_set_cookies:
        response.headers.append("set-cookie", _rewrite_set_cookie(cookie, request))
    return response
