"""
Integration tests for health check endpoints.

Tests basic and detailed health endpoints to ensure system
monitoring and diagnostics work correctly.
"""

import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_basic_health_check(self, client, mock_settings, mock_database, mock_storage):
        """Test basic health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["environment"] == "localhost"
        assert data["version"] == "1.0.0"
    
    def test_detailed_health_check_healthy(self, client, mock_settings, mock_database, mock_storage):
        """Test detailed health check when all systems are healthy."""
        response = client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["environment"] == "localhost"
        assert data["version"] == "1.0.0"
        assert "checks" in data
        assert data["checks"]["database"]["status"] == "healthy"
        assert data["checks"]["storage"]["status"] == "healthy"
    
    def test_detailed_health_check_unhealthy_database(self, client, mock_settings, mock_database, mock_storage):
        """Test detailed health check when database is unhealthy."""
        # Make database health check return unhealthy
        mock_database["manager"].health_check.return_value = {
            "status": "unhealthy",
            "connected": False,
            "error": "Connection failed"
        }
        
        response = client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"  # Overall status should be unhealthy
        assert data["checks"]["database"]["status"] == "unhealthy"
    
    def test_detailed_health_check_exception(self, client, mock_settings, mock_database, mock_storage):
        """Test detailed health check when an exception occurs."""
        # Make database health check raise an exception
        mock_database["manager"].health_check.side_effect = Exception("Database connection failed")
        
        response = client.get("/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "error" in data