"""
Pytest configuration and shared fixtures for the test suite.

This module provides common fixtures, test configuration, and utilities
used across all test modules.
"""

import pytest
import asyncio
import os
import tempfile
import shutil
from unittest.mock import patch, Mock
from pathlib import Path


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_aws_credentials():
    """Mock AWS credentials for testing."""
    with patch.dict(os.environ, {
        'AWS_ACCESS_KEY_ID': 'testing',
        'AWS_SECRET_ACCESS_KEY': 'testing',
        'AWS_SECURITY_TOKEN': 'testing',
        'AWS_SESSION_TOKEN': 'testing',
        'AWS_DEFAULT_REGION': 'us-east-1'
    }):
        yield


@pytest.fixture
def sample_netscape_cookies():
    """Sample Netscape format cookie data."""
    return """# Netscape HTTP Cookie File
# This is a generated file!  Do not edit.

.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123def456
.google.com	TRUE	/	FALSE	1735689600	AUTH_TOKEN	xyz789uvw012
.googleapis.com	TRUE	/api	FALSE	1735689600	API_KEY	qwe345rty678
"""


@pytest.fixture
def sample_json_cookies():
    """Sample JSON format cookie data."""
    return [
        {
            "domain": ".youtube.com",
            "name": "VISITOR_INFO1_LIVE",
            "value": "abc123def456",
            "path": "/",
            "expires": 1735689600,
            "secure": False,
            "httpOnly": True
        },
        {
            "domain": ".google.com",
            "name": "AUTH_TOKEN",
            "value": "xyz789uvw012",
            "path": "/",
            "expires": 1735689600,
            "secure": True,
            "httpOnly": False
        }
    ]


@pytest.fixture
def mock_cookie_settings():
    """Mock cookie settings for testing."""
    with patch('app.core.cookie_manager.settings') as mock_settings:
        mock_settings.cookie_s3_bucket = "test-cookie-bucket"
        mock_settings.cookie_encryption_key = "test-key-1234567890123456789012345678"
        mock_settings.cookie_refresh_interval = 3600
        mock_settings.cookie_validation_enabled = True
        mock_settings.cookie_backup_count = 3
        mock_settings.cookie_temp_dir = None  # Use system temp directory
        mock_settings.aws_region = "us-east-1"
        yield mock_settings


@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing."""
    mock_client = Mock()
    mock_client.get_object.return_value = {
        'Body': Mock(read=Mock(return_value=b'test data')),
        'ServerSideEncryption': 'AES256'
    }
    mock_client.put_object.return_value = {
        'ETag': '"test-etag"',
        'ServerSideEncryption': 'AES256'
    }
    mock_client.list_objects_v2.return_value = {
        'Contents': [
            {'Key': 'cookies/test.txt', 'Size': 100}
        ]
    }
    return mock_client


@pytest.fixture
def encryption_key():
    """Standard encryption key for testing."""
    return "test-key-1234567890123456789012345678"


# Configure pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may be skipped in quick runs)"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )


# Skip slow tests by default unless --runslow is given
def pytest_collection_modifyitems(config, items):
    """Modify test collection to handle slow tests."""
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )