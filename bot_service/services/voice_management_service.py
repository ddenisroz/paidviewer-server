import httpx
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from core.internal_service_auth import build_tts_httpx_client_kwargs
from repositories.user_voice_settings_repository import UserVoiceSettingsRepository
from services.voice_management_upstream import (
    VoiceManagementUpstreamClient,
    ensure_voice_management_provider,
    provider_admin_api_base,
    provider_request_params,
    provider_tts_api_base,
    raise_upstream_http_error,
    raise_upstream_transport_error,
    resolve_provider,
    tts_auth_headers,
)

logger = logging.getLogger(__name__)


class VoiceManagementService:
    """
    Service for managing text-to-speech voices.
    Handles interaction with external TTS service and local user voice settings.
    """
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserVoiceSettingsRepository(db)
        self.upstream = VoiceManagementUpstreamClient()

    def _resolve_provider(self, provider: str = "f5") -> str:
        return resolve_provider(provider)

    def _ensure_voice_management_provider(self, provider: str = "f5") -> str:
        return ensure_voice_management_provider(provider)

    def _provider_tts_api_base(self, provider: str = "f5") -> str:
        return provider_tts_api_base(provider)

    def _provider_admin_api_base(self, provider: str = "f5") -> str:
        return provider_admin_api_base(provider)

    def _tts_auth_headers(self, provider: str) -> dict:
        return tts_auth_headers(provider)

    def _provider_request_params(
        self,
        provider: str = "f5",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return provider_request_params(provider, extra)

    def _raise_upstream_http_error(
        self,
        *,
        response: httpx.Response,
        operation: str,
        default_detail: str,
    ) -> None:
        raise_upstream_http_error(
            response=response,
            operation=operation,
            default_detail=default_detail,
        )

    def _raise_upstream_transport_error(
        self,
        *,
        error: Exception,
        operation: str,
        timeout_detail: str,
        connect_detail: str,
    ) -> None:
        raise_upstream_transport_error(
            error=error,
            operation=operation,
            timeout_detail=timeout_detail,
            connect_detail=connect_detail,
        )

    async def get_global_voices(self, provider: str = "f5") -> List[Dict[str, Any]]:
        """Get list of available global voices from external TTS service."""
        try:
            response = await self.upstream.request(
                "get",
                url=f"{self._provider_tts_api_base(provider)}/voices/global",
                timeout=10.0,
                operation="fetch global voices",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            self._raise_upstream_http_error(
                response=response,
                operation="fetch global voices",
                default_detail="Failed to fetch global voices",
            )
        except HTTPException:
            raise

    async def get_user_custom_voices(self, user_id: int, provider: str = "f5") -> List[Dict[str, Any]]:
        """Get list of custom voices for a specific user."""
        try:
            response = await self.upstream.request(
                "get",
                url=f"{self._provider_tts_api_base(provider)}/user/voices/{user_id}",
                timeout=10.0,
                operation="fetch user voices",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return []
            self._raise_upstream_http_error(
                response=response,
                operation="fetch user voices",
                default_detail="Failed to fetch user voices",
            )
        except HTTPException:
            raise

    async def get_voice_info(self, voice_id: int, provider: str = "f5") -> Optional[Dict[str, Any]]:
        """Get information about a specific voice."""
        normalized_provider = self._ensure_voice_management_provider(provider)
        request_timeout = 10.0
        try:
            async with httpx.AsyncClient(timeout=request_timeout, **build_tts_httpx_client_kwargs()) as client:
                response = await client.get(
                    f"{self._provider_tts_api_base(normalized_provider)}/voices/{voice_id}",
                    headers=self._tts_auth_headers(normalized_provider),
                    params=self._provider_request_params(normalized_provider),
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    return None
                self._raise_upstream_http_error(
                    response=response,
                    operation="fetch voice info",
                    default_detail="Failed to fetch voice info",
                )
                return None
        except httpx.TimeoutException as error:
            logger.warning(
                "Voice info request timed out provider=%s voice_id=%s timeout=%ss",
                normalized_provider,
                voice_id,
                request_timeout,
            )
            raise HTTPException(status_code=504, detail="Voice service timed out") from error
        except httpx.RequestError as error:
            logger.warning(
                "Voice info request connection error provider=%s voice_id=%s error=%s",
                normalized_provider,
                voice_id,
                error,
            )
            raise HTTPException(status_code=503, detail="Failed to reach TTS voice service") from error
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("Error checking voice existence")
            raise HTTPException(status_code=500, detail="Internal server error") from error

    async def update_user_voice_settings(
        self, 
        user_id: int, 
        voice_id: int, 
        settings_data: Dict[str, Any],
        provider: str = "f5",
    ) -> Dict[str, Any]:
        """
        Update voice settings for a user.
        Handles both global voices (stored in DB) and custom voices (stored in external service).
        """
        # 1. Check if it's a global voice or custom voice
        normalized_provider = self._ensure_voice_management_provider(provider)
        voice_info = await self.get_voice_info(voice_id, provider=normalized_provider)
        
        if not voice_info:
            raise HTTPException(
                status_code=404, 
                detail=f"Voice {voice_id} not found"
            )
            
        is_global = voice_info.get('type') == 'global' or voice_info.get('is_global') is True
        
        if is_global:
            # Global voice overrides are stored locally per user in bot_service DB.
            persisted_settings = self.repository.update_or_create_by_voice_id(
                user_id=user_id,
                voice_id=voice_id,
                settings_data={**settings_data, "voice_name": voice_info.get("name")},
                tts_provider=normalized_provider,
            )

            return {
                "id": persisted_settings.id,
                "voice_id": persisted_settings.voice_id,
                "voice_name": persisted_settings.voice_name,
                "tts_provider": persisted_settings.tts_provider,
                "cfg_strength": persisted_settings.cfg_strength,
                "speed_preset": persisted_settings.speed_preset,
                "volume": persisted_settings.volume,
            }
        else:
            # Handle custom voice settings (stored in external service)
            # Verify ownership if possible, but the external service checks user_id usually
            try:
                response = await self.upstream.request(
                    "put",
                    url=f"{self._provider_tts_api_base(normalized_provider)}/user/voices/{voice_id}/settings",
                    timeout=10.0,
                    operation="update custom voice settings",
                    timeout_detail="TTS voice service timed out",
                    connect_detail="Failed to reach TTS voice service",
                    json=settings_data,
                    headers=self._tts_auth_headers(provider),
                    params=self._provider_request_params(normalized_provider),
                )
                if response.status_code == 200:
                    return response.json()
                self._raise_upstream_http_error(
                    response=response,
                    operation="update custom voice settings",
                    default_detail="Failed to update custom voice settings",
                )
            except HTTPException:
                raise
            except Exception:
                logger.exception("Error updating custom voice settings")
                raise HTTPException(status_code=500, detail="Internal server error")
    async def upload_user_voice(
        self,
        user_id: int,
        name: str,
        filename: str,
        content: bytes,
        content_type: str,
        provider: str = "f5",
        reference_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a user voice.
        Validates the file and sends it to the external TTS service.
        """
        import tempfile
        import os
        from validators.file_validators import FileValidator, validate_file_magic_number, ALLOWED_AUDIO_TYPES, MAX_VOICE_FILE_SIZE_MB

        # 1. Metadata Validation
        # Validate filename
        is_valid, error = FileValidator.validate_filename(filename)
        if not is_valid:
             raise HTTPException(status_code=400, detail=error)

        # Validate type/extension
        is_valid, error = FileValidator.validate_audio_metadata(filename, content_type)
        if not is_valid:
             raise HTTPException(status_code=400, detail=error)

        # Validate size
        is_valid, error = FileValidator.validate_size_limit(len(content), MAX_VOICE_FILE_SIZE_MB)
        if not is_valid:
             raise HTTPException(status_code=400, detail=error)

        # 2. Security Validation (Magic Number)
        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name

            is_valid, error = validate_file_magic_number(temp_file_path, ALLOWED_AUDIO_TYPES)
            if not is_valid:
                logger.warning(
                    f"[BLOCKED] [SECURITY] Voice upload rejected - invalid magic number: "
                    f"user={user_id}, filename={filename}, error={error}"
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid file content. File may be malicious or corrupted."
                )
            
            logger.info(f"[OK] [SECURITY] Voice file validated: user={user_id}, filename={filename}")

            # 3. External Service Upload
            files = {'file': (filename, content, content_type)}
            data = {'voice_name': name, 'user_id': str(user_id)}
            if reference_text:
                data['reference_text'] = reference_text
                data['sample_text'] = reference_text

            response = await self.upstream.request(
                "post",
                url=f"{self._provider_tts_api_base(provider)}/user/voices/upload",
                timeout=60.0,
                operation="upload user voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                files=files,
                data=data,
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(
                    "Voice upload upstream failed: status=%s body=%s",
                    response.status_code,
                    (response.text or "")[:500],
                )
                if response.status_code == 400:
                    detail = "Invalid voice upload request"
                elif response.status_code in (401, 403):
                    detail = "Voice service authorization failed"
                elif response.status_code == 404:
                    detail = "Voice endpoint not found"
                else:
                    detail = "Voice upload failed"
                raise HTTPException(status_code=response.status_code, detail=detail)

        except HTTPException:
            raise
        except Exception:
            logger.exception("Error uploading voice")
            raise HTTPException(status_code=500, detail="Internal server error")
        finally:
            # Cleanup temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file: {cleanup_error}")

    async def delete_custom_voice(self, user_id: int, voice_id: int, provider: str = "f5") -> bool:
        """Delete a custom voice for a user."""
        try:
            response = await self.upstream.request(
                "delete",
                url=f"{self._provider_tts_api_base(provider)}/user/voices/{voice_id}",
                timeout=10.0,
                operation="delete custom voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                params=self._provider_request_params(provider, {"user_id": user_id}),
                headers=self._tts_auth_headers(provider),
            )

            if response.status_code == 200:
                return True
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Voice not found")

            self._raise_upstream_http_error(
                response=response,
                operation="delete custom voice",
                default_detail="Failed to delete custom voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error deleting custom voice")
            raise HTTPException(status_code=500, detail="Failed to delete voice")

    async def admin_get_global_voices(self, provider: str = "f5") -> List[Dict[str, Any]]:
        """Get all global voices (for admin)."""
        try:
            response = await self.upstream.request(
                "get",
                url=f"{self._provider_admin_api_base(provider)}/voices",
                timeout=10.0,
                operation="fetch admin global voices",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                params=self._provider_request_params(provider, {"voice_type": "global"}),
                headers=self._tts_auth_headers(provider),
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return []
            self._raise_upstream_http_error(
                response=response,
                operation="fetch admin global voices",
                default_detail="Failed to fetch admin global voices",
            )
        except HTTPException:
            raise

    async def admin_update_global_voice(
        self,
        voice_id: int,
        settings_data: Dict[str, Any],
        provider: str = "f5",
    ) -> Dict[str, Any]:
        """Update global voice settings (admin)."""
        try:
            response = await self.upstream.request(
                "put",
                url=f"{self._provider_admin_api_base(provider)}/voices/{voice_id}/settings",
                timeout=10.0,
                operation="update global voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                json=settings_data,
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            self._raise_upstream_http_error(
                response=response,
                operation="update global voice",
                default_detail="Failed to update voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error updating global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_delete_global_voice(self, voice_id: int, provider: str = "f5") -> bool:
        """Delete a global voice (admin)."""
        try:
            response = await self.upstream.request(
                "delete",
                url=f"{self._provider_admin_api_base(provider)}/voices/{voice_id}",
                timeout=10.0,
                operation="delete global voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return True
            self._raise_upstream_http_error(
                response=response,
                operation="delete global voice",
                default_detail="Failed to delete voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error deleting global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_rename_global_voice(self, voice_id: int, new_name: str, provider: str = "f5") -> bool:
        """Rename a global voice (admin)."""
        try:
            response = await self.upstream.request(
                "put",
                url=f"{self._provider_admin_api_base(provider)}/voices/{voice_id}/rename",
                timeout=10.0,
                operation="rename global voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                params=self._provider_request_params(provider, {"new_name": new_name}),
                headers=self._tts_auth_headers(provider),
            )
            if response.status_code == 200:
                return True
            self._raise_upstream_http_error(
                response=response,
                operation="rename global voice",
                default_detail="Failed to rename voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error renaming global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_upload_voice(
        self,
        name: str,
        filename: str,
        content: bytes,
        content_type: str,
        provider: str = "f5",
    ) -> Dict[str, Any]:
        """Upload a global voice in selected provider service."""
        normalized_provider = self._ensure_voice_management_provider(provider)
        request_timeout = 60.0
        files = {"file": (filename, content, content_type)}
        data: Dict[str, str] = {}
        if name:
            data["name"] = name

        try:
            async with httpx.AsyncClient(timeout=request_timeout, **build_tts_httpx_client_kwargs()) as client:
                response = await client.post(
                    f"{self._provider_admin_api_base(normalized_provider)}/voices/upload",
                    files=files,
                    data=data,
                    headers=self._tts_auth_headers(normalized_provider),
                    params=self._provider_request_params(normalized_provider),
                )

            if response.status_code == 200:
                return response.json()

            logger.warning(
                "Admin upload voice failed provider=%s status=%s body=%s",
                provider,
                response.status_code,
                (response.text or "")[:500],
            )
            self._raise_upstream_http_error(
                response=response,
                operation="upload global voice",
                default_detail="Failed to upload voice",
            )
        except httpx.TimeoutException as error:
            logger.warning(
                "Admin upload voice timed out provider=%s timeout=%ss",
                normalized_provider,
                request_timeout,
            )
            raise HTTPException(status_code=504, detail="Voice upload timed out") from error
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error uploading global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_retranscribe_global_voice(self, voice_id: int, provider: str = "f5") -> Dict[str, Any]:
        """Retranscribe global voice in provider/gateway."""
        try:
            response = await self.upstream.request(
                "post",
                url=f"{self._provider_admin_api_base(provider)}/voices/{voice_id}/retranscribe",
                timeout=60.0,
                operation="retranscribe global voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            self._raise_upstream_http_error(
                response=response,
                operation="retranscribe global voice",
                default_detail="Failed to retranscribe voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error retranscribing global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_toggle_global_voice(self, voice_id: int, provider: str = "f5") -> Dict[str, Any]:
        """Toggle global voice active state in provider/gateway."""
        try:
            response = await self.upstream.request(
                "post",
                url=f"{self._provider_admin_api_base(provider)}/voices/{voice_id}/toggle",
                timeout=10.0,
                operation="toggle global voice",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            self._raise_upstream_http_error(
                response=response,
                operation="toggle global voice",
                default_detail="Failed to toggle voice",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error toggling global voice")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def admin_get_tts_stats(self, provider: str = "f5") -> Dict[str, Any]:
        """Fetch provider/gateway TTS stats for admin page."""
        try:
            response = await self.upstream.request(
                "get",
                url=f"{self._provider_admin_api_base(provider)}/stats",
                timeout=10.0,
                operation="load voice stats",
                timeout_detail="TTS voice service timed out",
                connect_detail="Failed to reach TTS voice service",
                headers=self._tts_auth_headers(provider),
                params=self._provider_request_params(provider),
            )
            if response.status_code == 200:
                return response.json()
            self._raise_upstream_http_error(
                response=response,
                operation="load voice stats",
                default_detail="Failed to load stats",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error fetching TTS stats")
            raise HTTPException(status_code=500, detail="Internal server error")





