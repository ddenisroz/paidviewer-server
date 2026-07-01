import asyncio
import httpx
import os
import sys

# Add parent directory to path to import core modules if needed, 
# although this script looks standalone.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Placeholder token - should be replaced with a real one for testing
# or loaded from .env/DB
TOKEN = os.environ.get("VK_LIVE_USER_TOKEN", "")
VERIFY_SSL = os.environ.get("VK_API_VERIFY_SSL", "true").lower() != "false"

BASE_URL = "https://apidev.live.vkvideo.ru"

async def check_endpoints():
    endpoints = [
        "/v1/current_user",
        "/v1/user",
        "/v1/user/me",
        "/v1/channel",
        "/v1/channels"
    ]

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }

    print("Checking endpoints with configured token...")

    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        for ep in endpoints:
            try:
                print(f"Checking {ep}...")
                resp = await client.get(f"{BASE_URL}{ep}", headers=headers)
                print(f"Status: {resp.status_code}")
                if resp.status_code == 200:
                    print(f"Response: {resp.text[:200]}...")
            except Exception as e:
                print(f"Error checking {ep}: {e}")

if __name__ == "__main__":
    if not TOKEN:
        print("Please set VK_LIVE_USER_TOKEN env var to run this script.")
    else:
        asyncio.run(check_endpoints())
