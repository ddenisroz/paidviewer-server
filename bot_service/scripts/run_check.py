#!/usr/bin/env python3
"""Single entry point for safe backend checks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


CHECK_SCRIPTS = {
    "admin": "dev/check_admin.py",
    "bot-token": "dev/check_bot_token.py",
    "postgres-data": "check_postgresql_data.py",
    "sessions": "dev/check_sessions.py",
    "tokens": "dev/check_tokens.py",
    "tts-enabled": "dev/check_tts_enabled.py",
    "tts-status": "dev/check_tts_status.py",
    "twitch-token": "dev/check_twitch_token.py",
    "user-whitelist": "dev/check_user_whitelist.py",
}


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def list_checks() -> None:
    print("Available checks:")
    for alias, script in sorted(CHECK_SCRIPTS.items()):
        print(f"  {alias:14} -> {script}")


def run_check(check_name: str, script_args: list[str]) -> int:
    script_name = CHECK_SCRIPTS.get(check_name)
    if not script_name:
        print(f"[ERROR] Unknown check: {check_name}")
        list_checks()
        return 2

    script_path = _scripts_dir() / script_name
    if not script_path.exists():
        print(f"[ERROR] Script not found: {script_path}")
        return 2

    command = [sys.executable, str(script_path), *script_args]
    print(f"[RUN] {' '.join(command)}")
    completed = subprocess.run(command, check=False)
    return int(completed.returncode or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Single launcher for safe backend checks")
    parser.add_argument("check_name", nargs="?", help="Check alias (see --list)")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="Arguments for the target script")
    parser.add_argument("--list", action="store_true", help="Show available checks")
    args = parser.parse_args()

    if args.list or not args.check_name:
        list_checks()
        return 0

    return run_check(args.check_name, args.script_args)


if __name__ == "__main__":
    raise SystemExit(main())
