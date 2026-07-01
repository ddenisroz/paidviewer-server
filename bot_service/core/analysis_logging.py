# bot_service/core/analysis_logging.py
"""
Analysis Logging for LLM Feature Verification

JSONL format optimized for LLM parsing during testing sessions.
Enable with environment variable: ANALYSIS_MODE=true
"""
import json
import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Correlation ID for request tracing
_correlation_id: ContextVar[str] = ContextVar('correlation_id', default='')


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one"""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())[:8]
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str = None) -> str:
    """Set correlation ID for current context"""
    if cid is None:
        cid = str(uuid.uuid4())[:8]
    _correlation_id.set(cid)
    return cid


def clear_correlation_id():
    """Clear correlation ID"""
    _correlation_id.set('')


class JSONLFormatter(logging.Formatter):
    """Format log records as JSON Lines"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "correlation_id": get_correlation_id(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields from record
        if hasattr(record, 'feature'):
            log_data['feature'] = record.feature
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        if hasattr(record, 'success'):
            log_data['success'] = record.success
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class AnalysisLogger:
    """Logger for LLM analysis of feature correctness"""
    
    _instance: Optional['AnalysisLogger'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.enabled = os.getenv('ANALYSIS_MODE', '').lower() in ('true', '1', 'yes')
        self.logger = logging.getLogger('bot_service.analysis')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Don't send to parent loggers
        
        if self.enabled:
            self._setup_handlers()
        
        self._initialized = True
    
    def _setup_handlers(self):
        """Setup file handler for analysis logs"""
        # Create analysis logs directory
        repo_root = Path(__file__).resolve().parents[2]
        log_dir = repo_root / "logs" / "analysis"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "bot_service_analysis.jsonl"
        
        # Rotating file handler (50MB max, keep 5 files for ~6 hours of testing)
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=5,
            encoding='utf-8'
        )
        handler.setFormatter(JSONLFormatter())
        handler.setLevel(logging.DEBUG)
        
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        
        # Also log to console in debug format
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '[ANALYSIS] %(asctime)s - %(message)s'
        ))
        self.logger.addHandler(console)
        
        self.logger.info("Analysis logging initialized", extra={
            'feature': 'system',
            'action': 'init',
            'extra_data': {'log_file': str(log_file)}
        })
    
    def log(
        self,
        feature: str,
        action: str,
        message: str,
        success: bool = True,
        duration_ms: float = None,
        user_id: int = None,
        level: int = logging.INFO,
        **extra
    ):
        """Log a feature event for analysis"""
        if not self.enabled:
            return
        
        record_extra = {
            'feature': feature,
            'action': action,
            'success': success,
        }
        if duration_ms is not None:
            record_extra['duration_ms'] = round(duration_ms, 2)
        if user_id is not None:
            record_extra['user_id'] = user_id
        if extra:
            record_extra['extra_data'] = extra
        
        self.logger.log(level, message, extra=record_extra)


# Global instance
_analysis_logger: Optional[AnalysisLogger] = None


def get_analysis_logger() -> AnalysisLogger:
    """Get the global analysis logger instance"""
    global _analysis_logger
    if _analysis_logger is None:
        _analysis_logger = AnalysisLogger()
    return _analysis_logger


# ============ Convenience Functions ============

def log_feature(
    feature: str,
    action: str,
    message: str,
    success: bool = True,
    duration_ms: float = None,
    user_id: int = None,
    **extra
):
    """Log a generic feature event"""
    get_analysis_logger().log(
        feature=feature,
        action=action,
        message=message,
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        **extra
    )


def log_command(
    command: str,
    args: dict,
    result: str,
    success: bool = True,
    user_id: int = None,
    platform: str = None,
    duration_ms: float = None
):
    """Log chat command execution"""
    log_feature(
        feature='chat_command',
        action='execute',
        message=f"Command !{command}",
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        command=command,
        args=args,
        result=result,
        platform=platform
    )


def log_tts_request(
    text: str,
    voice: str,
    success: bool = True,
    user_id: int = None,
    duration_ms: float = None,
    audio_size: int = None,
    error: str = None
):
    """Log TTS request from bot"""
    log_feature(
        feature='tts_request',
        action='generate',
        message=f"TTS request: {len(text)} chars, voice={voice}",
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        text_length=len(text),
        text_preview=text[:100] if len(text) > 100 else text,
        voice=voice,
        audio_size=audio_size,
        error=error
    )


def log_websocket(
    action: str,
    user_id: int = None,
    message_type: str = None,
    success: bool = True,
    **extra
):
    """Log WebSocket events"""
    log_feature(
        feature='websocket',
        action=action,
        message=f"WebSocket {action}",
        success=success,
        user_id=user_id,
        message_type=message_type,
        **extra
    )


def log_api_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration_ms: float = None,
    user_id: int = None,
    **extra
):
    """Log API request"""
    success = 200 <= status_code < 400
    log_feature(
        feature='api_request',
        action=method.lower(),
        message=f"{method} {endpoint} -> {status_code}",
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        endpoint=endpoint,
        status_code=status_code,
        **extra
    )


def log_auth(
    action: str,
    user_id: int = None,
    platform: str = None,
    success: bool = True,
    error: str = None
):
    """Log authentication events"""
    log_feature(
        feature='auth',
        action=action,
        message=f"Auth {action} for user {user_id}",
        success=success,
        user_id=user_id,
        platform=platform,
        error=error
    )


def log_error(
    feature: str,
    error: Exception,
    context: str = None,
    user_id: int = None,
    **extra
):
    """Log an error for analysis"""
    get_analysis_logger().log(
        feature=feature,
        action='error',
        message=f"Error in {feature}: {str(error)}",
        success=False,
        user_id=user_id,
        level=logging.ERROR,
        error_type=type(error).__name__,
        error_message=str(error),
        context=context,
        **extra
    )
