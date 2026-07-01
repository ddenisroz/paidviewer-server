# bot_service/tests/test_api/test_basic_endpoints.py
"""
Basic API endpoint tests - minimal working tests
"""
import pytest
from fastapi.testclient import TestClient


class TestBasicEndpoints:
    """Test basic public endpoints"""
    
    def test_health_check(self, client: TestClient):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "bot_service"
    
    def test_openapi_docs(self, client: TestClient):
        """Test OpenAPI documentation is available"""
        response = client.get("/docs")
        assert response.status_code == 200


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_auth_status_no_session(self, client: TestClient):
        """Test auth status without session"""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == False
    
    def test_auth_status_with_session(self, authenticated_client: TestClient):
        """Test auth status with valid session"""
        response = authenticated_client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == True
        assert "user" in data
    
    def test_logout(self, authenticated_client: TestClient):
        """Test logout endpoint"""
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == 200


class TestDatabaseHealthEndpoints:
    """Test database health monitoring endpoints"""
    
    def test_database_health(self, admin_client: TestClient):
        """Test database health endpoint"""
        response = admin_client.get("/api/admin/database/health")
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "checks" in data
    
    def test_database_pool_status(self, admin_client: TestClient):
        """Test database pool status endpoint"""
        response = admin_client.get("/api/admin/database/pool-status")
        assert response.status_code == 200
        data = response.json()
        # SQLite uses StaticPool, PostgreSQL uses QueuePool
        assert "pool_size" in data or "pool_class" in data
        assert "status" in data
    
    def test_database_health_requires_admin(self, authenticated_client: TestClient):
        """Test that database health requires admin access"""
        response = authenticated_client.get("/api/admin/database/health")
        # Should be 403 Forbidden for non-admin users
        assert response.status_code in [401, 403]
