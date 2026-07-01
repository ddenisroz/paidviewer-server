# services/database_maintenance/database_backup_service.py
"""Backup and restore operations for PostgreSQL database."""

import logging
import os
import pathlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DatabaseBackupService:
    """Service for backup/restore and backup file maintenance."""

    def __init__(self):
        self.repo_root = Path(__file__).resolve().parents[3]
        self.backup_dir = self.repo_root / "backups"

    def create_backup(self) -> Dict[str, Any]:
        """Create PostgreSQL dump with pg_dump."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            from core.config import settings as app_settings

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            database_url = app_settings.database_url
            if not database_url or "postgresql://" not in database_url:
                return {"success": False, "error": "PostgreSQL DATABASE_URL not configured"}

            parsed = urlparse(database_url)
            backup_file = self.backup_dir / f"backup_{timestamp}.sql"

            try:
                pg_dump_cmd = [
                    "pg_dump",
                    "-h",
                    parsed.hostname or "localhost",
                    "-p",
                    str(parsed.port or 5432),
                    "-U",
                    parsed.username,
                    "-d",
                    parsed.path[1:] if parsed.path else "",
                    "-f",
                    str(backup_file),
                ]

                env = os.environ.copy()
                if parsed.password:
                    env["PGPASSWORD"] = parsed.password

                result = subprocess.run(pg_dump_cmd, env=env, capture_output=True, text=True)

                if result.returncode == 0:
                    file_size = backup_file.stat().st_size
                    logger.info(
                        "[AUTH] PostgreSQL backup created: %s (%.2f MB)",
                        backup_file,
                        file_size / (1024 * 1024),
                    )
                    return {
                        "success": True,
                        "backup_file": str(backup_file),
                        "size_bytes": file_size,
                        "timestamp": timestamp,
                        "type": "postgresql",
                    }

                logger.error(
                    "pg_dump failed with returncode=%s stderr=%s",
                    result.returncode,
                    (result.stderr or "")[:500],
                )
                return {"success": False, "error": "pg_dump failed"}

            except FileNotFoundError:
                return {"success": False, "error": "pg_dump not found. Install PostgreSQL client tools."}
            except Exception:
                logger.exception("PostgreSQL backup error")
                return {"success": False, "error": "Internal server error"}

        except Exception:
            logger.exception("Error creating backup")
            return {"success": False, "error": "Internal server error"}

    def restore_from_backup(self) -> Dict[str, Any]:
        """Restore database from latest SQL backup."""
        try:
            if not self.backup_dir.exists():
                return {"success": False, "error": "No backups found"}

            from core.config import settings as app_settings

            database_url = app_settings.database_url
            if not database_url or "postgresql://" not in database_url:
                return {"success": False, "error": "PostgreSQL DATABASE_URL not configured"}

            backup_files = sorted(
                self.backup_dir.glob("backup_*.sql"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not backup_files:
                return {"success": False, "error": "No PostgreSQL backups found"}

            latest_backup = backup_files[0]
            return self.restore_from_backup_file(latest_backup.name)

        except Exception:
            logger.exception("Error restoring backup")
            return {"success": False, "error": "Internal server error"}

    def restore_from_backup_file(self, filename: str) -> Dict[str, Any]:
        """Restore database from specific SQL backup file."""
        try:
            backup_dir_path = self.backup_dir.resolve()

            if not filename.startswith("backup_") or not filename.endswith(".sql"):
                return {"success": False, "error": "Invalid PostgreSQL backup filename (must be .sql)"}
            if "/" in filename or "\\" in filename or ".." in filename:
                return {"success": False, "error": "Invalid file path"}

            backup_file_path = (backup_dir_path / filename).resolve()
            try:
                backup_file_path.relative_to(backup_dir_path)
            except ValueError:
                return {"success": False, "error": "Invalid file path"}

            if not backup_file_path.exists():
                return {"success": False, "error": "Backup file not found"}

            from core.config import settings

            database_url = settings.database_url
            if not database_url or "postgresql://" not in database_url:
                return {"success": False, "error": "PostgreSQL DATABASE_URL not configured"}

            parsed = urlparse(database_url)

            try:
                psql_cmd = [
                    "psql",
                    "-h",
                    parsed.hostname or "localhost",
                    "-p",
                    str(parsed.port or 5432),
                    "-U",
                    parsed.username,
                    "-d",
                    parsed.path[1:] if parsed.path else "",
                    "-f",
                    str(backup_file_path),
                ]

                env = os.environ.copy()
                if parsed.password:
                    env["PGPASSWORD"] = parsed.password

                result = subprocess.run(psql_cmd, env=env, capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info("[OK] PostgreSQL database restored from %s", filename)
                    return {
                        "success": True,
                        "restored_from": filename,
                        "type": "postgresql",
                        "message": f"PostgreSQL database restored from {filename}",
                    }

                logger.error(
                    "psql restore failed with returncode=%s stderr=%s",
                    result.returncode,
                    (result.stderr or "")[:500],
                )
                return {"success": False, "error": "Restore failed"}

            except FileNotFoundError:
                return {"success": False, "error": "psql not found. Install PostgreSQL client tools."}
            except Exception:
                logger.exception("PostgreSQL restore error")
                return {"success": False, "error": "Internal server error"}
        except Exception:
            logger.exception("Error restoring from %s", filename)
            return {"success": False, "error": "Internal server error"}

    def list_backups(self) -> Dict[str, Any]:
        """List all backup files."""
        try:
            if not self.backup_dir.exists():
                return {"success": True, "backups": []}

            backups = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith("backup_") and (filename.endswith(".db") or filename.endswith(".sql")):
                    file_path = self.backup_dir / filename
                    stat = file_path.stat()
                    backups.append(
                        {
                            "filename": filename,
                            "size_bytes": stat.st_size,
                            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )

            backups.sort(key=lambda x: x["created_at"], reverse=True)

            return {
                "success": True,
                "backups": backups,
                "total": len(backups),
                "total_size_bytes": sum(b["size_bytes"] for b in backups),
            }
        except Exception:
            logger.exception("Error listing backups")
            return {"success": False, "error": "Internal server error", "backups": []}

    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Delete single backup file by name."""
        try:
            backup_dir_path = self.backup_dir.resolve()

            if not filename.startswith("backup_") or not (filename.endswith(".db") or filename.endswith(".sql")):
                return {"success": False, "error": "Invalid backup filename"}
            if "/" in filename or "\\" in filename or ".." in filename:
                return {"success": False, "error": "Invalid file path"}

            file_path = (backup_dir_path / filename).resolve()
            try:
                file_path.relative_to(backup_dir_path)
            except ValueError:
                return {"success": False, "error": "Invalid file path"}

            if not file_path.exists():
                return {"success": False, "error": "Backup file not found"}

            file_size = file_path.stat().st_size
            file_path.unlink()

            logger.info("[DELETE] Backup deleted: %s (%.2f MB)", filename, file_size / (1024 * 1024))
            return {
                "success": True,
                "deleted_file": filename,
                "freed_bytes": file_size,
            }
        except Exception:
            logger.exception("Error deleting backup")
            return {"success": False, "error": "Internal server error"}
