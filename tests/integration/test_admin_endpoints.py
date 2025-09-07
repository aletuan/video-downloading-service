"""
Integration tests for admin endpoints.

Tests the admin API key management endpoints including creation,
listing, updating, and deletion of API keys.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import uuid


class TestAdminEndpoints:
    """Test admin endpoints."""
    
    def test_admin_endpoints_require_auth(self, client, mock_database, mock_storage):
        """Test that admin endpoints require authentication."""
        endpoints = [
            ("GET", "/api/v1/admin/api-keys"),
            ("POST", "/api/v1/admin/api-keys"),
            ("GET", "/api/v1/admin/stats")
        ]
        
        for method, endpoint in endpoints:
            response = client.request(method, endpoint)
            assert response.status_code in [401, 403]
    
    @patch("app.routers.admin.validate_api_key")
    @patch("app.core.database.get_db")
    def test_list_api_keys_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test successful API keys listing."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        mock_key1 = MagicMock()
        mock_key1.to_dict.return_value = {"id": "key1", "name": "Test Key 1"}
        mock_key2 = MagicMock()  
        mock_key2.to_dict.return_value = {"id": "key2", "name": "Test Key 2"}
        
        mock_result.scalars.return_value.all.return_value = [mock_key1, mock_key2]
        mock_session.execute.return_value = mock_result
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            "/api/v1/admin/api-keys",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "api_keys" in data
        assert "total" in data
    
    @patch("app.routers.admin.validate_api_key")
    @patch("app.core.database.get_db")
    def test_create_api_key_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test successful API key creation."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True,
            name="Test Admin"
        )
        
        # Mock database operations
        mock_session = AsyncMock()
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        # Mock APIKey creation
        with patch("app.routers.admin.APIKey") as mock_api_key_class, \
             patch("app.core.auth.APIKeyGenerator") as mock_generator:
            
            mock_api_key = MagicMock()
            mock_api_key.id = str(uuid.uuid4())
            mock_api_key.to_dict.return_value = {
                "id": str(uuid.uuid4()),
                "name": "Test Download Key",
                "permission_level": "download"
            }
            mock_api_key_class.return_value = mock_api_key
            
            # Mock API key generation
            mock_key_gen = MagicMock()
            mock_key_gen.generate_api_key.return_value = "yvs_generated_key"
            mock_generator.return_value = mock_key_gen
            
            response = client.post(
                "/api/v1/admin/api-keys",
                json={
                    "name": "Test Download Key",
                    "permission_level": "download",
                    "description": "Test description"
                },
                headers={"X-API-Key": admin_api_key}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert "key_info" in data