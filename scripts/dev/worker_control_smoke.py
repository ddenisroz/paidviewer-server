from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_SERVICE_ROOT = REPO_ROOT / "bot_service"
SELF_HOST_ROOT = Path(os.getenv("PAIDVIEWER_SELF_HOST_ROOT", REPO_ROOT.parent / "paidviewer-self-host"))
SELF_HOST_AGENT_ROOT = SELF_HOST_ROOT / "tts_worker_agent"

os.environ.setdefault("ENV_FILE", str(BOT_SERVICE_ROOT / ".env"))
os.environ["DEBUG"] = "true"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))
if SELF_HOST_AGENT_ROOT.exists() and str(SELF_HOST_ROOT) not in sys.path:
    sys.path.insert(0, str(SELF_HOST_ROOT))

from core.database import SessionLocal  # noqa: E402
from repositories.worker_repository import WorkerRepository  # noqa: E402
from services.tts.tts_manager import get_tts_manager  # noqa: E402
from services.worker_control.service import WorkerControlPlaneService  # noqa: E402

try:
    from tts_worker_agent.adapters import F5Adapter  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - operational smoke guard
    raise SystemExit(
        "Missing tts_worker_agent. Clone paidviewer-self-host next to paidviewer-server "
        "or set PAIDVIEWER_SELF_HOST_ROOT=/path/to/paidviewer-self-host."
    ) from exc


RIFF_SAMPLE = b"RIFF\x24\x00\x00\x00WAVEfmt "


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _build_f5_handler():
    class F5Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/tts/synthesize-channel":
                self.send_error(404)
                return

            content_length = int(self.headers.get("Content-Length") or "0")
            raw_payload = self.rfile.read(content_length)
            payload = json.loads(raw_payload.decode("utf-8"))
            voice_map = payload.get("voice_map") or {}
            selected_voice = payload.get("voice") or voice_map.get("f5") or "default_voice"

            response = {
                "success": True,
                "audio_url": "/audio/f5.wav",
                "selected_voice": selected_voice,
                "voice": selected_voice,
                "tts_type": "ai_f5",
                "duration": 0.11,
            }
            body = _json_bytes(response)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/audio/f5.wav":
                self.send_error(404)
                return

            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(RIFF_SAMPLE)))
            self.end_headers()
            self.wfile.write(RIFF_SAMPLE)

    return F5Handler


@contextmanager
def _serve(handler_cls) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _activate_managed_worker() -> dict:
    with SessionLocal() as db:
        service = WorkerControlPlaneService(db)
        pairing = service.issue_pairing_token(
            owner_user_id=None,
            label_hint="Smoke F5 worker",
            provider_hint="f5",
            is_managed=True,
        )
        return service.activate_worker(
            pairing_code=pairing["pairing_code"],
            label="Smoke F5 worker",
            supports_f5=True,
            capabilities={"providers": ["f5"], "runtime": "dev-smoke"},
            runtime_metadata={"hostname": "dev-smoke"},
        )


async def _process_one_worker_job(*, worker_key: str, adapter: F5Adapter) -> dict:
    for _ in range(50):
        with SessionLocal() as db:
            worker = WorkerRepository(db).get_by_worker_key(worker_key)
            if worker is None:
                raise RuntimeError(f"worker {worker_key} was not found")

            service = WorkerControlPlaneService(db)
            poll_payload = service.poll_worker_jobs(
                worker=worker,
                max_jobs=1,
                supports_f5=True,
                capabilities={"providers": ["f5"], "runtime": "dev-smoke"},
                runtime_metadata={"hostname": "dev-smoke"},
            )
            jobs = list(poll_payload.get("jobs") or [])
            if not jobs:
                await asyncio.sleep(0.2)
                continue

            job = jobs[0]
            try:
                result = adapter.synthesize(job)
                completed = await service.complete_job(
                    worker=worker,
                    job_id=str(job["id"]),
                    audio_base64=base64.b64encode(result.audio_bytes).decode("ascii"),
                    content_type=result.content_type,
                    source_url=result.source_url,
                    result_payload=result.result_payload,
                )
                return completed
            except Exception as error:
                return service.fail_job(
                    worker=worker,
                    job_id=str(job["id"]),
                    error_code="dev_smoke_failed",
                    error_message=str(error),
                    retryable=False,
                )

    raise TimeoutError(f"worker {worker_key} did not receive an f5 job in time")


async def main() -> None:
    with _serve(_build_f5_handler()) as f5_url:
        activation = _activate_managed_worker()
        worker_key = str(activation["worker"]["worker_key"])
        adapter = F5Adapter(endpoint_url=f5_url, api_key="")

        worker_task = asyncio.create_task(
            _process_one_worker_job(
                worker_key=worker_key,
                adapter=adapter,
            )
        )

        with SessionLocal() as db:
            result = await get_tts_manager().synthesize_tts(
                channel_name="dev-smoke",
                text="managed f5 worker smoke",
                author="dev-smoke",
                user_id=None,
                volume_level=50.0,
                use_ai_tts=True,
                use_basic_tts=False,
                db_session=db,
                tts_settings={
                    "engine": "f5tts",
                    "advanced_provider": "f5",
                    "f5_mode": "cloud",
                    "voice": "default_voice",
                },
                word_filter=[],
                blocked_users=[],
                engine="f5tts",
            )

        worker_result = await asyncio.wait_for(worker_task, timeout=15)

        if not result.get("success"):
            raise RuntimeError(f"f5 smoke failed: {result}")
        if not result.get("worker_path_used"):
            raise RuntimeError(f"f5 smoke did not use worker path: {result}")
        if result.get("provider") != "f5":
            raise RuntimeError(f"f5 smoke resolved wrong provider: {result}")
        if worker_result.get("status") != "completed":
            raise RuntimeError(f"f5 worker job did not complete: {worker_result}")

        print(
            f"[OK] provider=f5 worker_key={result.get('worker_key')} "
            f"audio_url={result.get('audio_url')}"
        )

    print("[OK] managed worker smoke completed for F5")


if __name__ == "__main__":
    asyncio.run(main())
