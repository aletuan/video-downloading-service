from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import validator, Field
from typing import Optional
import secrets
import os
import logging


class Settings(BaseSettings):
    """Base settings class for the YouTube Download Service."""
    
    # Environment
    environment: str = "localhost"
    debug: bool = True
    
    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Storage
    download_base_path: str = "./downloads"
    max_file_size_gb: int = 5
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./youtube_service.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Processing
    max_concurrent_downloads: int = 3
    download_timeout: int = 3600
    
    # YouTube
    yt_dlp_update_check: bool = False
    extract_flat: bool = False
    
    # Security
    secret_key: str = "your-secret-key-here-change-in-production"
    api_key_header: str = "X-API-Key"
    
    # Bootstrap/Setup
    bootstrap_setup_token: Optional[str] = None
    
    # Cookie Management
    cookie_s3_bucket: Optional[str] = None
    cookie_encryption_key: Optional[str] = None
    cookie_refresh_interval: int = 60  # minutes
    cookie_validation_enabled: bool = True
    cookie_backup_count: int = 3
    cookie_temp_dir: Optional[str] = None
    cookie_expiration_warning_days: int = 7
    cookie_rotation_schedule_days: int = 30
    cookie_rate_limit_window: int = 60  # seconds
    cookie_rate_limit_requests: int = 10
    cookie_integrity_checks_enabled: bool = True
    cookie_cache_ttl_minutes: int = 60
    cookie_alert_threshold: int = 5  # consecutive failures
    cookie_backoff_initial_delay: float = 1.0  # seconds
    cookie_backoff_max_delay: float = 300.0  # seconds
    cookie_backoff_factor: float = 2.0
    cookie_debug_logging: bool = False
    
    @validator('cookie_encryption_key')
    def validate_cookie_encryption_key(cls, v):
        """Validate encryption key configuration."""
        if v is not None and len(v) < 32:
            raise ValueError('Cookie encryption key must be at least 32 characters long')
        return v
    
    @validator('cookie_refresh_interval')
    def validate_cookie_refresh_interval(cls, v):
        """Validate cookie refresh interval."""
        if v < 5:
            raise ValueError('Cookie refresh interval must be at least 5 minutes')
        if v > 1440:  # 24 hours
            raise ValueError('Cookie refresh interval should not exceed 24 hours')
        return v
    
    @validator('cookie_expiration_warning_days')
    def validate_cookie_expiration_warning_days(cls, v):
        """Validate cookie expiration warning threshold."""
        if v < 1:
            raise ValueError('Cookie expiration warning days must be at least 1')
        if v > 90:
            raise ValueError('Cookie expiration warning days should not exceed 90')
        return v
    
    @validator('cookie_rate_limit_requests')
    def validate_cookie_rate_limit(cls, v):
        """Validate cookie rate limit configuration."""
        if v < 1:
            raise ValueError('Cookie rate limit requests must be at least 1')
        if v > 100:
            raise ValueError('Cookie rate limit requests should not exceed 100')
        return v
    
    @validator('cookie_backoff_factor')
    def validate_backoff_factor(cls, v):
        """Validate exponential backoff factor."""
        if v < 1.1:
            raise ValueError('Cookie backoff factor must be at least 1.1')
        if v > 10.0:
            raise ValueError('Cookie backoff factor should not exceed 10.0')
        return v
    
    def validate_cookie_configuration(self) -> dict:
        """
        Validate cookie management configuration and return validation results.
        
        Returns:
            dict: Validation results with warnings and errors
        """
        validation_results = {
            'valid': True,
            'warnings': [],
            'errors': [],
            'recommendations': []
        }
        
        # Check required settings for cookie functionality
        if self.cookie_s3_bucket is None:
            validation_results['warnings'].append(
                'cookie_s3_bucket not configured - cookie authentication will be disabled'
            )
        
        if self.cookie_encryption_key is None:
            validation_results['warnings'].append(
                'cookie_encryption_key not configured - using auto-generated key (not persistent)'
            )
        
        # Check for insecure configurations
        if self.cookie_debug_logging and not self.debug:
            validation_results['warnings'].append(
                'cookie_debug_logging enabled in non-debug mode - may expose sensitive data'
            )
        
        # Performance recommendations
        if self.cookie_cache_ttl_minutes > 240:  # 4 hours
            validation_results['recommendations'].append(
                'Consider reducing cookie_cache_ttl_minutes for better security'
            )
        
        if self.cookie_rate_limit_requests > 20:
            validation_results['recommendations'].append(
                'High cookie rate limit may impact security - consider reducing'
            )
        
        # Environment-specific checks
        if self.environment == 'aws':
            if self.cookie_s3_bucket is None:
                validation_results['errors'].append(
                    'cookie_s3_bucket is required for AWS environment'
                )
                validation_results['valid'] = False
            
            if self.cookie_debug_logging:
                validation_results['warnings'].append(
                    'cookie_debug_logging should be disabled in AWS environment'
                )
        
        return validation_results
    
    model_config = SettingsConfigDict(env_file=".env")


class AWSSettings(Settings):
    """AWS-specific settings."""
    
    environment: str = "aws"
    debug: bool = False
    
    # AWS Services
    aws_region: str = "us-east-1"
    s3_bucket_name: Optional[str] = None
    s3_cloudfront_domain: Optional[str] = None
    
    # Database (RDS)
    database_url: str  # Must be provided via environment
    
    # Redis (ElastiCache)
    redis_url: str  # Must be provided via environment
    
    # Celery with SQS
    broker_url: Optional[str] = None  # SQS broker URL
    result_backend: Optional[str] = None  # Redis or RDS for results
    
    # Monitoring
    cloudwatch_log_group: str = "/aws/ecs/youtube-service"
    enable_xray: bool = True
    
    # Cookie Management (AWS-specific overrides)
    cookie_s3_bucket: Optional[str] = None  # Must be provided via environment
    cookie_encryption_key: Optional[str] = None  # Should use AWS Parameter Store/Secrets Manager
    cookie_validation_enabled: bool = True
    cookie_integrity_checks_enabled: bool = True
    cookie_debug_logging: bool = False  # Disable debug logging in production
    cookie_cache_ttl_minutes: int = 30  # Shorter TTL in production
    cookie_alert_threshold: int = 3  # More sensitive alerting in production


def get_settings() -> Settings:
    """Get settings based on environment."""
    import os
    
    environment = os.getenv("ENVIRONMENT", "localhost")
    
    if environment == "aws":
        return AWSSettings()
    else:
        return Settings()


def validate_and_log_configuration(settings: Settings, logger: Optional[logging.Logger] = None) -> bool:
    """
    Validate configuration and log results.
    
    Args:
        settings: Settings instance to validate
        logger: Logger instance for output
        
    Returns:
        bool: True if configuration is valid
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    validation_results = settings.validate_cookie_configuration()
    
    # Log validation results
    if validation_results['valid']:
        logger.info("Cookie configuration validation passed")
    else:
        logger.error("Cookie configuration validation failed")
        for error in validation_results['errors']:
            logger.error(f"Configuration error: {error}")
    
    # Log warnings
    for warning in validation_results['warnings']:
        logger.warning(f"Configuration warning: {warning}")
    
    # Log recommendations
    for recommendation in validation_results['recommendations']:
        logger.info(f"Configuration recommendation: {recommendation}")
    
    # Log cookie configuration summary (without sensitive data)
    cookie_config_summary = {
        'cookies_enabled': settings.cookie_s3_bucket is not None,
        'validation_enabled': settings.cookie_validation_enabled,
        'integrity_checks_enabled': settings.cookie_integrity_checks_enabled,
        'refresh_interval_minutes': settings.cookie_refresh_interval,
        'cache_ttl_minutes': settings.cookie_cache_ttl_minutes,
        'rate_limit_requests': settings.cookie_rate_limit_requests,
        'rate_limit_window_seconds': settings.cookie_rate_limit_window,
        'alert_threshold': settings.cookie_alert_threshold,
        'debug_logging': settings.cookie_debug_logging
    }
    
    if settings.cookie_debug_logging:
        logger.debug(f"Cookie configuration: {cookie_config_summary}")
    else:
        logger.info(f"Cookie configuration initialized: {cookie_config_summary}")
    
    return validation_results['valid']


def get_environment_variable_documentation() -> dict:
    """
    Get documentation for all cookie-related environment variables.
    
    Returns:
        dict: Environment variable documentation
    """
    return {
        'COOKIE_S3_BUCKET': {
            'description': 'S3 bucket name for storing secure cookie files',
            'required': True,
            'aws_required': True,
            'example': 'my-service-secure-config'
        },
        'COOKIE_ENCRYPTION_KEY': {
            'description': 'Base64 encryption key for in-memory cookie encryption (min 32 chars)',
            'required': False,
            'aws_required': True,
            'example': 'your-32-character-base64-key-here',
            'security': 'Store in AWS Parameter Store/Secrets Manager'
        },
        'COOKIE_REFRESH_INTERVAL': {
            'description': 'Cookie cache refresh interval in minutes',
            'required': False,
            'default': 60,
            'range': '5-1440'
        },
        'COOKIE_VALIDATION_ENABLED': {
            'description': 'Enable cookie validation and freshness checks',
            'required': False,
            'default': True,
            'type': 'boolean'
        },
        'COOKIE_BACKUP_COUNT': {
            'description': 'Number of backup cookie files to maintain',
            'required': False,
            'default': 3,
            'range': '1-10'
        },
        'COOKIE_TEMP_DIR': {
            'description': 'Directory for temporary cookie files',
            'required': False,
            'default': 'system temp directory',
            'example': '/tmp/cookie-temp'
        },
        'COOKIE_EXPIRATION_WARNING_DAYS': {
            'description': 'Days before expiration to show warnings',
            'required': False,
            'default': 7,
            'range': '1-90'
        },
        'COOKIE_ROTATION_SCHEDULE_DAYS': {
            'description': 'Scheduled cookie rotation interval in days',
            'required': False,
            'default': 30,
            'range': '7-365'
        },
        'COOKIE_RATE_LIMIT_WINDOW': {
            'description': 'Rate limiting window in seconds',
            'required': False,
            'default': 60,
            'range': '30-3600'
        },
        'COOKIE_RATE_LIMIT_REQUESTS': {
            'description': 'Maximum requests per rate limit window',
            'required': False,
            'default': 10,
            'range': '1-100'
        },
        'COOKIE_INTEGRITY_CHECKS_ENABLED': {
            'description': 'Enable cookie file integrity validation',
            'required': False,
            'default': True,
            'type': 'boolean'
        },
        'COOKIE_CACHE_TTL_MINUTES': {
            'description': 'In-memory cookie cache TTL in minutes',
            'required': False,
            'default': 60,
            'range': '5-240'
        },
        'COOKIE_ALERT_THRESHOLD': {
            'description': 'Consecutive failures before sending alerts',
            'required': False,
            'default': 5,
            'range': '1-50'
        },
        'COOKIE_BACKOFF_INITIAL_DELAY': {
            'description': 'Initial delay for exponential backoff in seconds',
            'required': False,
            'default': 1.0,
            'range': '0.1-10.0'
        },
        'COOKIE_BACKOFF_MAX_DELAY': {
            'description': 'Maximum delay for exponential backoff in seconds',
            'required': False,
            'default': 300.0,
            'range': '10.0-3600.0'
        },
        'COOKIE_BACKOFF_FACTOR': {
            'description': 'Exponential backoff multiplication factor',
            'required': False,
            'default': 2.0,
            'range': '1.1-10.0'
        },
        'COOKIE_DEBUG_LOGGING': {
            'description': 'Enable detailed cookie debug logging (SECURITY RISK)',
            'required': False,
            'default': False,
            'type': 'boolean',
            'security': 'Should be False in production'
        }
    }


# Global settings instance
settings = get_settings()

# Validate configuration on import
logger = logging.getLogger(__name__)
try:
    config_valid = validate_and_log_configuration(settings, logger)
    if not config_valid:
        logger.warning("Configuration validation failed - some features may not work correctly")
except Exception as e:
    logger.error(f"Configuration validation error: {e}")
    # Don't fail startup on validation errors, but log them