import json

from tts_worker_agent.config import PROVISIONING_KIND, load_config, load_provisioning_bundle


def test_worker_agent_config_loader_accepts_utf8_bom(tmp_path):
    config_path = tmp_path / "config.json"
    payload = {
        "server_base_url": "http://127.0.0.1:8000",
        "providers": {
            "f5": {
                "enabled": True,
                "endpoint_url": "http://127.0.0.1:8011",
            },
        },
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8-sig")

    config = load_config(config_path)

    assert config.server_base_url == "http://127.0.0.1:8000"
    assert config.providers["f5"].endpoint_url == "http://127.0.0.1:8011"


def test_worker_agent_provisioning_loader_accepts_utf8_bom(tmp_path):
    provisioning_path = tmp_path / "paidviewer-worker-provisioning.json"
    payload = {
        "kind": PROVISIONING_KIND,
        "pairing_code": "PVW-TEST",
    }
    provisioning_path.write_text(json.dumps(payload), encoding="utf-8-sig")

    bundle = load_provisioning_bundle(provisioning_path)

    assert bundle["pairing_code"] == "PVW-TEST"
