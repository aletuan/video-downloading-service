from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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


def get_settings() -> Settings:
    """Get settings based on environment."""
    import os
    
    environment = os.getenv("ENVIRONMENT", "localhost")
    
    if environment == "aws":
        return AWSSettings()
    else:
        return Settings()


# Global settings instance
settings = get_settings()