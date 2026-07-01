import base64
from datetime import timedelta

from core.datetime_utils import utcnow_naive
from models import LocalTTSEndpoint, TTSJob, WorkerPairingToken


def _activate_worker(client, pairing_code: str, *, supports_f5: bool = True, label: str = "Test Worker"):
    response = client.post(
        "/api/worker-agent/activate",
        json={
            "pairing_code": pairing_code,
            "label": label,
            "supports_f5": supports_f5,
            "capabilities": {
                "providers": [provider for provider, enabled in (("f5", supports_f5),) if enabled],
                "runtime": "pytest",
                "agent_version": "1.0.0",
            },
            "runtime_metadata": {"hostname": "pytest-host", "agent_version": "1.0.0"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _poll_worker(client, auth_token: str, *, supports_f5: bool = True, wait_for_jobs: bool = False):
    response = client.post(
        "/api/worker-agent/poll",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "max_jobs": 1,
            "wait_for_jobs": wait_for_jobs,
            "supports_f5": supports_f5,
            "capabilities": {
                "providers": [provider for provider, enabled in (("f5", supports_f5),) if enabled],
                "agent_version": "1.0.0",
            },
            "runtime_metadata": {"hostname": "pytest-host", "agent_version": "1.0.0"},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_worker_pair_activate_and_complete_job(authenticated_client, db, test_user):
    token_response = authenticated_client.post(
        "/api/tts/workers/pairing-tokens",
        json={"label_hint": "My PC", "provider_hint": "f5"},
    )
    assert token_response.status_code == 200, token_response.text
    pairing_code = token_response.json()["pairing_code"]

    activation = _activate_worker(authenticated_client, pairing_code, label="Home PC")
    auth_token = activation["auth_token"]
    worker_key = activation["worker"]["worker_key"]

    list_response = authenticated_client.get("/api/tts/workers")
    assert list_response.status_code == 200, list_response.text
    workers = list_response.json()["workers"]
    assert any(worker["worker_key"] == worker_key for worker in workers)

    job_response = authenticated_client.post(
        "/api/tts/workers/jobs",
        json={
            "provider": "f5",
            "text": "hello from worker control plane",
            "voice": "default_voice",
            "payload": {
                "channel_name": "pytest",
                "author": "pytest",
                "user_id": test_user.id,
                "tts_settings": {"advanced_provider": "f5"},
            },
        },
    )
    assert job_response.status_code == 200, job_response.text
    job_id = job_response.json()["job"]["id"]

    poll_payload = _poll_worker(authenticated_client, auth_token)
    jobs = poll_payload["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["provider"] == "f5"

    audio_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt "
    complete_response = authenticated_client.post(
        f"/api/worker-agent/jobs/{job_id}/complete",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "content_type": "audio/wav",
            "result_payload": {"duration": 0.1},
        },
    )
    assert complete_response.status_code == 200, complete_response.text

    job_status = authenticated_client.get(f"/api/tts/workers/jobs/{job_id}")
    assert job_status.status_code == 200, job_status.text
    job = job_status.json()["job"]
    assert job["status"] == "completed"
    assert job["result_audio_url"]
    assert job["result_payload"]["provider"] == "f5"

    pairing_token_row = db.query(WorkerPairingToken).first()
    assert pairing_token_row is not None
    assert pairing_token_row.used_at is not None


def test_user_can_create_provisioning_bundle(authenticated_client):
    response = authenticated_client.post(
        "/api/tts/workers/provisioning",
        json={"label_hint": "Studio PC", "provider_hint": "f5"},
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    bundle = payload["provisioning_bundle"]

    assert payload["download_filename"].startswith("paidviewer-worker-provisioning-f5-")
    assert bundle["kind"] == "paidviewer_worker_provisioning"
    assert bundle["server_base_url"] == "http://testserver"
    assert bundle["pairing_code"]
    assert "http://localhost:5173" in bundle["trusted_origins"]
    assert bundle["label"] == "Studio PC"
    assert bundle["providers"]["f5"]["enabled"] is True
    assert bundle["providers"]["f5"]["endpoint_url"] == "http://127.0.0.1:8011"
    assert bundle["required_agent_version"]
    assert payload["worker_agent_contract"]["official_mode"] == "self_host"
    assert payload["worker_agent_contract"]["recommended_path"] == "tts_worker_agent"


def test_provisioning_bundle_includes_saved_local_runtime_key(authenticated_client, db, test_user):
    db.add(
        LocalTTSEndpoint(
            user_id=test_user.id,
            provider="f5",
            endpoint_url="http://127.0.0.1:8011",
            api_key="local-runtime-key",
            use_local=True,
        )
    )
    db.commit()

    response = authenticated_client.post(
        "/api/tts/workers/provisioning",
        json={"label_hint": "Studio PC", "provider_hint": "f5"},
    )
    assert response.status_code == 200, response.text

    bundle = response.json()["provisioning_bundle"]
    assert bundle["providers"]["f5"]["endpoint_url"] == "http://127.0.0.1:8011"
    assert bundle["providers"]["f5"]["api_key"] == "local-runtime-key"


def test_worker_activation_rejects_outdated_agent_version(authenticated_client, monkeypatch):
    monkeypatch.setattr("api.tts.worker_routes.settings.tts_worker_agent_required_version", "9.9.9")

    token_response = authenticated_client.post(
        "/api/tts/workers/pairing-tokens",
        json={"label_hint": "Old PC", "provider_hint": "f5"},
    )
    assert token_response.status_code == 200, token_response.text

    response = authenticated_client.post(
        "/api/worker-agent/activate",
        json={
            "pairing_code": token_response.json()["pairing_code"],
            "label": "Old Worker",
            "supports_f5": True,
            "capabilities": {"providers": ["f5"], "agent_version": "1.0.0"},
            "runtime_metadata": {"hostname": "pytest-host", "agent_version": "1.0.0"},
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "version_mismatch"
    assert detail["required_agent_version"] == "9.9.9"


def test_worker_poll_requeues_expired_jobs(authenticated_client, db):
    pairing_code = authenticated_client.post(
        "/api/tts/workers/pairing-tokens",
        json={"provider_hint": "f5"},
    ).json()["pairing_code"]
    activation = _activate_worker(authenticated_client, pairing_code)
    auth_token = activation["auth_token"]

    job_response = authenticated_client.post(
        "/api/tts/workers/jobs",
        json={"provider": "f5", "text": "lease expiry test"},
    )
    assert job_response.status_code == 200, job_response.text
    job_id = job_response.json()["job"]["id"]

    first_poll = _poll_worker(authenticated_client, auth_token)
    assert len(first_poll["jobs"]) == 1
    assert first_poll["jobs"][0]["attempt_count"] == 1

    job_row = db.query(TTSJob).filter(TTSJob.id == job_id).first()
    assert job_row is not None
    job_row.lease_expires_at = utcnow_naive() - timedelta(seconds=5)
    db.add(job_row)
    db.commit()

    second_poll = _poll_worker(authenticated_client, auth_token)
    assert len(second_poll["jobs"]) == 1
    assert second_poll["jobs"][0]["id"] == job_id
    assert second_poll["jobs"][0]["attempt_count"] == 2


def test_provider_specific_worker_rejects_unknown_provider_jobs(authenticated_client):
    pairing_code = authenticated_client.post(
        "/api/tts/workers/pairing-tokens",
        json={"provider_hint": "f5"},
    ).json()["pairing_code"]
    activation = _activate_worker(authenticated_client, pairing_code)
    auth_token = activation["auth_token"]

    invalid_job = authenticated_client.post(
        "/api/tts/workers/jobs",
        json={"provider": "unsupported", "text": "unsupported job"},
    )
    assert invalid_job.status_code == 400, invalid_job.text

    f5_job = authenticated_client.post(
        "/api/tts/workers/jobs",
        json={"provider": "f5", "text": "f5 job"},
    )
    assert f5_job.status_code == 200, f5_job.text
    f5_job_id = f5_job.json()["job"]["id"]

    poll_payload = _poll_worker(authenticated_client, auth_token)
    assert len(poll_payload["jobs"]) == 1
    assert poll_payload["jobs"][0]["id"] == f5_job_id
    assert poll_payload["jobs"][0]["provider"] == "f5"


def test_admin_can_issue_managed_pairing_and_managed_job(admin_client):
    pairing_response = admin_client.post(
        "/api/tts/admin/workers/pairing-tokens",
        json={"label_hint": "Managed F5", "provider_hint": "f5", "is_managed": True},
    )
    assert pairing_response.status_code == 200, pairing_response.text
    pairing_payload = pairing_response.json()
    assert pairing_payload["is_managed"] is True

    activation = _activate_worker(
        admin_client,
        pairing_payload["pairing_code"],
        supports_f5=True,
        label="Managed F5 Worker",
    )
    auth_token = activation["auth_token"]

    job_response = admin_client.post(
        "/api/tts/admin/workers/jobs",
        json={"provider": "f5", "text": "managed f5 job"},
    )
    assert job_response.status_code == 200, job_response.text
    job_id = job_response.json()["job"]["id"]

    poll_payload = _poll_worker(admin_client, auth_token)
    assert len(poll_payload["jobs"]) == 1
    assert poll_payload["jobs"][0]["id"] == job_id
    assert poll_payload["jobs"][0]["provider"] == "f5"

    workers_response = admin_client.get("/api/tts/admin/workers")
    assert workers_response.status_code == 200, workers_response.text
    workers = workers_response.json()["workers"]
    managed_worker = next(worker for worker in workers if worker["worker_key"] == activation["worker"]["worker_key"])
    assert managed_worker["is_managed"] is True
