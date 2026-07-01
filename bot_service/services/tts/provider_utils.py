"""Helpers for provider-aware advanced TTS routing."""

from __future__ import annotations

import ipaddress
import os
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlparse, urlunparse

from core.config import settings

TTSProvider = Literal["f5", "gcloud"]
ProviderMode = Literal["cloud", "local"]
ProviderPublicMode = Literal["cloud", "self_host"]

_DEFAULT_PROVIDER: TTSProvider = "f5"
_DEFAULT_MODE: ProviderMode = "cloud"
_DEFAULT_PUBLIC_MODE: ProviderPublicMode = "cloud"

_DEFAULT_LOCAL_TTS_ALLOWED_HOSTS = (
    "localhost",
    "127.0.0.1",
    "::1",
    "host.docker.internal",
    "f5_tts",
    "tts_service",
)
_DEFAULT_LOCAL_TTS_ALLOWED_CIDRS = ("127.0.0.0/8", "::1/128")
_LOOPBACK_LOCAL_TTS_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DOCKER_SERVICE_URLS = {
    "gateway": ("tts_gateway", 8010),
    "f5": ("tts_service", 8011),
}


class ProviderRoutingError(ValueError):
    """Raised when provider routing is invalid for the current deployment contract."""


def _is_running_in_container() -> bool:
    return (
        os.path.exists("/.dockerenv")
        or str(os.getenv("PAIDVIEWER_IN_DOCKER", "")).strip().lower() in {"1", "true", "yes", "on"}
    )


def _runtime_service_url(raw_url: str, service: str) -> str:
    """Return a Docker-reachable URL when an in-container process received a host loopback URL."""

    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return ""

    if not _is_running_in_container():
        return url

    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower().strip(".")
    if host not in _LOOPBACK_LOCAL_TTS_HOSTS:
        return url

    replacement = _DOCKER_SERVICE_URLS.get(service)
    if not replacement:
        return url

    replacement_host, replacement_port = replacement
    host_for_url = f"[{replacement_host}]" if ":" in replacement_host else replacement_host
    netloc = f"{host_for_url}:{replacement_port}"
    return urlunparse((parsed.scheme or "http", netloc, "", "", "", ""))


def normalize_provider(provider: Optional[str]) -> TTSProvider:
    normalized = (provider or "").strip().lower()
    if normalized in {"f5", "google-f5"}:
        return "f5"
    if normalized in {"gcloud", "google_cloud", "google-cloud", "google"}:
        return "gcloud"
    return _DEFAULT_PROVIDER


def normalize_provider_mode(mode: Optional[str]) -> ProviderMode:
    normalized = (mode or "").strip().lower()
    if normalized in {"local", "self_host", "self-host"}:
        return "local"
    return _DEFAULT_MODE


def to_public_provider_mode(mode: Optional[str]) -> ProviderPublicMode:
    return "self_host" if normalize_provider_mode(mode) == "local" else _DEFAULT_PUBLIC_MODE


def get_official_mode_path(provider: Optional[str], public_mode: Optional[str]) -> Optional[str]:
    normalized_provider = normalize_provider(provider)
    normalized_public_mode = to_public_provider_mode(public_mode)

    if normalized_provider == "gcloud":
        return "internal" if normalized_public_mode == "cloud" else None

    if normalized_public_mode == "cloud":
        return "tts-gateway"
    return "tts_worker_agent"


def resolve_cloud_slot_policy(
    provider: Optional[str],
    *,
    is_whitelisted: bool = False,
) -> Dict[str, Any]:
    normalized_provider = normalize_provider(provider)
    policy = str(getattr(settings, "tts_cloud_slot_mode", "open") or "open").strip().lower()
    if policy not in {"open", "whitelist"}:
        policy = "open"

    if normalized_provider == "gcloud":
        return {
            "provider": normalized_provider,
            "policy": "internal",
            "slot_allowed": True,
            "degraded_reason": None,
            "error_code": None,
        }

    if policy == "whitelist" and not is_whitelisted:
        return {
            "provider": normalized_provider,
            "policy": policy,
            "slot_allowed": False,
            "degraded_reason": "Cloud capacity is limited right now. A self-host slot is recommended for this channel.",
            "error_code": "cloud_slot_required",
        }

    return {
        "provider": normalized_provider,
        "policy": policy,
        "slot_allowed": True,
        "degraded_reason": None,
        "error_code": None,
    }


def build_tts_mode_contract(
    provider: Optional[str],
    mode: Optional[str],
    *,
    available: bool,
    is_whitelisted: bool = False,
    degraded_reason: Optional[str] = None,
    error_code: Optional[str] = None,
    recommended_path: Optional[str] = None,
    capabilities: Optional[Dict[str, Any]] = None,
    upstream: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_provider = normalize_provider(provider)
    normalized_mode = normalize_provider_mode(mode)
    public_mode = to_public_provider_mode(normalized_mode)
    resolved_capabilities = dict(capabilities or get_provider_capabilities(normalized_provider))
    slot_policy = (
        resolve_cloud_slot_policy(normalized_provider, is_whitelisted=is_whitelisted)
        if public_mode == "cloud"
        else {
            "provider": normalized_provider,
            "policy": "n/a",
            "slot_allowed": True,
            "degraded_reason": None,
            "error_code": None,
        }
    )

    slot_allowed = bool(slot_policy["slot_allowed"])
    final_error_code = error_code or slot_policy["error_code"]
    final_degraded_reason = degraded_reason or slot_policy["degraded_reason"]
    final_available = bool(available) and slot_allowed

    official_path = get_official_mode_path(normalized_provider, public_mode)
    final_recommended_path = recommended_path or (
        get_official_mode_path(normalized_provider, "self_host")
        if public_mode == "cloud" and not slot_allowed
        else official_path
    )

    resolved_status = status
    if not resolved_status:
        if final_available:
            resolved_status = "healthy"
        elif final_error_code or final_degraded_reason:
            resolved_status = "degraded"
        else:
            resolved_status = "unavailable"

    payload = {
        "provider": normalized_provider,
        "mode": normalized_mode,
        "official_mode": public_mode,
        "available": final_available,
        "healthy": final_available,
        "status": resolved_status,
        "degraded_reason": final_degraded_reason,
        "slot_allowed": slot_allowed,
        "recommended_path": final_recommended_path,
        "official_path": official_path,
        "error_code": final_error_code,
        "capabilities": resolved_capabilities,
        "voice_admin": bool(resolved_capabilities.get("voice_admin", False)),
    }
    if upstream is not None:
        payload["upstream"] = upstream
        payload["upstream_url"] = upstream.get("url")
        payload["via_gateway"] = upstream.get("via") == "gateway"
    else:
        payload["upstream_url"] = resolved_capabilities.get("synthesis_upstream_url")
        payload["via_gateway"] = resolved_capabilities.get("synthesis_via") == "gateway"
    payload["slot_policy"] = {
        "policy": slot_policy["policy"],
        "slot_allowed": slot_allowed,
    }
    return payload


def normalize_engine(engine: Optional[str], provider: Optional[str] = None) -> str:
    normalized_engine = (engine or "").strip().lower()
    if normalized_engine in {"gtts", "gcloud", "f5tts"}:
        return normalized_engine

    normalized_provider = normalize_provider(provider)
    if normalized_provider == "gcloud":
        return "gcloud"
    return "f5tts"


def infer_provider_from_engine(engine: Optional[str], advanced_provider: Optional[str] = None) -> TTSProvider:
    normalized_engine = normalize_engine(engine, provider=advanced_provider)
    if normalized_engine == "gcloud":
        return "gcloud"
    if normalized_engine == "f5tts":
        return "f5"
    return normalize_provider(advanced_provider)


def resolve_provider_mode_for_settings(
    *,
    engine: Optional[str],
    use_local_tts: bool,
    advanced_provider: Optional[str],
    f5_mode: Optional[str],
) -> tuple[TTSProvider, ProviderMode]:
    provider = infer_provider_from_engine(engine, advanced_provider=advanced_provider)
    if provider == "gcloud":
        return provider, "cloud"

    if f5_mode is not None:
        return provider, normalize_provider_mode(f5_mode)

    if use_local_tts:
        return provider, "local"
    return provider, _DEFAULT_MODE


def get_tts_gateway_url() -> str:
    """Return normalized gateway URL when configured."""

    return _runtime_service_url(settings.tts_gateway_url or "", "gateway")


def get_provider_service_url(provider: Optional[str]) -> str:
    """Direct provider URL (not gateway) for synthesis fallback/local compatibility."""

    normalized_provider = normalize_provider(provider)
    if normalized_provider == "gcloud":
        raise ProviderRoutingError("gcloud_synthesis_is_internal")

    f5_url = _runtime_service_url(settings.f5_tts_service_url or "", "f5")
    if f5_url:
        return f5_url
    return _runtime_service_url("http://localhost:8011", "f5")


def should_route_provider_via_gateway(provider: Optional[str]) -> bool:
    """True when advanced synthesis traffic should go through gateway."""

    normalized_provider = normalize_provider(provider)
    return normalized_provider == "f5" and bool(get_tts_gateway_url())


def get_synthesis_upstream_url(provider: Optional[str]) -> str:
    """Resolve synthesis upstream URL according to gateway-first contract."""

    normalized_provider = normalize_provider(provider)
    if normalized_provider == "gcloud":
        raise ProviderRoutingError("gcloud_synthesis_is_internal")

    gateway_url = get_tts_gateway_url()
    if gateway_url:
        return gateway_url

    return get_provider_service_url(normalized_provider)


def get_synthesis_upstream_params(
    provider: Optional[str],
    extra_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build synthesis query params. Gateway mode requires explicit provider."""

    normalized_provider = normalize_provider(provider)
    params: Dict[str, Any] = dict(extra_params or {})
    if should_route_provider_via_gateway(normalized_provider):
        params.setdefault("provider", normalized_provider)
    return params


def get_voice_management_upstream_url(provider: Optional[str]) -> str:
    """Resolve voice/admin upstream URL (provider-owned, no gateway routing)."""

    normalized_provider = normalize_provider(provider)
    if normalized_provider == "gcloud":
        raise ProviderRoutingError("gcloud_voice_management_not_supported")

    return get_provider_service_url("f5")


def get_voice_management_upstream_params(
    provider: Optional[str],
    extra_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Voice/admin requests are provider direct and do not require provider query param."""

    _ = provider
    return dict(extra_params or {})


def get_provider_capabilities(provider: Optional[str]) -> Dict[str, Any]:
    normalized_provider = normalize_provider(provider)
    gateway_configured = bool(get_tts_gateway_url())

    if normalized_provider == "gcloud":
        return {
            "provider": "gcloud",
            "synthesis_supported": True,
            "synthesis_available": True,
            "synthesis_requires_gateway": False,
            "synthesis_via": "internal",
            "voice_crud": False,
            "voice_admin": False,
            "voice_reason": "gcloud_managed_voices_only",
            "supports_streaming": False,
            "supports_voice_clone": False,
            "supports_voice_design": False,
            "supports_models": False,
            "supports_global_voices": False,
            "supports_user_voices": False,
            "official_modes": ["cloud"],
            "official_cloud_path": "internal",
            "official_self_host_path": None,
            "legacy_raw_endpoint_supported": False,
            "mode_contract": {
                "cloud": {"supported": True, "path": "internal", "legacy_alias": "cloud"},
                "self_host": {"supported": False, "path": None, "legacy_alias": "local"},
            },
        }

    synthesis_upstream_url = ""
    voice_upstream_url = ""
    try:
        synthesis_upstream_url = get_synthesis_upstream_url("f5")
    except ProviderRoutingError:
        synthesis_upstream_url = ""
    try:
        voice_upstream_url = get_voice_management_upstream_url("f5")
    except ProviderRoutingError:
        voice_upstream_url = ""

    return {
        "provider": "f5",
        "synthesis_supported": True,
        "synthesis_available": True,
        "synthesis_requires_gateway": False,
        "synthesis_via": "gateway" if gateway_configured else "direct",
        "synthesis_upstream_url": synthesis_upstream_url,
        "voice_crud": True,
        "voice_admin": True,
        "voice_upstream_configured": True,
        "voice_upstream_url": voice_upstream_url,
        "supports_streaming": False,
        "supports_voice_clone": True,
        "supports_voice_design": False,
        "supports_models": False,
        "supports_global_voices": True,
        "supports_user_voices": True,
        "official_modes": ["cloud", "self_host"],
        "official_cloud_path": "tts-gateway",
        "official_self_host_path": "tts_worker_agent",
        "legacy_raw_endpoint_supported": True,
        "mode_contract": {
            "cloud": {"supported": True, "path": "tts-gateway", "legacy_alias": "cloud"},
            "self_host": {"supported": True, "path": "tts_worker_agent", "legacy_alias": "local"},
        },
    }


def get_all_provider_capabilities() -> Dict[str, Dict[str, Any]]:
    return {
        "f5": get_provider_capabilities("f5"),
        "gcloud": get_provider_capabilities("gcloud"),
    }


def get_provider_upstream_url(provider: Optional[str]) -> str:
    """Backward-compatible alias for synthesis upstream resolver."""

    return get_synthesis_upstream_url(provider)


def get_provider_upstream_params(
    provider: Optional[str],
    extra_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Backward-compatible alias for synthesis upstream params."""

    return get_synthesis_upstream_params(provider, extra_params=extra_params)


def get_local_tts_allowed_hosts() -> set[str]:
    raw = getattr(settings, "local_tts_allowed_hosts", "") or ""
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        values = list(_DEFAULT_LOCAL_TTS_ALLOWED_HOSTS)
    return set(values)


def get_local_tts_allowed_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    raw = getattr(settings, "local_tts_allowed_cidrs", "") or ""
    cidr_values = [item.strip() for item in raw.split(",") if item.strip()]
    if not cidr_values:
        cidr_values = list(_DEFAULT_LOCAL_TTS_ALLOWED_CIDRS)

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in cidr_values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def is_local_tts_host_allowed(hostname: str) -> bool:
    candidate = (hostname or "").strip().lower().strip(".")
    if not candidate:
        return False

    if candidate in get_local_tts_allowed_hosts():
        return True

    try:
        host_ip = ipaddress.ip_address(candidate)
    except ValueError:
        return False

    for network in get_local_tts_allowed_networks():
        if host_ip in network:
            return True
    return False


def normalize_local_tts_endpoint_url(endpoint_url: str) -> str:
    raw_url = (endpoint_url or "").strip()
    if not raw_url:
        raise ValueError("endpoint_url is required")

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint_url must start with http:// or https://")

    if parsed.username or parsed.password:
        raise ValueError("endpoint_url must not contain credentials")

    if not parsed.hostname:
        raise ValueError("endpoint_url host is required")

    if parsed.path not in {"", "/"}:
        raise ValueError("endpoint_url must not contain path")

    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("endpoint_url must not contain query, params, or fragment")

    host = parsed.hostname.strip().lower().strip(".")
    if not is_local_tts_host_allowed(host):
        raise ValueError("endpoint_url host is not allowed by LOCAL_TTS_ALLOWED_HOSTS/CIDRS")

    port = parsed.port
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("endpoint_url port is invalid")

    host_for_url = f"[{host}]" if ":" in host and not host.startswith("[") else host
    netloc = f"{host_for_url}:{port}" if port else host_for_url
    return f"{parsed.scheme}://{netloc}"


def get_local_tts_probe_endpoints(endpoint_url: str, provider: Optional[str] = None) -> list[str]:
    """Return safe server-side probe URLs for a user-facing local endpoint."""

    endpoint = normalize_local_tts_endpoint_url(endpoint_url)
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").strip().lower().strip(".")
    if host not in _LOOPBACK_LOCAL_TTS_HOSTS:
        return [endpoint]

    _ = normalize_provider(provider)
    candidates = [endpoint]

    for replacement_host in ("host.docker.internal", "tts_service"):
        if not is_local_tts_host_allowed(replacement_host):
            continue
        host_for_url = f"[{replacement_host}]" if ":" in replacement_host else replacement_host
        netloc = f"{host_for_url}:{parsed.port}" if parsed.port else host_for_url
        candidate = urlunparse((parsed.scheme, netloc, "", "", "", ""))
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates
