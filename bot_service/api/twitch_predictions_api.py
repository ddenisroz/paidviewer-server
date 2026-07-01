"""Twitch predictions API."""

from typing import Any, List, Literal, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from auth.auth import get_current_user
from core.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/twitch/predictions", tags=["twitch-predictions"])


class PredictionOutcome(BaseModel):
    title: str = Field(..., min_length=1, max_length=25)


class PredictionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=45)
    outcomes: List[PredictionOutcome] = Field(..., min_length=2, max_length=10)
    prediction_window: int = Field(..., ge=30, le=1800)

    @field_validator("outcomes")
    @classmethod
    def validate_outcomes(cls, values: List[PredictionOutcome]) -> List[PredictionOutcome]:
        titles = [outcome.title for outcome in values]
        if len(titles) != len(set(titles)):
            raise ValueError("Outcomes must be unique")
        return values


class PredictionEnd(BaseModel):
    status: Literal["RESOLVED", "CANCELED"]
    winning_outcome_id: Optional[str] = None

    @field_validator("winning_outcome_id")
    @classmethod
    def validate_winner(cls, value: Optional[str], info):
        status = info.data.get("status")
        if status == "RESOLVED" and not value:
            raise ValueError("winning_outcome_id is required when status is RESOLVED")
        if status == "CANCELED" and value:
            raise ValueError("winning_outcome_id must be empty when status is CANCELED")
        return value


def _extract_user_id(user: Any) -> int:
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = user.get("id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id


async def get_twitch_credentials(user: dict) -> tuple[str, str, int]:
    from core.database import get_db
    from core.token_encryption import decrypt_token, is_token_encrypted
    from repositories.user_token_repository import UserTokenRepository

    user_id = _extract_user_id(user)
    db = next(get_db())
    try:
        token_repo = UserTokenRepository(db)
        user_token = token_repo.get_by_user_and_platform(user_id, "twitch")
        if not user_token or not user_token.access_token:
            logger.error("twitch_token_not_found", user_id=user_id)
            raise HTTPException(status_code=400, detail="Twitch OAuth token not found")

        token = user_token.access_token
        if is_token_encrypted(token):
            token = decrypt_token(token)

        broadcaster_id = str(user_token.platform_user_id or "").strip()
        if not broadcaster_id:
            logger.error("twitch_broadcaster_id_missing", user_id=user_id)
            raise HTTPException(status_code=400, detail="Twitch broadcaster id not found")

        return token, broadcaster_id, user_id
    finally:
        db.close()


async def make_twitch_api_request(
    method: str,
    endpoint: str,
    token: str,
    *,
    json_data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    url = f"https://api.twitch.tv/helix{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Id": settings.twitch_client_id,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=30.0,
            )

        if response.status_code == 200:
            return response.json()

        error_data = response.json() if response.text else {}
        error_message = error_data.get("message", "Unknown error")
        logger.error("twitch_api_error", endpoint=endpoint, status_code=response.status_code, error=error_message)
        raise HTTPException(status_code=response.status_code, detail=f"Twitch API error: {error_message}")
    except httpx.RequestError as exc:
        logger.error("twitch_api_request_error", endpoint=endpoint, error=str(exc))
        raise HTTPException(status_code=500, detail="Twitch API connection error")


@router.post("/create", response_model=dict)
async def create_prediction(prediction: PredictionCreate, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        data = {
            "broadcaster_id": broadcaster_id,
            "title": prediction.title,
            "outcomes": [{"title": outcome.title} for outcome in prediction.outcomes],
            "prediction_window": prediction.prediction_window,
        }

        logger.info(
            "twitch_prediction_creating",
            user_id=user_id,
            title=prediction.title,
            outcomes_count=len(prediction.outcomes),
        )
        response = await make_twitch_api_request("POST", "/predictions", token, json_data=data)
        prediction_data = response.get("data", [{}])[0]
        logger.info(
            "twitch_prediction_created",
            user_id=user_id,
            prediction_id=prediction_data.get("id"),
            title=prediction.title,
        )
        return {"success": True, "prediction": prediction_data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_prediction_create_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create prediction")


@router.patch("/{prediction_id}/end", response_model=dict)
async def end_prediction(prediction_id: str, end_data: PredictionEnd, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        data = {
            "broadcaster_id": broadcaster_id,
            "id": prediction_id,
            "status": end_data.status,
        }
        if end_data.winning_outcome_id:
            data["winning_outcome_id"] = end_data.winning_outcome_id

        logger.info("twitch_prediction_ending", user_id=user_id, prediction_id=prediction_id, status=end_data.status)
        response = await make_twitch_api_request("PATCH", "/predictions", token, json_data=data)
        prediction_data = response.get("data", [{}])[0]
        logger.info("twitch_prediction_ended", user_id=user_id, prediction_id=prediction_id, status=end_data.status)
        return {"success": True, "prediction": prediction_data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_prediction_end_error", prediction_id=prediction_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to end prediction")


@router.get("/active", response_model=dict)
async def get_active_predictions(current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, user_id = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request("GET", "/predictions", token, params={"broadcaster_id": broadcaster_id})
        predictions = response.get("data", [])
        logger.info("twitch_predictions_fetched", user_id=user_id, count=len(predictions))
        return {"success": True, "predictions": predictions}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_predictions_fetch_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load predictions")


@router.get("/{prediction_id}", response_model=dict)
async def get_prediction(prediction_id: str, current_user: dict = Depends(get_current_user)):
    try:
        token, broadcaster_id, _ = await get_twitch_credentials(current_user)
        response = await make_twitch_api_request(
            "GET",
            "/predictions",
            token,
            params={"broadcaster_id": broadcaster_id, "id": prediction_id},
        )
        predictions = response.get("data", [])
        if not predictions:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return {"success": True, "prediction": predictions[0]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("twitch_prediction_fetch_error", prediction_id=prediction_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to load prediction")
