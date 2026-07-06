"""Test migration and bootstrap script expectations."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMigrationScript:
    """Test suite for migration/bootstrapping scripts."""

    def test_dockerfile_bootstraps_database_before_bot_startup(self):
        dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile.prod"
        assert dockerfile.exists(), "bot_service/Dockerfile.prod is missing"

        content = dockerfile.read_text(encoding="utf-8")

        assert "scripts/bootstrap_database.py" in content
        assert "uvicorn main:create_app" in content

    def test_env_example_files_complete(self):
        bot_env_path = Path(".env.example")
        if not bot_env_path.exists():
            return

        with open(bot_env_path, "r", encoding="utf-8") as file:
            bot_env_content = file.read()

        required_bot_vars = [
            "SECRET_KEY",
            "TOKEN_ENCRYPTION_KEY",
            "DATABASE_URL",
            "BOT_SERVICE_HOST",
            "BOT_SERVICE_PORT",
            "TWITCH_CLIENT_ID",
            "TWITCH_CLIENT_SECRET",
            "VK_CLIENT_ID",
            "VK_CLIENT_SECRET",
            "F5_TTS_SERVICE_URL",
            "QWEN_TTS_SERVICE_URL",
            "FRONTEND_URL",
            "CORS_ORIGINS",
        ]
        for var in required_bot_vars:
            if var not in bot_env_content:
                print(f"[WARN] {var} not found in bot_service/.env.example")

    def test_migration_scripts_exist(self):
        migrate_sh = Path("../scripts/migrate.sh")
        migrate_ps1 = Path("../scripts/migrate.ps1")

        if os.name != "nt":
            assert os.access(migrate_sh, os.X_OK), "scripts/migrate.sh is not executable"

    def test_migration_script_has_key_generation(self):
        migrate_sh = Path("../scripts/migrate.sh")
        if not migrate_sh.exists():
            return

        with open(migrate_sh, "r", encoding="utf-8") as file:
            content = file.read()

        if "openssl rand -hex 32" not in content:
            print("[WARN] SECRET_KEY generation not found")
        if "Fernet.generate_key" not in content:
            print("[WARN] Encryption key generation not found")

    def test_migration_script_creates_directories(self):
        migrate_sh = Path("../scripts/migrate.sh")
        if not migrate_sh.exists():
            return

        with open(migrate_sh, "r", encoding="utf-8") as file:
            content = file.read()

        for dir_name in ["data", "logs", "models", "voices", "audio"]:
            if dir_name not in content:
                print(f"[WARN] Directory creation for {dir_name} not found")

    def test_migration_script_points_to_server_smoke(self):
        migrate_sh = Path("../scripts/migrate.sh")
        if not migrate_sh.exists():
            return

        with open(migrate_sh, "r", encoding="utf-8") as file:
            content = file.read()

        assert "vps-deploy-smoke.sh" in content
        assert "deploy/docker/.env.example" in content

    def test_required_directories_structure(self):
        migrate_sh = Path("../scripts/migrate.sh")
        if not migrate_sh.exists():
            return

        with open(migrate_sh, "r", encoding="utf-8") as file:
            content = file.read()

        assert "/srv/paidviewer" in content
        for dirname in ["env", "uploads", "logs", "backups", "postgres", "redis", "bot-data"]:
            assert dirname in content

    def test_env_files_have_comments(self):
        bot_env_path = Path(".env.example")
        if not bot_env_path.exists():
            return

        with open(bot_env_path, "r", encoding="utf-8") as file:
            content = file.read()

        if "# ===" not in content:
            print("[WARN] Section headers not found")
        if "SECURITY" not in content:
            print("[WARN] Security section not found")
        if "DATABASE" not in content:
            print("[WARN] Database section not found")
        if "TWITCH" not in content:
            print("[WARN] Twitch section not found")

        if "openssl rand -hex 32" not in content:
            print("[WARN] SECRET_KEY generation instruction not found")
        assert "Fernet" in content, "Encryption key generation instruction not found"

    def test_config_validation_on_startup(self):
        from core.config import validate_settings

        validate_settings()


def run_tests():
    test_suite = TestMigrationScript()
    tests = [
        test_suite.test_env_example_files_complete,
        test_suite.test_migration_scripts_exist,
        test_suite.test_migration_script_has_key_generation,
        test_suite.test_migration_script_creates_directories,
        test_suite.test_migration_script_installs_dependencies,
        test_suite.test_migration_script_runs_migrations,
        test_suite.test_required_directories_structure,
        test_suite.test_env_files_have_comments,
        test_suite.test_config_validation_on_startup,
    ]

    passed = 0
    for test in tests:
        test()
        passed += 1

    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if run_tests() else 1)

