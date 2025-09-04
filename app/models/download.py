"""
Download Models and Enums

Pydantic models and enums for download requests, responses, and configuration.
Used for API validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class VideoQuality(str, Enum):
    """Supported video quality options."""
    BEST = "best"
    WORST = "worst"
    ULTRA_HD = "2160p"  # 4K
    FULL_HD = "1080p"
    HD = "720p"
    SD = "480p"
    LOW = "360p"


class VideoFormat(str, Enum):
    """Supported video output formats."""
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    AVI = "avi"
    MOV = "mov"


class AudioFormat(str, Enum):
    """Supported audio output formats."""
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"
    FLAC = "flac"
    AAC = "aac"


class SubtitleFormat(str, Enum):
    """Supported subtitle formats."""
    SRT = "srt"
    VTT = "vtt"
    TXT = "txt"


class JobStatus(str, Enum):
    """Download job status values."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadRequest(BaseModel):
    """Request model for initiating a download."""
    
    url: str = Field(..., description="YouTube video URL to download")
    quality: VideoQuality = Field(VideoQuality.BEST, description="Video quality preference")
    include_transcription: bool = Field(True, description="Whether to download subtitles/captions")
    audio_only: bool = Field(False, description="Download audio only (no video)")
    output_format: VideoFormat = Field(VideoFormat.MP4, description="Output video format")
    subtitle_languages: List[str] = Field(["en"], description="Preferred subtitle languages")
    extract_thumbnail: bool = Field(True, description="Extract video thumbnail")
    
    @field_validator('url')
    @classmethod
    def validate_youtube_url(cls, v):
        """Validate that the URL is a YouTube URL."""
        if not v:
            raise ValueError("URL is required")
        
        # Basic YouTube URL validation
        youtube_domains = [
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'youtu.be', 'www.youtu.be'
        ]
        
        if not any(domain in v.lower() for domain in youtube_domains):
            raise ValueError("URL must be a valid YouTube URL")
        
        return v
    
    @field_validator('subtitle_languages')
    @classmethod
    def validate_subtitle_languages(cls, v):
        """Validate subtitle language codes."""
        if not v:
            return ["en"]
        
        # Basic language code validation (ISO 639-1)
        valid_codes = {
            'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh',
            'ar', 'hi', 'tr', 'pl', 'nl', 'sv', 'da', 'no', 'fi', 'cs'
        }
        
        for lang in v:
            if len(lang) != 2 or lang.lower() not in valid_codes:
                raise ValueError(f"Invalid language code: {lang}")
        
        return [lang.lower() for lang in v]
    
    @model_validator(mode='after')
    def validate_audio_only_format(self):
        """Ensure audio-only downloads use audio format."""
        if self.audio_only and self.output_format not in [VideoFormat.MP4, VideoFormat.WEBM]:
            # For audio-only, we'll convert to audio format in the service
            pass
        
        return self


class TranscriptionFileInfo(BaseModel):
    """Information about a transcription/subtitle file."""
    
    language: str = Field(..., description="Language code")
    format: SubtitleFormat = Field(..., description="Subtitle format")
    file_path: str = Field(..., description="Path/URL to the subtitle file")
    is_auto_generated: bool = Field(..., description="Whether subtitles are auto-generated")


class VideoMetadataInfo(BaseModel):
    """Video metadata information."""
    
    title: str = Field(..., description="Video title")
    duration: int = Field(..., description="Duration in seconds")
    channel_name: str = Field(..., description="Channel/uploader name")
    upload_date: Optional[datetime] = Field(None, description="Upload date")
    view_count: Optional[int] = Field(None, description="View count")
    like_count: Optional[int] = Field(None, description="Like count")
    description: Optional[str] = Field(None, description="Video description")
    thumbnail_url: Optional[str] = Field(None, description="Thumbnail URL")
    video_id: str = Field(..., description="YouTube video ID")


class DownloadJobResponse(BaseModel):
    """Response model for download job information."""
    
    id: UUID = Field(..., description="Job identifier")
    url: str = Field(..., description="YouTube video URL")
    status: JobStatus = Field(..., description="Current job status")
    progress: float = Field(..., description="Download progress (0.0 to 1.0)")
    
    # Request options
    quality: str = Field(..., description="Requested video quality")
    include_transcription: bool = Field(..., description="Whether transcriptions are included")
    audio_only: bool = Field(..., description="Audio-only download")
    output_format: str = Field(..., description="Output format")
    
    # Metadata (available after extraction)
    title: Optional[str] = Field(None, description="Video title")
    duration: Optional[int] = Field(None, description="Duration in seconds")
    channel_name: Optional[str] = Field(None, description="Channel name")
    upload_date: Optional[datetime] = Field(None, description="Upload date")
    view_count: Optional[int] = Field(None, description="View count")
    like_count: Optional[int] = Field(None, description="Like count")
    
    # File paths (available after completion)
    video_path: Optional[str] = Field(None, description="Path/URL to downloaded video")
    transcription_path: Optional[str] = Field(None, description="Path/URL to transcription file")
    thumbnail_path: Optional[str] = Field(None, description="Path/URL to thumbnail")
    
    # Timestamps
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Processing start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    
    # Error information
    error_message: Optional[str] = Field(None, description="Error message if failed")
    retry_count: int = Field(0, description="Number of retry attempts")


class DownloadProgressUpdate(BaseModel):
    """Real-time progress update via WebSocket."""
    
    job_id: UUID = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Current status")
    progress: float = Field(..., description="Progress percentage (0.0 to 1.0)")
    message: str = Field(..., description="Progress message")
    
    # Additional progress details
    downloaded_bytes: Optional[int] = Field(None, description="Bytes downloaded")
    total_bytes: Optional[int] = Field(None, description="Total bytes to download")
    download_speed: Optional[float] = Field(None, description="Download speed in bytes/second")
    eta: Optional[int] = Field(None, description="Estimated time remaining in seconds")
    
    timestamp: datetime = Field(default_factory=datetime.now, description="Update timestamp")


class DownloadJobsList(BaseModel):
    """Paginated list of download jobs."""
    
    jobs: List[DownloadJobResponse] = Field(..., description="List of download jobs")
    total: int = Field(..., description="Total number of jobs")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Jobs per page")
    pages: int = Field(..., description="Total number of pages")


class QualityPresetInfo(BaseModel):
    """Information about a quality preset."""
    
    name: str = Field(..., description="Preset name")
    video_bitrate: str = Field(..., description="Video bitrate")
    audio_bitrate: str = Field(..., description="Audio bitrate")
    max_resolution: str = Field(..., description="Maximum resolution")


class SystemStatusResponse(BaseModel):
    """System status information."""
    
    status: str = Field(..., description="Overall system status")
    active_downloads: int = Field(..., description="Number of active downloads")
    queue_length: int = Field(..., description="Number of queued jobs")
    available_qualities: List[VideoQuality] = Field(..., description="Supported video qualities")
    available_formats: List[VideoFormat] = Field(..., description="Supported video formats")
    audio_formats: List[AudioFormat] = Field(..., description="Supported audio formats")
    quality_presets: List[QualityPresetInfo] = Field(..., description="Available quality presets")
    max_concurrent_downloads: int = Field(..., description="Maximum concurrent downloads")
    storage_type: str = Field(..., description="Storage type (local/s3)")


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")