from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()


class DownloadJob(Base):
    """
    SQLAlchemy model for YouTube video download jobs.
    
    Tracks the complete lifecycle of a video download request,
    including metadata, processing options, storage paths, and status.
    """
    __tablename__ = "download_jobs"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Core download information
    url = Column(String, nullable=False, index=True)
    status = Column(
        String, 
        nullable=False, 
        default="queued", 
        index=True
    )  # queued, processing, completed, failed
    progress = Column(Float, default=0.0)
    
    # Video metadata (populated after extraction)
    title = Column(String)
    duration = Column(Integer)  # Duration in seconds
    channel_name = Column(String)
    upload_date = Column(DateTime)
    view_count = Column(Integer)
    like_count = Column(Integer)
    
    # Processing options (set by user)
    quality = Column(String, default="best")  # best, 720p, 1080p, etc.
    include_transcription = Column(Boolean, default=True)
    audio_only = Column(Boolean, default=False)
    output_format = Column(String, default="mp4")  # mp4, mkv, webm, etc.
    subtitle_languages = Column(String)  # JSON array of language codes
    
    # Storage paths (populated after download)
    video_path = Column(String)
    transcription_path = Column(String)
    thumbnail_path = Column(String)
    
    # File information
    file_size = Column(Integer)  # File size in bytes
    video_codec = Column(String)
    audio_codec = Column(String)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Additional metadata
    user_agent = Column(String)  # User agent used for download
    ip_address = Column(String)  # Client IP address
    
    def __repr__(self) -> str:
        return f"<DownloadJob(id={self.id}, url={self.url}, status={self.status})>"
    
    def __str__(self) -> str:
        return f"DownloadJob({self.id}): {self.title or 'Untitled'} - {self.status}"
    
    @property
    def is_completed(self) -> bool:
        """Check if the download job is completed successfully."""
        return self.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        """Check if the download job has failed."""
        return self.status == "failed"
    
    @property
    def is_processing(self) -> bool:
        """Check if the download job is currently processing."""
        return self.status == "processing"
    
    @property
    def can_retry(self) -> bool:
        """Check if the download job can be retried."""
        return self.retry_count < self.max_retries and self.is_failed
    
    @property
    def duration_formatted(self) -> Optional[str]:
        """Get formatted duration string (HH:MM:SS)."""
        if not self.duration:
            return None
        
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def file_size_formatted(self) -> Optional[str]:
        """Get formatted file size string."""
        if not self.file_size:
            return None
        
        # Convert bytes to human-readable format
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if self.file_size < 1024:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024
        
        return f"{self.file_size:.1f} PB"
    
    def to_dict(self) -> dict:
        """Convert the model instance to a dictionary."""
        return {
            'id': str(self.id),
            'url': self.url,
            'status': self.status,
            'progress': self.progress,
            'title': self.title,
            'duration': self.duration,
            'duration_formatted': self.duration_formatted,
            'channel_name': self.channel_name,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'view_count': self.view_count,
            'like_count': self.like_count,
            'quality': self.quality,
            'include_transcription': self.include_transcription,
            'audio_only': self.audio_only,
            'output_format': self.output_format,
            'subtitle_languages': self.subtitle_languages,
            'video_path': self.video_path,
            'transcription_path': self.transcription_path,
            'thumbnail_path': self.thumbnail_path,
            'file_size': self.file_size,
            'file_size_formatted': self.file_size_formatted,
            'video_codec': self.video_codec,
            'audio_codec': self.audio_codec,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'can_retry': self.can_retry,
        }


class APIKey(Base):
    """
    SQLAlchemy model for API key management.
    
    Stores hashed API keys with associated permissions and metadata
    for authentication and authorization.
    """
    __tablename__ = "api_keys"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # API key information
    name = Column(String, nullable=False, index=True)  # Human-readable name
    key_hash = Column(String, nullable=False, unique=True, index=True)  # SHA-256 hash of API key
    permission_level = Column(String, nullable=False, default="read_only")  # Permission level
    
    # Status and metadata
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    description = Column(Text)  # Optional description
    
    # Usage tracking
    last_used_at = Column(DateTime(timezone=True))
    usage_count = Column(Integer, nullable=False, default=0)
    
    # Rate limiting (optional override of default limits)
    custom_rate_limit = Column(Integer)  # Custom requests per minute limit
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True))  # Optional expiration date
    
    # Metadata
    created_by = Column(String)  # Who created this API key
    notes = Column(Text)  # Additional notes
    
    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name}, permission={self.permission_level})>"
    
    def __str__(self) -> str:
        return f"APIKey({self.name}): {self.permission_level} - {'Active' if self.is_active else 'Inactive'}"
    
    @property
    def is_expired(self) -> bool:
        """Check if the API key has expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if the API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired
    
    @property
    def days_until_expiry(self) -> Optional[int]:
        """Get number of days until API key expires."""
        if not self.expires_at:
            return None
        
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, delta.days)
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """
        Convert the model instance to a dictionary.
        
        Args:
            include_sensitive: Whether to include sensitive information (key_hash)
        """
        data = {
            'id': str(self.id),
            'name': self.name,
            'permission_level': self.permission_level,
            'is_active': self.is_active,
            'description': self.description,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'usage_count': self.usage_count,
            'custom_rate_limit': self.custom_rate_limit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_by': self.created_by,
            'notes': self.notes,
            'is_expired': self.is_expired,
            'is_valid': self.is_valid,
            'days_until_expiry': self.days_until_expiry,
        }
        
        if include_sensitive:
            data['key_hash'] = self.key_hash
        
        return data