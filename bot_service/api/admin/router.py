from fastapi import APIRouter
from api.admin import channels, dashboard, read_models, system, users, voices

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Include sub-routers from modules
# Note: The sub-routers occupy the same prefix scope, so we just aggregate them.
# The modules themselves define @router with prefix="/api/admin", so if we include them here,
# we need to be careful not to double-prefix.
# Typically, if modules define prefix="/api/admin", we should NOT use prefix here OR use prefix="" here and include them.
# However, if modules define prefix="/api/admin", and we do app.include_router(admin_router),
# and `admin_router` includes `dashboard.router`, then `dashboard.router` paths will be relative to whatever `admin_router` is mounted at?
# No, standard practice:
# 1. Module `dashboard.py`: router = APIRouter(prefix="/api/admin"...)
# 2. Aggregator `router.py`: router = APIRouter(); router.include_router(dashboard.router)
# 3. App: app.include_router(aggregator.router)

# To allow clean aggregation, I should create the aggregator router without prefix, 
# because sub-routers ALREADY have the full prefix.

router = APIRouter()

router.include_router(dashboard.router)
router.include_router(read_models.router)
router.include_router(users.router)
router.include_router(channels.router)
router.include_router(system.router)
router.include_router(voices.router)
