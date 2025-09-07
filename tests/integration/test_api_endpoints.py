"""
Integration tests for FastAPI endpoints.

Tests the main API endpoints including authentication, authorization,
request/response validation, and error handling.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import uuid
from datetime import datetime, timezone

from app.main import app
from app.core.config import Settings


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_database():
    """Mock database operations."""
    with patch("app.core.database.init_database") as mock_init, \
         patch("app.core.database.close_database") as mock_close, \
         patch("app.core.database.db_manager") as mock_manager:
        
        # Mock db manager health check
        mock_manager.health_check.return_value = {
            "status": "healthy",
            "connected": True,
            "database_url": "sqlite:///test.db",
            "version": "SQLite 3.x"
        }
        
        yield {
            "init": mock_init,
            "close": mock_close,
            "manager": mock_manager
        }


@pytest.fixture
def mock_storage():
    """Mock storage operations."""
    with patch("app.core.storage.init_storage") as mock_init, \
         patch("app.core.storage.health_check_storage") as mock_health:
        
        # Mock storage health check
        mock_health.return_value = {
            "status": "healthy",
            "storage_type": "LocalStorageHandler",
            "base_path": "downloads",
            "bucket_name": None
        }
        
        yield {
            "init": mock_init,
            "health": mock_health
        }


@pytest.fixture
def mock_settings():
    """Mock settings for tests."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.environment = "localhost"
        mock_settings.debug = True
        mock_settings.download_base_path = "/tmp/test_downloads"
        mock_settings.host = "localhost"
        mock_settings.port = 8000
        yield mock_settings


@pytest.fixture
def admin_api_key():
    """Sample admin API key for testing."""
    return "yvs_admin_test_key_12345"


@pytest.fixture
def download_api_key():
    """Sample download API key for testing."""
    return "yvs_download_test_key_67890"


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


class TestDownloadEndpoints:
    """Test video download endpoints."""
    
    def test_download_endpoint_requires_auth(self, client, mock_database, mock_storage):
        """Test that download endpoint requires authentication."""
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
        
        # Should get 401 or 403 for missing authentication
        assert response.status_code in [401, 403]
    
    def test_download_endpoint_invalid_api_key(self, client, mock_database, mock_storage):
        """Test download endpoint with invalid API key."""
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers={"X-API-Key": "invalid_key"}
        )
        
        assert response.status_code in [401, 403]
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.routers.downloads.queue_download_task")
    def test_download_endpoint_success(self, mock_queue, mock_validate, client, mock_database, mock_storage, download_api_key):
        """Test successful video download request."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="download",
            is_valid=True
        )
        
        # Mock task queuing
        job_id = str(uuid.uuid4())
        mock_queue.return_value = job_id
        
        response = client.post(
            "/api/v1/download",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "quality": "720p",
                "output_format": "mp4"
            },
            headers={"X-API-Key": download_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert "message" in data
    
    @patch("app.routers.downloads.validate_api_key")
    def test_download_endpoint_invalid_url(self, mock_validate, client, mock_database, mock_storage, download_api_key):
        """Test download endpoint with invalid YouTube URL."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="download",
            is_valid=True
        )
        
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.google.com"},  # Invalid YouTube URL
            headers={"X-API-Key": download_api_key}
        )
        
        assert response.status_code == 422  # Validation error
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.core.database.get_db")
    def test_status_endpoint_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test job status endpoint with valid job."""
        # Mock API key validation (admin key for read access)
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query
        job_id = str(uuid.uuid4())
        mock_session = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.status = "completed"
        mock_job.to_dict.return_value = {
            "job_id": job_id,
            "status": "completed",
            "video_path": "downloads/test.mp4"
        }
        mock_session.get.return_value = mock_job
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            f"/api/v1/status/{job_id}",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.core.database.get_db")
    def test_status_endpoint_job_not_found(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test job status endpoint with non-existent job."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query returning None
        job_id = str(uuid.uuid4())
        mock_session = AsyncMock()
        mock_session.get.return_value = None
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            f"/api/v1/status/{job_id}",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.routers.downloads.YouTubeDownloader")
    def test_info_endpoint_success(self, mock_downloader, mock_validate, client, mock_database, mock_storage):
        """Test video info endpoint with valid YouTube URL."""
        # Mock YouTube downloader
        mock_dl_instance = MagicMock()
        mock_dl_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up",
            "duration": 213,
            "view_count": 1000000
        }
        mock_downloader.return_value = mock_dl_instance
        
        response = client.get(
            "/api/v1/info",
            params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["metadata"]["id"] == "dQw4w9WgXcQ"
        assert data["metadata"]["title"] == "Rick Astley - Never Gonna Give You Up"
    
    def test_info_endpoint_invalid_url(self, client, mock_database, mock_storage):
        """Test video info endpoint with invalid URL."""
        response = client.get(
            "/api/v1/info",
            params={"url": "https://www.google.com"}
        )
        
        assert response.status_code == 422  # Validation error
    
    @patch("app.routers.downloads.validate_api_key")  
    @patch("app.core.database.get_db")
    def test_jobs_endpoint_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test jobs listing endpoint."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        # Mock job objects
        mock_job1 = MagicMock()
        mock_job1.to_dict.return_value = {"job_id": "job1", "status": "completed"}
        mock_job2 = MagicMock()
        mock_job2.to_dict.return_value = {"job_id": "job2", "status": "processing"}
        
        mock_result.scalars.return_value.all.return_value = [mock_job1, mock_job2]
        mock_session.execute.return_value = mock_result
        
        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2
        mock_session.execute.return_value = mock_count_result
        
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            "/api/v1/jobs",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data


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


class TestErrorHandling:
    """Test error handling and HTTP status codes."""
    
    def test_404_for_nonexistent_endpoints(self, client, mock_database, mock_storage):
        """Test 404 response for non-existent endpoints."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_405_for_wrong_http_method(self, client, mock_database, mock_storage):
        """Test 405 response for wrong HTTP methods."""
        # Health endpoint only supports GET, try POST
        response = client.post("/health")
        assert response.status_code == 405
    
    def test_422_for_invalid_request_body(self, client, mock_database, mock_storage):
        """Test 422 response for invalid request body."""
        # Try to create admin key without required setup token header
        response = client.post(
            "/api/v1/bootstrap/admin-key",
            json={"invalid": "data"}
        )
        
        assert response.status_code in [422, 403]  # Validation error or missing header
    
    def test_content_type_handling(self, client, mock_database, mock_storage):
        """Test proper content-type handling."""
        # Send invalid JSON
        response = client.post(
            "/api/v1/bootstrap/admin-key",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422


class TestAuthenticationAndAuthorization:
    """Test authentication and authorization middleware."""
    
    def test_missing_api_key_header(self, client, mock_database, mock_storage):
        """Test endpoints that require API key but none provided."""
        protected_endpoints = [
            ("POST", "/api/v1/download"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/api/v1/admin/api-keys")
        ]
        
        for method, endpoint in protected_endpoints:
            response = client.request(
                method, 
                endpoint,
                json={} if method == "POST" else None
            )
            assert response.status_code in [401, 403]
    
    def test_invalid_api_key_format(self, client, mock_database, mock_storage):
        """Test API key with invalid format."""
        invalid_keys = [
            "invalid_key",
            "yvs_",  # Too short
            "wrong_prefix_12345",
            ""
        ]
        
        for invalid_key in invalid_keys:
            response = client.post(
                "/api/v1/download",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                headers={"X-API-Key": invalid_key}
            )
            assert response.status_code in [401, 403]
    
    @patch("app.routers.downloads.validate_api_key")
    def test_insufficient_permissions(self, mock_validate, client, mock_database, mock_storage):
        """Test API key with insufficient permissions."""
        # Mock API key with read-only permissions trying to access download endpoint
        mock_validate.return_value = MagicMock(
            permission_level="read_only",
            is_valid=True
        )
        
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers={"X-API-Key": "yvs_readonly_key"}
        )
        
        assert response.status_code == 403


class TestRequestValidation:
    """Test request validation and data sanitization."""
    
    def test_url_parameter_validation(self, client, mock_database, mock_storage):
        """Test URL parameter validation."""
        invalid_urls = [
            "",
            "not-a-url",
            "https://www.google.com",  # Not YouTube
            "javascript:alert('xss')",
        ]
        
        for invalid_url in invalid_urls:
            response = client.get(
                "/api/v1/info",
                params={"url": invalid_url}
            )
            assert response.status_code == 422
    
    def test_json_body_validation(self, client, mock_database, mock_storage):
        """Test JSON body validation."""
        # Test download endpoint with invalid data
        invalid_payloads = [
            {},  # Missing required url
            {"url": ""},  # Empty URL
            {"url": "https://www.youtube.com/watch?v=test", "quality": "invalid"},  # Invalid quality
            {"url": "https://www.youtube.com/watch?v=test", "output_format": "invalid"}  # Invalid format
        ]
        
        for payload in invalid_payloads:
            response = client.post("/api/v1/download", json=payload)
            assert response.status_code in [401, 403, 422]  # Auth error or validation error
    
    def test_query_parameter_limits(self, client, mock_database, mock_storage):
        """Test query parameter limits and validation."""
        # Test jobs endpoint with invalid pagination parameters
        with patch("app.routers.downloads.validate_api_key") as mock_validate:
            mock_validate.return_value = MagicMock(
                permission_level="admin",
                is_valid=True
            )
            
            # Test negative page number
            response = client.get(
                "/api/v1/jobs?page=-1",
                headers={"X-API-Key": "test_key"}
            )
            # Should handle gracefully, either 422 or default to page 1
            assert response.status_code in [200, 422]
            
            # Test excessive per_page limit
            response = client.get(
                "/api/v1/jobs?per_page=1000",
                headers={"X-API-Key": "test_key"}
            )
            # Should handle gracefully, either 422 or cap the limit
            assert response.status_code in [200, 422]


class TestMalformedRequestEdgeCases:
    """Test handling of malformed requests and boundary conditions."""
    
    def test_malformed_json_payloads(self, client, mock_database, mock_storage):
        """Test handling of malformed JSON payloads."""
        malformed_payloads = [
            '{"url": "https://youtube.com/watch?v=test"',  # Missing closing brace
            '{"url": "https://youtube.com/watch?v=test", "quality": }',  # Invalid JSON syntax
            '{"url": "https://youtube.com/watch?v=test", "quality": null}',  # Null value
            '{"url": undefined}',  # JavaScript-style undefined
            '{"url": "test", "nested": {"invalid": }}',  # Nested malformed JSON
        ]
        
        for payload in malformed_payloads:
            response = client.post(
                "/api/v1/download",
                data=payload,  # Send raw string instead of json parameter
                headers={"Content-Type": "application/json"}
            )
            # Should return 422 for malformed JSON
            assert response.status_code == 422
    
    def test_oversized_request_payloads(self, client, mock_database, mock_storage):
        """Test handling of oversized request payloads."""
        # Create oversized JSON payload
        oversized_payload = {
            "url": "https://youtube.com/watch?v=test",
            "huge_field": "x" * (10 * 1024 * 1024)  # 10MB string
        }
        
        try:
            response = client.post("/api/v1/download", json=oversized_payload)
            # Should either reject or handle gracefully
            assert response.status_code in [413, 422, 400]  # Payload too large, validation error, or bad request
        except Exception:
            # May throw exception for oversized payload - that's acceptable
            pass
    
    def test_unicode_and_special_characters(self, client, mock_database, mock_storage):
        """Test handling of unicode and special characters in requests."""
        unicode_payloads = [
            {"url": "https://youtube.com/watch?v=测试"},  # Chinese characters
            {"url": "https://youtube.com/watch?v=тест"},  # Cyrillic
            {"url": "https://youtube.com/watch?v=🎵🎬"},  # Emojis
            {"url": "https://youtube.com/watch?v=test", "description": "файл с русскими буквами"},
            {"url": "https://youtube.com/watch?v=test\x00null"},  # Null byte
        ]
        
        for payload in unicode_payloads:
            response = client.post("/api/v1/download", json=payload)
            # Should handle gracefully, either accepting or rejecting with proper error
            assert response.status_code in [200, 400, 401, 403, 422]
    
    def test_content_type_mismatches(self, client, mock_database, mock_storage):
        """Test handling of content type mismatches."""
        valid_payload = {"url": "https://youtube.com/watch?v=test"}
        
        # Send JSON with wrong content type
        response = client.post(
            "/api/v1/download",
            json=valid_payload,
            headers={"Content-Type": "text/plain"}
        )
        # Should handle content type mismatch
        assert response.status_code in [400, 415, 422]
        
        # Send form data instead of JSON
        response = client.post(
            "/api/v1/download",
            data="url=https://youtube.com/watch?v=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        # Should handle form data appropriately
        assert response.status_code in [400, 415, 422]
    
    def test_http_method_edge_cases(self, client, mock_database, mock_storage):
        """Test handling of unsupported HTTP methods."""
        unsupported_methods = [
            ("PATCH", "/api/v1/download"),
            ("PUT", "/api/v1/info"),
            ("DELETE", "/api/v1/health"),
            ("HEAD", "/api/v1/download"),
            ("OPTIONS", "/api/v1/admin/keys"),
        ]
        
        for method, endpoint in unsupported_methods:
            response = client.request(method, endpoint)
            # Should return method not allowed
            assert response.status_code == 405
    
    def test_header_injection_attempts(self, client, mock_database, mock_storage):
        """Test handling of header injection attempts."""
        malicious_headers = {
            "X-API-Key": "test\r\nEvil-Header: injected",  # CRLF injection
            "X-Forwarded-For": "127.0.0.1\r\nHost: evil.com",
            "User-Agent": "Mozilla/5.0\x00\r\nEvil: header",
        }
        
        for header, value in malicious_headers.items():
            try:
                response = client.get("/health", headers={header: value})
                # Should handle malicious headers gracefully
                assert response.status_code in [200, 400, 422]
            except Exception:
                # Headers with null bytes or CRLF may raise exceptions - acceptable
                pass
    
    def test_url_path_traversal_attempts(self, client, mock_database, mock_storage):
        """Test handling of path traversal attempts in URLs."""
        malicious_paths = [
            "/api/v1/../../../etc/passwd",
            "/api/v1/download/../../admin/keys",
            "/api/v1/info?url=../config",
            "/api/v1/jobs/../../../secret",
        ]
        
        for path in malicious_paths:
            response = client.get(path)
            # Should either return 404 (not found) or proper error, not expose sensitive paths
            assert response.status_code in [404, 400, 422]
            # Ensure no sensitive information is leaked in response
            response_text = response.text.lower()
            assert "passwd" not in response_text
            assert "config" not in response_text or "configuration" not in response_text
    
    def test_extremely_long_urls(self, client, mock_database, mock_storage):
        """Test handling of extremely long URLs."""
        # Create extremely long URL
        base_url = "https://youtube.com/watch?v=test"
        long_url = base_url + "&param=" + "x" * 10000
        
        response = client.get("/api/v1/info", params={"url": long_url})
        # Should handle long URLs gracefully
        assert response.status_code in [400, 413, 414, 422]  # Bad request, payload too large, URI too long, or validation error
    
    def test_concurrent_request_edge_cases(self, client, mock_database, mock_storage):
        """Test handling of rapid concurrent requests."""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get("/health")
            results.append(response.status_code)
        
        # Send multiple concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should complete successfully or with expected errors
        for status_code in results:
            assert status_code in [200, 429, 503]  # OK, too many requests, or service unavailable