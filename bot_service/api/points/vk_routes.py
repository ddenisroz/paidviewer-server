from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
import logging

from core.database import get_db
from services.platform_rewards_service import get_platform_rewards_service
from auth.auth import get_current_user
from core.security_modern import limiter
from api.points.routes import CreateRewardRequest, ToggleRewardRequest, ProcessVKDemandsRequest

logger = logging.getLogger('bot_service')

points_vk_router = APIRouter(tags=["points_vk"])

VK_REWARDS_REQUIRED_ROLE = "channel_owner"
VK_REWARDS_DEFAULT_REASON = "Подключите VK Live с правами на управление наградами и очередью запросов."


def _vk_rewards_capability_response(
    can_create: bool,
    reason: str | None,
    rewards: list | None = None,
) -> JSONResponse:
    return JSONResponse(content={
        "success": True,
        "platform": "vk",
        "capability": {
            "can_create": can_create,
            "reason": reason,
            "required_role": VK_REWARDS_REQUIRED_ROLE,
            "platform": "vk",
        },
        "rewards": rewards or [],
    })


@points_vk_router.get("/rewards/vk")
async def get_vk_rewards(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VK channel rewards."""
    try:
        rewards = await get_platform_rewards_service().get_rewards(user['id'], 'vk', db)
        return _vk_rewards_capability_response(True, None, rewards)
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            reason = exc.detail if isinstance(exc.detail, str) and exc.detail.strip() else VK_REWARDS_DEFAULT_REASON
            return _vk_rewards_capability_response(False, reason, [])
        raise
    except Exception:
        logger.exception("[ERROR] [VK REWARDS] Error")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.post("/rewards/vk/create")
@limiter.limit("10/minute")
async def create_vk_reward(
    request: Request,
    reward_data: CreateRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a reward on VK Live."""
    try:
        result = await get_platform_rewards_service().create_reward(
            user['id'], 'vk', reward_data.dict(), db
        )

        return {
            "success": True,
            "platform": "vk",
            "reward": result
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating VK reward")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.patch("/rewards/vk/{reward_id}")
async def update_vk_reward(
    reward_id: str,
    reward_data: CreateRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a reward on VK Live."""
    try:
        result = await get_platform_rewards_service().update_reward(
            user['id'], 'vk', reward_id, reward_data.dict(), db
        )

        return JSONResponse(content={
            "success": True,
            "platform": "vk",
            "reward": result
        })

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating VK reward")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.delete("/rewards/vk/{reward_id}")
@limiter.limit("20/minute")
async def delete_vk_reward(
    request: Request,
    reward_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a reward on VK Live."""
    try:
        await get_platform_rewards_service().delete_reward(user['id'], 'vk', reward_id, db)

        return JSONResponse(content={
            "success": True,
            "platform": "vk",
            "message": "Reward deleted."
        })

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting VK reward")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.patch("/rewards/vk/{reward_id}/toggle")
async def toggle_vk_reward(
    reward_id: str,
    request: ToggleRewardRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable or disable a VK Live reward."""
    try:
        success = await get_platform_rewards_service().toggle_reward(
            user['id'], 'vk', reward_id, request.is_enabled, db
        )

        if success:
            return JSONResponse(content={
                "success": True,
                "platform": "vk",
                "is_enabled": request.is_enabled,
                "message": f"Reward {'enabled' if request.is_enabled else 'disabled'}"
            })
        raise HTTPException(status_code=400, detail="VK Live API failed to toggle the reward.")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error toggling VK reward")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.get("/rewards/vk/demands")
async def get_vk_reward_demands(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get VK Live reward requests."""
    try:
        demands = await get_platform_rewards_service().get_demands(user['id'], 'vk', db)

        return JSONResponse(content={
            "success": True,
            "platform": "vk",
            "demands": demands
        })

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting VK reward demands")
        raise HTTPException(status_code=500, detail="Internal server error")


@points_vk_router.post("/rewards/vk/demands/process")
async def process_vk_reward_demands(
    request_data: ProcessVKDemandsRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Process VK Live reward requests (accept or reject)."""
    try:
        result = await get_platform_rewards_service().process_demands(
            user['id'], 'vk', request_data.demand_ids, request_data.action, db
        )

        if result:
            return JSONResponse(content={
                "success": True,
                "platform": "vk",
                "action": request_data.action,
                "processed_count": len(request_data.demand_ids),
                "message": f"Requests {'accepted' if request_data.action == 'accept' else 'rejected'}"
            })
        raise HTTPException(status_code=400, detail="Failed to process reward requests.")

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error processing VK reward demands")
        raise HTTPException(status_code=500, detail="Internal server error")
