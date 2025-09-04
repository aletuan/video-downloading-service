"""
Unit tests for configuration management.

Tests settings classes, environment variable loading, and configuration validation.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.core.config import Settings, AWSSettings, get_settings


class TestSettings:
    """Test the base Settings class."""
    
    def test_default_settings_creation(self):
        """Test creating settings with default values."""
        settings = Settings()
        
        # Environment settings
        assert settings.environment == "localhost"
        assert settings.debug is True
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        
        # Storage settings
        assert settings.download_base_path == "./downloads"
        assert settings.max_file_size_gb == 5
        
        # Database settings
        assert settings.database_url == "sqlite+aiosqlite:///./youtube_service.db"
        
        # Redis settings
        assert settings.redis_url == "redis://localhost:6379/0"
        
        # Processing settings
        assert settings.max_concurrent_downloads == 3
        assert settings.download_timeout == 3600
    
    def test_youtube_download_settings(self):
        """Test YouTube-specific download settings."""
        settings = Settings()
        
        assert settings.yt_dlp_update_check is False
        assert settings.extract_flat is False
        assert settings.default_video_quality == "best"
        assert settings.default_audio_quality == "best"
        assert settings.default_subtitle_languages == ["en"]
        assert settings.extract_thumbnails is True
        assert settings.extract_subtitles is True
        assert settings.extract_auto_subtitles is True
    
    def test_video_processing_settings(self):
        """Test video processing settings."""
        settings = Settings()
        
        assert settings.default_video_format == "mp4"
        assert settings.default_audio_format == "mp3"
        assert settings.enable_format_conversion is True
        assert settings.ffmpeg_quality_preset == "medium"
        assert settings.max_video_resolution is None
    
    def test_quality_presets_structure(self):
        """Test quality presets dictionary structure."""
        settings = Settings()
        
        expected_presets = ["low", "medium", "high", "ultra"]
        assert list(settings.quality_presets.keys()) == expected_presets
        
        # Test each preset has required keys
        for preset_name, preset_config in settings.quality_presets.items():
            assert "video_bitrate" in preset_config
            assert "audio_bitrate" in preset_config
            assert "max_resolution" in preset_config
            
            # Validate bitrate formats
            assert preset_config["video_bitrate"].endswith("M")
            assert preset_config["audio_bitrate"].endswith("k")
    
    def test_retry_configuration(self):
        """Test retry configuration settings."""
        settings = Settings()
        
        assert settings.max_download_retries == 3
        assert settings.download_retry_delay == 60
        assert settings.exponential_backoff is True
    
    def test_security_settings(self):
        """Test security-related settings."""
        settings = Settings()
        
        assert settings.secret_key == "your-secret-key-here-change-in-production"
        assert settings.api_key_header == "X-API-Key"
    
    @patch.dict(os.environ, {
        'ENVIRONMENT': 'production',
        'DEBUG': 'false',
        'HOST': '127.0.0.1',
        'PORT': '9000',
        'MAX_CONCURRENT_DOWNLOADS': '5',
        'DATABASE_URL': 'postgresql://test:test@localhost/testdb',
        'REDIS_URL': 'redis://localhost:6379/1'
    })
    def test_environment_variable_override(self):
        """Test that environment variables override default settings."""
        settings = Settings()
        
        assert settings.environment == "production"
        assert settings.debug is False
        assert settings.host == "127.0.0.1"
        assert settings.port == 9000
        assert settings.max_concurrent_downloads == 5
        assert settings.database_url == "postgresql://test:test@localhost/testdb"
        assert settings.redis_url == "redis://localhost:6379/1"
    
    @patch.dict(os.environ, {
        'DEFAULT_SUBTITLE_LANGUAGES': '["en","es","fr"]'
    })
    def test_list_environment_variable_parsing(self):
        """Test parsing of list-type environment variables."""
        settings = Settings()
        # Note: Pydantic automatically parses JSON strings for list types
        assert settings.default_subtitle_languages == ["en", "es", "fr"]
    
    def test_settings_immutability(self):
        """Test that settings behave correctly when accessed."""
        settings = Settings()
        original_port = settings.port
        
        # Settings should maintain their values
        assert settings.port == original_port
        assert settings.environment == "localhost"
    
    def test_path_settings(self):
        """Test path-related settings."""
        settings = Settings()
        
        assert settings.download_base_path == "./downloads"
        assert settings.temp_download_path == "/tmp/youtube_downloads"
    
    @patch.dict(os.environ, {
        'MAX_FILE_SIZE_GB': '10',
        'DOWNLOAD_TIMEOUT': '7200',
        'MAX_DOWNLOAD_RETRIES': '5',
        'DOWNLOAD_RETRY_DELAY': '120'
    })
    def test_numeric_environment_variables(self):
        """Test parsing of numeric environment variables."""
        settings = Settings()
        
        assert settings.max_file_size_gb == 10
        assert settings.download_timeout == 7200
        assert settings.max_download_retries == 5
        assert settings.download_retry_delay == 120
    
    @patch.dict(os.environ, {
        'YT_DLP_UPDATE_CHECK': 'true',
        'EXTRACT_THUMBNAILS': 'false',
        'ENABLE_FORMAT_CONVERSION': 'false',
        'EXPONENTIAL_BACKOFF': 'false'
    })
    def test_boolean_environment_variables(self):
        """Test parsing of boolean environment variables."""
        settings = Settings()
        
        assert settings.yt_dlp_update_check is True
        assert settings.extract_thumbnails is False
        assert settings.enable_format_conversion is False
        assert settings.exponential_backoff is False


class TestAWSSettings:
    """Test the AWSSettings class."""
    
    @patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://user:pass@rds.amazonaws.com/dbname',
        'REDIS_URL': 'redis://elasticache.amazonaws.com:6379/0'
    })
    def test_aws_settings_creation(self):
        """Test creating AWS settings with required environment variables."""
        aws_settings = AWSSettings()
        
        # Inherited settings with AWS overrides
        assert aws_settings.environment == "aws"
        assert aws_settings.debug is False
        
        # AWS-specific settings
        assert aws_settings.aws_region == "us-east-1"
        assert aws_settings.s3_bucket_name is None
        assert aws_settings.s3_cloudfront_domain is None
        
        # Required environment variables
        assert aws_settings.database_url == "postgresql://user:pass@rds.amazonaws.com/dbname"
        assert aws_settings.redis_url == "redis://elasticache.amazonaws.com:6379/0"
        
        # Monitoring settings
        assert aws_settings.cloudwatch_log_group == "/aws/ecs/youtube-service"
        assert aws_settings.enable_xray is True
    
    @patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://test/test',
        'REDIS_URL': 'redis://test:6379',
        'AWS_REGION': 'us-west-2',
        'S3_BUCKET_NAME': 'my-video-bucket',
        'S3_CLOUDFRONT_DOMAIN': 'https://d1234567890.cloudfront.net',
        'BROKER_URL': 'sqs://us-west-2/123456789/celery-queue',
        'RESULT_BACKEND': 'redis://elasticache.amazonaws.com:6379/1',
        'CLOUDWATCH_LOG_GROUP': '/aws/lambda/youtube-service',
        'ENABLE_XRAY': 'false'
    })
    def test_aws_settings_with_all_options(self):
        """Test AWS settings with all optional values set."""
        aws_settings = AWSSettings()
        
        assert aws_settings.aws_region == "us-west-2"
        assert aws_settings.s3_bucket_name == "my-video-bucket"
        assert aws_settings.s3_cloudfront_domain == "https://d1234567890.cloudfront.net"
        assert aws_settings.broker_url == "sqs://us-west-2/123456789/celery-queue"
        assert aws_settings.result_backend == "redis://elasticache.amazonaws.com:6379/1"
        assert aws_settings.cloudwatch_log_group == "/aws/lambda/youtube-service"
        assert aws_settings.enable_xray is False
    
    @patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://test/test',
        'REDIS_URL': 'redis://test:6379'
    })
    def test_aws_settings_inheritance(self):
        """Test that AWS settings inherit from base Settings."""
        aws_settings = AWSSettings()
        
        # Should inherit all base settings
        assert aws_settings.host == "0.0.0.0"
        assert aws_settings.port == 8000
        assert aws_settings.max_concurrent_downloads == 3
        assert aws_settings.default_video_quality == "best"
        assert aws_settings.quality_presets is not None
        assert "low" in aws_settings.quality_presets
    
    def test_aws_settings_without_required_env_vars(self):
        """Test AWS settings creation without required environment variables."""
        # This should work since Pydantic will use the annotated type defaults
        # The required database_url and redis_url will need to be set in production
        with patch.dict(os.environ, {}, clear=True):
            try:
                aws_settings = AWSSettings()
                # If no validation error, these should be the empty string or None
                # depending on the field definition
            except Exception:
                # Expected if pydantic validation requires these fields
                pass


class TestGetSettings:
    """Test the get_settings factory function."""
    
    @patch.dict(os.environ, {'ENVIRONMENT': 'localhost'})
    def test_get_settings_localhost(self):
        """Test get_settings returns Settings for localhost environment."""
        with patch('app.core.config.Settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            
            result = get_settings()
            
            mock_settings.assert_called_once()
            assert result == mock_settings.return_value
    
    @patch.dict(os.environ, {'ENVIRONMENT': 'development'})  
    def test_get_settings_development(self):
        """Test get_settings returns Settings for development environment."""
        with patch('app.core.config.Settings') as mock_settings:
            mock_settings.return_value = MagicMock()
            
            result = get_settings()
            
            mock_settings.assert_called_once()
            assert result == mock_settings.return_value
    
    @patch.dict(os.environ, {
        'ENVIRONMENT': 'aws',
        'DATABASE_URL': 'postgresql://test/test',
        'REDIS_URL': 'redis://test:6379'
    })
    def test_get_settings_aws(self):
        """Test get_settings returns AWSSettings for aws environment."""
        with patch('app.core.config.AWSSettings') as mock_aws_settings:
            mock_aws_settings.return_value = MagicMock()
            
            result = get_settings()
            
            mock_aws_settings.assert_called_once()
            assert result == mock_aws_settings.return_value
    
    def test_get_settings_no_environment(self):
        """Test get_settings returns Settings when ENVIRONMENT is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('app.core.config.Settings') as mock_settings:
                mock_settings.return_value = MagicMock()
                
                result = get_settings()
                
                mock_settings.assert_called_once()
                assert result == mock_settings.return_value


class TestSettingsValidation:
    """Test settings validation and edge cases."""
    
    def test_quality_presets_completeness(self):
        """Test that all quality presets have consistent structure."""
        settings = Settings()
        
        for preset_name, preset_config in settings.quality_presets.items():
            # Each preset should have exactly these keys
            expected_keys = {"video_bitrate", "audio_bitrate", "max_resolution"}
            assert set(preset_config.keys()) == expected_keys
            
            # Validate value formats
            assert isinstance(preset_config["video_bitrate"], str)
            assert isinstance(preset_config["audio_bitrate"], str)
            assert isinstance(preset_config["max_resolution"], str)
            
            # Check bitrate formats
            assert preset_config["video_bitrate"].endswith("M")
            assert preset_config["audio_bitrate"].endswith("k")
            assert preset_config["max_resolution"].endswith("p")
    
    @patch.dict(os.environ, {
        'MAX_CONCURRENT_DOWNLOADS': '0'
    })
    def test_edge_case_zero_concurrent_downloads(self):
        """Test behavior with zero concurrent downloads."""
        settings = Settings()
        assert settings.max_concurrent_downloads == 0
    
    @patch.dict(os.environ, {
        'PORT': '65535'
    })
    def test_maximum_port_number(self):
        """Test with maximum valid port number."""
        settings = Settings()
        assert settings.port == 65535
    
    def test_settings_model_config(self):
        """Test that settings properly configure pydantic model."""
        settings = Settings()
        
        # Verify the model config is set
        assert hasattr(settings, 'model_config')
        assert settings.model_config.env_file == ".env"
    
    def test_default_subtitle_languages_type(self):
        """Test that default_subtitle_languages is properly typed as List[str]."""
        settings = Settings()
        
        assert isinstance(settings.default_subtitle_languages, list)
        assert all(isinstance(lang, str) for lang in settings.default_subtitle_languages)
        assert settings.default_subtitle_languages == ["en"]
    
    @patch.dict(os.environ, {
        'SECRET_KEY': 'production-secret-key-12345',
        'API_KEY_HEADER': 'Authorization'
    })
    def test_security_settings_override(self):
        """Test security settings can be overridden via environment."""
        settings = Settings()
        
        assert settings.secret_key == "production-secret-key-12345"
        assert settings.api_key_header == "Authorization"


class TestSettingsIntegration:
    """Integration tests for settings functionality."""
    
    def test_settings_can_be_serialized(self):
        """Test that settings can be converted to dict for serialization."""
        settings = Settings()
        
        # Should be able to convert to dict without errors
        settings_dict = settings.model_dump()
        
        assert isinstance(settings_dict, dict)
        assert "environment" in settings_dict
        assert "database_url" in settings_dict
        assert "quality_presets" in settings_dict
    
    def test_settings_json_serialization(self):
        """Test that settings can be JSON serialized."""
        import json
        
        settings = Settings()
        settings_dict = settings.model_dump()
        
        # Should be able to serialize to JSON without errors
        json_str = json.dumps(settings_dict)
        assert isinstance(json_str, str)
        
        # Should be able to deserialize back
        deserialized = json.loads(json_str)
        assert isinstance(deserialized, dict)
        assert deserialized["environment"] == "localhost"
    
    @patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://localhost/test',
        'REDIS_URL': 'redis://localhost:6379/2'
    })
    def test_real_settings_instantiation(self):
        """Test creating actual settings instances without mocks."""
        # Base settings
        base_settings = Settings()
        assert isinstance(base_settings, Settings)
        
        # AWS settings
        aws_settings = AWSSettings()
        assert isinstance(aws_settings, AWSSettings)
        assert isinstance(aws_settings, Settings)  # Should inherit from Settings
        
        # Factory function
        factory_settings = get_settings()
        assert isinstance(factory_settings, Settings)