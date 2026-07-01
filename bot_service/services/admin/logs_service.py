# bot_service/services/admin/logs_service.py
"""Service for reading and exporting logs."""

import os
import glob
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from core.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)


class LogsService:
    """Service for working with system logs."""

    def __init__(self):
        self._log_dirs = self._get_log_directories()

    def _get_log_directories(self) -> List[str]:
        """Return the list of log directories."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        dirs = []

        # bot_service/logs
        log_dir = os.path.join(base_dir, 'logs')
        if os.path.exists(log_dir):
            dirs.append(log_dir)

        # root/logs
        root_log_dir = os.path.join(os.path.dirname(base_dir), 'logs')
        if os.path.exists(root_log_dir):
            dirs.append(root_log_dir)

        return dirs

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None

        # Format: TIMESTAMP LEVEL MODULE: MESSAGE
        parts = line.split(' ', 3)
        if len(parts) >= 4:
            timestamp_str = f"{parts[0]} {parts[1]}"
            log_level = parts[2]
            message_part = parts[3]

            # Extract module
            module = "system"
            message = message_part
            if ':' in message_part:
                module_part, msg = message_part.split(':', 1)
                module = module_part.strip()
                message = msg.strip()

            # Parse timestamp
            try:
                timestamp = datetime.fromisoformat(
                    timestamp_str.replace('Z', '+00:00')
                )
            except ValueError:
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    timestamp = utcnow_naive()

            return {
                "timestamp": timestamp.isoformat(),
                "level": log_level.upper(),
                "module": module,
                "message": message
            }

        # Fallback when parsing fails
        return {
            "timestamp": utcnow_naive().isoformat(),
            "level": "INFO",
            "module": "system",
            "message": line
        }

    async def get_system_logs(
        self,
        level: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> dict:
        """Return system logs with optional filters."""
        logs: List[Dict[str, Any]] = []

        try:
            # Collect all .log files
            log_files = []
            for log_dir in self._log_dirs:
                log_files.extend(glob.glob(os.path.join(log_dir, '*.log')))

            # Read logs
            for log_file in log_files:
                lines = []
                try:
                    # Attempt 1: UTF-8 with BOM support
                    with open(log_file, "r", encoding="utf-8-sig") as f:
                        lines = f.readlines()
                except UnicodeDecodeError:
                    try:
                        # Attempt 2: CP1251 (common Windows Cyrillic encoding)
                        with open(log_file, "r", encoding="cp1251") as f:
                            lines = f.readlines()
                    except UnicodeDecodeError:
                        try:
                            # Attempt 3: CP866 (legacy DOS Cyrillic console encoding)
                            with open(log_file, "r", encoding="cp866") as f:
                                lines = f.readlines()
                        except UnicodeDecodeError:
                            try:
                                # Attempt 4: Latin-1 (always decodes, but text may look garbled)
                                with open(log_file, "r", encoding="latin1") as f:
                                    lines = f.readlines()
                            except Exception:
                                logger.exception("Failed to read log file '{log_file}'")
                                continue
                except Exception:
                    logger.exception("Error opening log file '{log_file}'")
                    continue

                for line in lines:
                    parsed = self._parse_log_line(line)
                    if parsed:
                        logs.append(parsed)

            # Sort by time, newest first
            logs.sort(key=lambda x: x["timestamp"], reverse=True)

        except Exception:
            logger.exception("Error reading system logs")
            logs = []

        # Filter by level
        if level:
            logs = [log for log in logs if log["level"] == level.upper()]

        # Filter by search query
        if search:
            search_lower = search.lower()
            logs = [log for log in logs if search_lower in log["message"].lower()]

        # Limit item count
        logs = logs[:limit]

        return {
            "logs": logs,
            "total": len(logs),
            "filters": {
                "level": level,
                "search": search,
                "limit": limit
            }
        }

    async def get_bots_logs(self) -> dict:
        """
        Return bot logs from files.

        Note: this can be extended later to read separate bot log files.
        For now bot logs are available through the main log file.
        """
        # Bot logs are currently available through the main log file.
        return {
            "logs": [],
            "message": "Bot logs are available in the main log file (logs/bot_service.log)"
        }

    async def export_system_logs(
        self,
        level: Optional[str] = None,
        search: Optional[str] = None
    ) -> dict:
        """Export system logs to CSV."""
        logs_data = await self.get_system_logs(level, search, limit=1000)

        # Generate CSV
        csv_lines = ["timestamp,level,module,message"]
        for log in logs_data["logs"]:
            # Escape quotes in the message
            message = log['message'].replace('"', '""')
            csv_lines.append(
                f"{log['timestamp']},{log['level']},{log['module']},\"{message}\""
            )

        csv_content = "\n".join(csv_lines)

        return {
            "content": csv_content,
            "filename": f"system_logs_{utcnow_naive().strftime('%Y%m%d_%H%M%S')}.csv",
            "mime_type": "text/csv"
        }


# Singleton instance
logs_service = LogsService()

