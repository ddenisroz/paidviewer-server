from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_settings_env_file_override_ignores_bad_local_dotenv() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tmp_path = Path(__file__).resolve().parent / ".pytest_tmp" / "config_env_isolation"
    shutil.rmtree(tmp_path, ignore_errors=True)
    tmp_path.mkdir(parents=True, exist_ok=True)

    bad_local_env = tmp_path / ".env"
    test_env = tmp_path / ".env.test"

    bad_local_env.write_text("DEBUG=release\n", encoding="utf-8")
    test_env.write_text("DEBUG=true\n", encoding="utf-8")

    env = os.environ.copy()
    env.pop("DEBUG", None)
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(repo_root) if not existing_pythonpath else os.pathsep.join([str(repo_root), existing_pythonpath])
    env["ENV_FILE"] = str(test_env)

    result = subprocess.run(
        [sys.executable, "-c", "from core.config import Settings; print(Settings().debug)"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "True"
