from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, HttpUrl, validator
from enum import Enum
import uuid


class DownloadStatus(str, Enum):
    """Download job status enumeration."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoQuality(str, Enum):
    """Video quality options."""
    BEST = "best"
    WORST = "worst"
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"
    P2160 = "2160p"  # 4K


class OutputFormat(str, Enum):
    """Supported output formats."""
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    MP3 = "mp3"  # Audio only
    M4A = "m4a"  # Audio only


class DownloadRequest(BaseModel):
    """Request model for initiating a download."""
    
    url: HttpUrl = Field(
        ...,
        description="YouTube video URL to download",
        example="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )
    
    quality: VideoQuality = Field(
        default=VideoQuality.BEST,
        description="Video quality preference"
    )
    
    output_format: OutputFormat = Field(
        default=OutputFormat.MP4,
        description="Output file format"
    )
    
    audio_only: bool = Field(
        default=False,
        description="Download audio only"
    )
    
    include_transcription: bool = Field(
        default=True,
        description="Extract subtitles and transcriptions"
    )
    
    subtitle_languages: List[str] = Field(
        default=["en"],
        description="List of subtitle languages to extract",
        example=["en", "es", "fr"]
    )
    
    @validator('url')
    def validate_youtube_url(cls, v):
        """Validate that the URL is from YouTube."""
        url_str = str(v)
        youtube_domains = [
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'youtu.be', 'www.youtu.be'
        ]
        
        if not any(domain in url_str for domain in youtube_domains):
            raise ValueError('URL must be from YouTube')
        
        return v
    
    @validator('subtitle_languages')
    def validate_subtitle_languages(cls, v):
        """Validate subtitle language codes."""
        if not v:
            return ["en"]
        
        # Basic validation for language codes (2-3 letter codes)
        for lang in v:
            if not isinstance(lang, str) or len(lang) < 2 or len(lang) > 5:
                raise ValueError(f'Invalid language code: {lang}')
        
        return v


class DownloadResponse(BaseModel):
    """Response model for download initiation."""
    
    job_id: str = Field(
        ...,
        description="Unique job identifier"
    )
    
    status: DownloadStatus = Field(
        ...,
        description="Current job status"
    )
    
    message: str = Field(
        ...,
        description="Status message",
        example="Download job queued successfully"
    )
    
    estimated_time: Optional[int] = Field(
        None,
        description="Estimated completion time in seconds"
    )


class VideoMetadata(BaseModel):
    """Video metadata extracted from YouTube."""
    
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    duration: Optional[int] = Field(None, description="Duration in seconds")
    upload_date: Optional[str] = None
    uploader: Optional[str] = None
    uploader_id: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    thumbnail: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    language: Optional[str] = None
    available_formats: Optional[int] = None
    has_subtitles: Optional[bool] = None
    available_subtitles: List[str] = Field(default_factory=list)
    automatic_captions: List[str] = Field(default_factory=list)


class JobProgress(BaseModel):
    """Progress information for a download job."""
    
    current: float = Field(
        ...,
        ge=0,
        le=100,
        description="Current progress percentage (0-100)"
    )
    
    total: float = Field(
        default=100,
        description="Total progress value (usually 100)"
    )
    
    status: str = Field(
        ...,
        description="Current status message"
    )
    
    eta: Optional[int] = Field(
        None,
        description="Estimated time to completion in seconds"
    )


class DownloadJobStatus(BaseModel):
    """Complete status information for a download job."""
    
    job_id: str = Field(
        ...,
        description="Unique job identifier"
    )
    
    url: str = Field(
        ...,
        description="Original video URL"
    )
    
    status: DownloadStatus = Field(
        ...,
        description="Current job status"
    )
    
    progress: JobProgress = Field(
        ...,
        description="Progress information"
    )
    
    metadata: Optional[VideoMetadata] = Field(
        None,
        description="Video metadata (available after processing starts)"
    )
    
    # File information (available after completion)
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    subtitle_paths: List[str] = Field(default_factory=list)
    
    # File metadata
    file_size: Optional[int] = Field(None, description="File size in bytes")
    file_size_formatted: Optional[str] = None
    duration_formatted: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(
        ...,
        description="Job creation timestamp"
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error information
    error_message: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)
    can_retry: bool = Field(default=False)


class DownloadJobList(BaseModel):
    """Response model for listing download jobs."""
    
    jobs: List[DownloadJobStatus] = Field(
        ...,
        description="List of download jobs"
    )
    
    total: int = Field(
        ...,
        ge=0,
        description="Total number of jobs"
    )
    
    page: int = Field(
        ...,
        ge=1,
        description="Current page number"
    )
    
    per_page: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of jobs per page"
    )
    
    total_pages: int = Field(
        ...,
        ge=1,
        description="Total number of pages"
    )


class VideoInfo(BaseModel):
    """Response model for video information extraction."""
    
    url: str = Field(
        ...,
        description="Video URL"
    )
    
    metadata: VideoMetadata = Field(
        ...,
        description="Extracted video metadata"
    )
    
    available_formats: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Available download formats"
    )
    
    recommended_quality: str = Field(
        default="720p",
        description="Recommended quality for download"
    )


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str = Field(
        ...,
        description="Error type"
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error details"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp"
    )


class HealthStatus(BaseModel):
    """Health check response model."""
    
    status: str = Field(
        ...,
        description="Overall health status"
    )
    
    environment: str = Field(
        ...,
        description="Current environment"
    )
    
    version: str = Field(
        ...,
        description="Application version"
    )
    
    timestamp: Optional[datetime] = None
    
    checks: Optional[Dict[str, Any]] = Field(
        None,
        description="Detailed health check results"
    )


# WebSocket message models
class WebSocketMessage(BaseModel):
    """Base WebSocket message model."""
    
    type: str = Field(
        ...,
        description="Message type"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Message timestamp"
    )


class ProgressMessage(WebSocketMessage):
    """WebSocket progress update message."""
    
    type: Literal["progress"] = Field(default="progress")
    job_id: str = Field(..., description="Job ID")
    progress: JobProgress = Field(..., description="Progress information")


class StatusMessage(WebSocketMessage):
    """WebSocket status update message."""
    
    type: Literal["status"] = Field(default="status")
    job_id: str = Field(..., description="Job ID")
    status: DownloadStatus = Field(..., description="New status")
    message: str = Field(..., description="Status message")


class ErrorMessage(WebSocketMessage):
    """WebSocket error message."""
    
    type: Literal["error"] = Field(default="error")
    job_id: Optional[str] = None
    error: str = Field(..., description="Error message")