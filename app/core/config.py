from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List


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
    
    # YouTube Download Settings
    yt_dlp_update_check: bool = False
    extract_flat: bool = False
    default_video_quality: str = "best"
    default_audio_quality: str = "best"
    default_subtitle_languages: List[str] = ["en"]
    extract_thumbnails: bool = True
    extract_subtitles: bool = True
    extract_auto_subtitles: bool = True
    
    # Download Paths
    temp_download_path: str = "/tmp/youtube_downloads"
    
    # Video Processing
    default_video_format: str = "mp4"
    default_audio_format: str = "mp3"
    enable_format_conversion: bool = True
    ffmpeg_quality_preset: str = "medium"  # ultrafast, fast, medium, slow, veryslow
    max_video_resolution: Optional[str] = None  # "720p", "1080p", "1440p", "2160p"
    
    # Quality Presets
    quality_presets: dict = {
        "low": {
            "video_bitrate": "1M",
            "audio_bitrate": "96k",
            "max_resolution": "720p"
        },
        "medium": {
            "video_bitrate": "2M", 
            "audio_bitrate": "128k",
            "max_resolution": "1080p"
        },
        "high": {
            "video_bitrate": "5M",
            "audio_bitrate": "320k",
            "max_resolution": "1440p"
        },
        "ultra": {
            "video_bitrate": "10M",
            "audio_bitrate": "320k",
            "max_resolution": "2160p"
        }
    }
    
    # Retry Configuration
    max_download_retries: int = 3
    download_retry_delay: int = 60  # seconds
    exponential_backoff: bool = True
    
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