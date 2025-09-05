import os
import pytest
from unittest.mock import patch

from app.core.config import Settings, AWSSettings, get_settings


class TestSettings:
    """Test cases for Settings class."""

    def test_default_settings(self):
        """Test that default settings are correctly set."""
        settings = Settings()
        
        assert settings.environment == "localhost"
        assert settings.debug is True
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.download_base_path == "./downloads"
        assert settings.max_file_size_gb == 5
        assert settings.database_url == "sqlite+aiosqlite:///./youtube_service.db"
        assert settings.redis_url == "redis://localhost:6379/0"
        assert settings.max_concurrent_downloads == 3
        assert settings.download_timeout == 3600
        assert settings.yt_dlp_update_check is False
        assert settings.extract_flat is False
        assert settings.secret_key == "your-secret-key-here-change-in-production"
        assert settings.api_key_header == "X-API-Key"

    def test_custom_settings(self):
        """Test that custom settings override defaults."""
        settings = Settings(
            environment="production",
            debug=False,
            port=9000,
            max_file_size_gb=10
        )
        
        assert settings.environment == "production"
        assert settings.debug is False
        assert settings.port == 9000
        assert settings.max_file_size_gb == 10


class TestAWSSettings:
    """Test cases for AWSSettings class."""

    def test_aws_settings_defaults(self):
        """Test that AWS settings have correct defaults."""
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "REDIS_URL": "redis://aws-redis:6379/0"
        }):
            settings = AWSSettings()
            
            assert settings.environment == "aws"
            assert settings.debug is False
            assert settings.aws_region == "us-east-1"
            assert settings.s3_bucket_name is None
            assert settings.s3_cloudfront_domain is None
            assert settings.cloudwatch_log_group == "/aws/ecs/youtube-service"
            assert settings.enable_xray is True

    def test_aws_settings_with_values(self):
        """Test AWS settings with provided values."""
        settings = AWSSettings(
            database_url="postgresql://aws:password@rds:5432/youtube",
            redis_url="redis://elasticache:6379/0",
            s3_bucket_name="my-bucket",
            s3_cloudfront_domain="d123456.cloudfront.net",
            aws_region="us-west-2"
        )
        
        assert settings.database_url == "postgresql://aws:password@rds:5432/youtube"
        assert settings.redis_url == "redis://elasticache:6379/0"
        assert settings.s3_bucket_name == "my-bucket"
        assert settings.s3_cloudfront_domain == "d123456.cloudfront.net"
        assert settings.aws_region == "us-west-2"


class TestGetSettings:
    """Test cases for get_settings function."""

    def test_get_settings_localhost(self):
        """Test that get_settings returns Settings for localhost environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "localhost"}):
            settings = get_settings()
            assert isinstance(settings, Settings)
            assert settings.environment == "localhost"

    def test_get_settings_aws(self):
        """Test that get_settings returns AWSSettings for aws environment."""
        with patch.dict(os.environ, {
            "ENVIRONMENT": "aws",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "REDIS_URL": "redis://test:6379/0"
        }):
            settings = get_settings()
            assert isinstance(settings, AWSSettings)
            assert settings.environment == "aws"

    def test_get_settings_default(self):
        """Test that get_settings returns Settings when no environment is set."""
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()
            assert isinstance(settings, Settings)
            assert settings.environment == "localhost"

    def test_get_settings_unknown_environment(self):
        """Test that get_settings returns Settings for unknown environments."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            settings = get_settings()
            assert isinstance(settings, Settings)
            assert settings.environment == "production"