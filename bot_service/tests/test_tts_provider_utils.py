import pytest

from services.tts import provider_utils


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("f5", "f5"),
        ("google-f5", "f5"),
        ("gcloud", "gcloud"),
        ("google_cloud", "gcloud"),
        ("google-cloud", "gcloud"),
        ("google", "gcloud"),
        ("unknown", "f5"),
        ("", "f5"),
        (None, "f5"),
    ],
)
def test_normalize_provider(raw, expected):
    assert provider_utils.normalize_provider(raw) == expected


@pytest.mark.parametrize(
    ("engine", "advanced_provider", "expected"),
    [
        ("f5tts", None, "f5"),
        ("gcloud", None, "gcloud"),
        ("", "gcloud", "gcloud"),
        ("", "f5", "f5"),
        ("unknown", None, "f5"),
    ],
)
def test_infer_provider_from_engine(engine, advanced_provider, expected):
    assert provider_utils.infer_provider_from_engine(engine, advanced_provider=advanced_provider) == expected


@pytest.mark.parametrize(
    ("mode", "expected", "public_expected"),
    [
        ("local", "local", "self_host"),
        ("self_host", "local", "self_host"),
        ("self-host", "local", "self_host"),
        ("cloud", "cloud", "cloud"),
        ("", "cloud", "cloud"),
        ("unexpected", "cloud", "cloud"),
        (None, "cloud", "cloud"),
    ],
)
def test_normalize_provider_mode_and_public_mode(mode, expected, public_expected):
    assert provider_utils.normalize_provider_mode(mode) == expected
    assert provider_utils.to_public_provider_mode(mode) == public_expected


def test_get_official_mode_path_matches_provider_modes():
    assert provider_utils.get_official_mode_path("f5", "cloud") == "tts-gateway"
    assert provider_utils.get_official_mode_path("f5", "self_host") == "tts_worker_agent"
    assert provider_utils.get_official_mode_path("gcloud", "cloud") == "internal"
    assert provider_utils.get_official_mode_path("gcloud", "self_host") is None


def test_resolve_provider_mode_for_settings_prefers_explicit_f5_mode_over_use_local_flag():
    provider, mode = provider_utils.resolve_provider_mode_for_settings(
        engine="f5tts",
        use_local_tts=True,
        advanced_provider="f5",
        f5_mode="cloud",
    )
    assert provider == "f5"
    assert mode == "cloud"


def test_resolve_provider_mode_for_settings_uses_legacy_use_local_only_when_f5_mode_missing():
    provider, mode = provider_utils.resolve_provider_mode_for_settings(
        engine="f5tts",
        use_local_tts=True,
        advanced_provider="f5",
        f5_mode=None,
    )
    assert provider == "f5"
    assert mode == "local"


def test_resolve_provider_mode_for_settings_gcloud_is_always_cloud():
    provider, mode = provider_utils.resolve_provider_mode_for_settings(
        engine="gcloud",
        use_local_tts=True,
        advanced_provider="gcloud",
        f5_mode="local",
    )
    assert provider == "gcloud"
    assert mode == "cloud"


def test_resolve_cloud_slot_policy_honors_whitelist_mode(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_cloud_slot_mode", "whitelist")

    denied = provider_utils.resolve_cloud_slot_policy("f5", is_whitelisted=False)
    allowed = provider_utils.resolve_cloud_slot_policy("f5", is_whitelisted=True)
    internal = provider_utils.resolve_cloud_slot_policy("gcloud", is_whitelisted=False)

    assert denied["slot_allowed"] is False
    assert denied["error_code"] == "cloud_slot_required"
    assert allowed["slot_allowed"] is True
    assert internal["policy"] == "internal"
    assert internal["slot_allowed"] is True


def test_build_tts_mode_contract_prefers_self_host_when_cloud_slot_denied(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_cloud_slot_mode", "whitelist")

    payload = provider_utils.build_tts_mode_contract(
        "f5",
        "cloud",
        available=True,
        is_whitelisted=False,
    )

    assert payload["provider"] == "f5"
    assert payload["official_mode"] == "cloud"
    assert payload["slot_allowed"] is False
    assert payload["available"] is False
    assert payload["recommended_path"] == "tts_worker_agent"
    assert payload["error_code"] == "cloud_slot_required"


def test_get_provider_service_url_returns_f5_url(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011")
    assert provider_utils.get_provider_service_url("f5") == "http://f5:8011"


def test_get_provider_service_url_falls_back_to_localhost(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "")
    assert provider_utils.get_provider_service_url("f5") == "http://localhost:8011"


def test_get_provider_service_url_rejects_gcloud():
    with pytest.raises(provider_utils.ProviderRoutingError, match="gcloud_synthesis_is_internal"):
        provider_utils.get_provider_service_url("gcloud")


def test_get_provider_upstream_url_prefers_gateway_for_f5(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "http://gateway:8010/")
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011")

    assert provider_utils.get_provider_upstream_url("f5") == "http://gateway:8010"


def test_get_provider_upstream_url_falls_back_to_direct_f5(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "")
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011")

    assert provider_utils.get_provider_upstream_url("f5") == "http://f5:8011"


def test_get_provider_upstream_url_rejects_gcloud():
    with pytest.raises(provider_utils.ProviderRoutingError, match="gcloud_synthesis_is_internal"):
        provider_utils.get_provider_upstream_url("gcloud")


def test_get_provider_upstream_params_includes_provider_only_for_gateway(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "http://gateway:8010")
    assert provider_utils.get_provider_upstream_params("f5") == {"provider": "f5"}
    assert provider_utils.get_provider_upstream_params("f5", {"user_id": 42}) == {"user_id": 42, "provider": "f5"}

    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "")
    assert provider_utils.get_provider_upstream_params("f5") == {}
    assert provider_utils.get_provider_upstream_params("f5", {"user_id": 42}) == {"user_id": 42}


def test_voice_management_upstream_matches_f5_service(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011/")
    assert provider_utils.get_voice_management_upstream_url("f5") == "http://f5:8011"
    assert provider_utils.get_voice_management_upstream_params("f5", {"user_id": 7}) == {"user_id": 7}


def test_voice_management_upstream_rejects_gcloud():
    with pytest.raises(provider_utils.ProviderRoutingError, match="gcloud_voice_management_not_supported"):
        provider_utils.get_voice_management_upstream_url("gcloud")


def test_provider_capabilities_expose_f5_and_gcloud_contracts(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "http://gateway:8010")
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011")

    f5_capabilities = provider_utils.get_provider_capabilities("f5")
    gcloud_capabilities = provider_utils.get_provider_capabilities("gcloud")

    assert f5_capabilities["provider"] == "f5"
    assert f5_capabilities["voice_crud"] is True
    assert f5_capabilities["official_self_host_path"] == "tts_worker_agent"
    assert f5_capabilities["synthesis_via"] == "gateway"

    assert gcloud_capabilities["provider"] == "gcloud"
    assert gcloud_capabilities["voice_crud"] is False
    assert gcloud_capabilities["official_cloud_path"] == "internal"
    assert gcloud_capabilities["official_self_host_path"] is None


def test_get_all_provider_capabilities_contains_supported_providers(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "tts_gateway_url", "")
    monkeypatch.setattr(provider_utils.settings, "f5_tts_service_url", "http://f5:8011")

    payload = provider_utils.get_all_provider_capabilities()

    assert set(payload.keys()) == {"f5", "gcloud"}
    assert payload["f5"]["provider"] == "f5"
    assert payload["gcloud"]["provider"] == "gcloud"


def test_normalize_local_tts_endpoint_url_accepts_allowed_host(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "localhost")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "127.0.0.0/8")

    assert provider_utils.normalize_local_tts_endpoint_url("http://localhost:8001/") == "http://localhost:8001"


def test_normalize_local_tts_endpoint_url_rejects_path(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "localhost")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "127.0.0.0/8")

    with pytest.raises(ValueError, match="must not contain path"):
        provider_utils.normalize_local_tts_endpoint_url("http://localhost:8001/api/health")


def test_normalize_local_tts_endpoint_url_rejects_disallowed_host(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "localhost")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "127.0.0.0/8")

    with pytest.raises(ValueError, match="host is not allowed"):
        provider_utils.normalize_local_tts_endpoint_url("http://evil.example:9000")


def test_normalize_local_tts_endpoint_url_allows_host_from_cidr(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "10.0.0.0/8")

    assert provider_utils.normalize_local_tts_endpoint_url("http://10.5.6.7:8011") == "http://10.5.6.7:8011"


def test_get_local_tts_probe_endpoints_adds_docker_fallbacks_for_loopback(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "localhost,host.docker.internal,tts_service")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "127.0.0.0/8")

    assert provider_utils.get_local_tts_probe_endpoints("http://localhost:8011", "f5") == [
        "http://localhost:8011",
        "http://host.docker.internal:8011",
        "http://tts_service:8011",
    ]


def test_get_local_tts_probe_endpoints_keeps_non_loopback_singleton(monkeypatch):
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_hosts", "tts_service,host.docker.internal")
    monkeypatch.setattr(provider_utils.settings, "local_tts_allowed_cidrs", "")

    assert provider_utils.get_local_tts_probe_endpoints("http://tts_service:8011", "f5") == [
        "http://tts_service:8011",
    ]
