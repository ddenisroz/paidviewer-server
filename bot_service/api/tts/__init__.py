from fastapi import APIRouter

from .synthesis_routes import tts_router as synthesis_router
from .settings_routes import router as settings_router
# Keep others for now if they exist, or comment out if we are deprecating
from .voices_routes import voices_router, user_voices_router
from .local_routes import local_tts_router
from .filters_routes import filters_router
from .blocked_users_routes import blocked_users_router
from .channel_points_routes import channel_points_router
from .worker_routes import worker_agent_router, worker_router

# Create main router
router = APIRouter()

# Include sub-routers
# Note: prefixes are defined in the sub-routers now
router.include_router(synthesis_router)
router.include_router(settings_router)
router.include_router(voices_router)
router.include_router(user_voices_router)
router.include_router(local_tts_router)
router.include_router(filters_router) 
router.include_router(blocked_users_router)
router.include_router(channel_points_router)
router.include_router(worker_router)
router.include_router(worker_agent_router)

# Export the main router as 'tts_router' for main.py convenience
tts_router = router
