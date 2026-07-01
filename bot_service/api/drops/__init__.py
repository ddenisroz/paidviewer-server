from fastapi import APIRouter

from .config_routes import router as config_router
from .rewards_routes import router as rewards_router
from .history_routes import router as history_router
from .webhooks_routes import router as webhooks_router

# Create main router
router = APIRouter()

# Include sub-routers
router.include_router(config_router)
router.include_router(rewards_router)
router.include_router(history_router)
router.include_router(webhooks_router)
