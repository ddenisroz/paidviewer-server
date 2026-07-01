# bot_service/api/donationalerts_api.py
"""DonationAlerts API - Clean Architecture version."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from urllib.parse import urlencode, urlparse
from core.database import get_db
from auth.auth import get_current_user, get_current_user_optional
from core.config import settings
from repositories.user_token_repository import UserTokenRepository
from repositories.donation_alert_repository import DonationAlertRepository
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/donationalerts", tags=["donationalerts"])
_DONATIONALERTS_ALLOWED_AUTH_HOSTS = {"www.donationalerts.com", "donationalerts.com"}


def _is_safe_donationalerts_auth_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if any(ch in url for ch in ("\r", "\n", "\t")):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    return (parsed.netloc or "").lower() in _DONATIONALERTS_ALLOWED_AUTH_HOSTS


@router.get("/status")
async def get_donationalerts_status(
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Get the DonationAlerts status."""
    try:
        # Extract user_id from user dict
        user_id = user.get('id') if user else None
        
        if not user_id:
            return {
                "success": True,
                "connected": False,
                "user_info": None
            }

        # Check whether a DonationAlerts token exists in the repository.
        token_repo = UserTokenRepository(db)
        token = token_repo.get_by_user_and_platform(user_id, "donationalerts")

        if token and token.access_token:
            return {
                "success": True,
                "connected": True,
                "user_info": {
                    "platform_user_id": token.platform_user_id
                }
            }
        else:
            return {
                "success": True,
                "connected": False,
                "user_info": None
            }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting DonationAlerts status")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/connect")
async def connect_donationalerts(
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    response: Response = None,
):
    """Connect DonationAlerts."""
    try:
        # Ensure that the user is authenticated.
        # NOTE: optional auth may return None for unauthenticated requests.
        if not user or not user.get('id') or user.get('id') <= 0:
            logger.error("User not authenticated")
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        user_id = user.get('id')

        # Read the current settings.
        client_id = settings.donationalerts_client_id
        redirect_uri = settings.donationalerts_redirect_uri

        # Validate the settings.
        if not client_id:
            logger.error("DONATIONALERTS_CLIENT_ID not set in environment variables")
            raise HTTPException(status_code=503, detail="DonationAlerts integration is not configured")

        # Build the authorization URL.
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "oauth-user-show oauth-donation-subscribe oauth-donation-index",
            "state": state,
        }
        auth_url = f"https://www.donationalerts.com/oauth/authorize?{urlencode(params)}"

        if not _is_safe_donationalerts_auth_url(auth_url):
            logger.error("Unsafe DonationAlerts auth URL generated for user %s", user_id)
            raise HTTPException(status_code=500, detail="Failed to generate secure auth URL")

        if response is not None:
            response.set_cookie(
                key="oauth_state_da",
                value=state,
                max_age=600,
                httponly=True,
                samesite="lax",
                secure=settings.is_production,
            )

        logger.info("DonationAlerts auth URL generated for user %s", user_id)

        return {
            "success": True,
            "message": "DonationAlerts connection initiated",
            "auth_url": auth_url
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error connecting DonationAlerts")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/disconnect")
async def disconnect_donationalerts(
    user: dict = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Disconnect DonationAlerts."""
    try:
        if not user or not user.get('id') or user.get('id') <= 0:
            raise HTTPException(status_code=401, detail="Not authenticated")
            
        user_id = user.get('id')

        # Remove the DonationAlerts token through the repository.
        token_repo = UserTokenRepository(db)
        token_repo.delete_by_user_and_platform(user_id, "donationalerts")

        logger.info(f"[OK] Disconnected DonationAlerts for user {user_id}")
        return {
            "success": True,
            "message": "DonationAlerts disconnected successfully"
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error disconnecting DonationAlerts")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/donations")
async def get_donations_history(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the user's donation history."""
    try:
        user_id = user.get('id')
        donation_repo = DonationAlertRepository(db)

        # Load the data through the repository.
        total = donation_repo.count_by_user_id(user_id)
        donations = donation_repo.get_by_user_id(user_id, limit=limit, offset=offset)

        return {
            "success": True,
            "donations": [
                {
                    "id": d.id,
                    "amount": d.amount,
                    "currency": d.currency,
                    "message": d.message,
                    "channel_name": d.channel_name,
                    "processed_at": d.processed_at.isoformat() if d.processed_at else None,
                    "is_processed": d.is_processed,
                    "alert_id": d.alert_id
                }
                for d in donations
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "pages": (total + limit - 1) // limit if limit > 0 else 0
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting donations")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/donations/stats")
async def get_donations_stats(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get donation statistics."""
    try:
        from datetime import timedelta
        from datetime import datetime as dt

        user_id = user.get('id')
        donation_repo = DonationAlertRepository(db)

        # All-time statistics
        total_donations = donation_repo.count_by_user_id(user_id)
        total_amount = donation_repo.sum_amount_by_user(user_id)

        # Last-month statistics
        one_month_ago = dt.utcnow() - timedelta(days=30)
        month_donations = donation_repo.count_by_user_since(user_id, one_month_ago)
        month_amount = donation_repo.sum_amount_by_user_since(user_id, one_month_ago)

        # Last-week statistics
        one_week_ago = dt.utcnow() - timedelta(days=7)
        week_donations = donation_repo.count_by_user_since(user_id, one_week_ago)
        week_amount = donation_repo.sum_amount_by_user_since(user_id, one_week_ago)

        return {
            "success": True,
            "stats": {
                "total_donations": total_donations,
                "total_amount": round(total_amount, 2),
                "average_donation": round(total_amount / total_donations if total_donations > 0 else 0, 2),
                "month_donations": month_donations,
                "month_amount": round(month_amount, 2),
                "week_donations": week_donations,
                "week_amount": round(week_amount, 2)
            }
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting donations stats")
        raise HTTPException(status_code=500, detail="Internal server error")
