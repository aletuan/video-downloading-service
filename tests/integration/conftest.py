"""
Shared fixtures for integration tests.

Provides common test fixtures for FastAPI endpoint testing including
mocked database, storage, and authentication components.
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