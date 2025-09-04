from datetime import datetime
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
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
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