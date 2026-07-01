# bot_service/tests/test_api_admin_dashboard.py
"""
Тесты для Admin Dashboard API
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_dashboard_stats_unauthorized(client: TestClient):
    """Тест: неавторизованный доступ к dashboard stats должен возвращать 401"""
    response = client.get("/api/admin/dashboard/stats")
    assert response.status_code == 401
