# bot_service/integrations/donationalerts/client.py
"""Base DonationAlerts API client for the new integration layer."""

import logging
from typing import Optional, Dict, Any

from integrations.base import BaseIntegrationClient, TokenInfo

logger = logging.getLogger(__name__)


class DonationAlertsClient(BaseIntegrationClient):
    """Base DonationAlerts API client."""
    
    BASE_URL = "https://www.donationalerts.com/api/v1"
    
    def __init__(self):
        super().__init__(self.BASE_URL)
    
    async def _get_headers(self, token: Optional[TokenInfo] = None) -> Dict[str, str]:
        """Build headers for the DonationAlerts API."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers
    
    # Additional methods will be added as runtime logic moves into the integration layer.
