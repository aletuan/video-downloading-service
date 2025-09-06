"""
Integration tests for bootstrap endpoints.

Tests the initial system setup endpoints used for creating
the first admin API key and system configuration.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import uuid


class TestBootstrapEndpoints:
    """Test bootstrap endpoints."""
    
    def test_bootstrap_status_needs_setup(self, client, mock_database, mock_storage):
        """Test bootstrap status when setup is needed."""
        # Mock no existing admin keys
        with patch("app.routers.bootstrap.select") as mock_select, \
             patch("app.core.database.get_db") as mock_get_db:
            
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []  # No admin keys
            mock_session.execute.return_value = mock_result
            mock_get_db.return_value.__aenter__.return_value = mock_session
            
            response = client.get("/api/v1/bootstrap/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["bootstrap_available"] is True
            assert data["status"] == "needs_setup"
    
    def test_bootstrap_status_already_configured(self, client, mock_database, mock_storage):
        """Test bootstrap status when already configured."""
        # Mock existing admin keys
        with patch("app.routers.bootstrap.select") as mock_select, \
             patch("app.core.database.get_db") as mock_get_db:
            
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_admin_key = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_admin_key]  # Has admin keys
            mock_session.execute.return_value = mock_result
            mock_get_db.return_value.__aenter__.return_value = mock_session
            
            response = client.get("/api/v1/bootstrap/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["bootstrap_available"] is False
            assert data["status"] == "configured"
    
    def test_bootstrap_create_admin_key_success(self, client, mock_database, mock_storage):
        """Test successful admin key creation via bootstrap."""
        setup_token = "test-setup-token"
        
        with patch("app.routers.bootstrap.settings") as mock_settings, \
             patch("app.routers.bootstrap.select") as mock_select, \
             patch("app.core.database.get_db") as mock_get_db, \
             patch("app.core.auth.APIKeyGenerator") as mock_generator:
            
            # Mock settings
            mock_settings.bootstrap_setup_token = setup_token
            
            # Mock no existing admin keys
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result
            mock_get_db.return_value.__aenter__.return_value = mock_session
            
            # Mock API key generation
            mock_key_gen = MagicMock()
            mock_key_gen.generate_api_key.return_value = "yvs_generated_admin_key"
            mock_generator.return_value = mock_key_gen
            
            # Mock APIKey creation
            with patch("app.routers.bootstrap.APIKey") as mock_api_key_class:
                mock_api_key = MagicMock()
                mock_api_key.id = str(uuid.uuid4())
                mock_api_key_class.return_value = mock_api_key
                
                response = client.post(
                    "/api/v1/bootstrap/admin-key",
                    json={"name": "Test Admin Key", "description": "Test description"},
                    headers={"X-Setup-Token": setup_token}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["name"] == "Test Admin Key"
        assert data["permission_level"] == "admin"
    
    def test_bootstrap_create_admin_key_invalid_token(self, client, mock_database, mock_storage):
        """Test admin key creation with invalid setup token."""
        with patch("app.routers.bootstrap.settings") as mock_settings:
            mock_settings.bootstrap_setup_token = "correct-token"
            
            response = client.post(
                "/api/v1/bootstrap/admin-key",
                json={"name": "Test Admin Key", "description": "Test description"},
                headers={"X-Setup-Token": "wrong-token"}
            )
        
        assert response.status_code == 403
        data = response.json()
        assert "Invalid setup token" in data["detail"]