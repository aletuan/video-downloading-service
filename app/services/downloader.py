"""
YouTube Downloader Service

Core service for downloading YouTube videos using yt-dlp with support for:
- Video metadata extraction
- Multiple quality/format options
- Transcription extraction
- Progress tracking
- Error handling and retries
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, asdict

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.core.config import settings
from app.core.storage import get_storage_handler
from app.models.database import DownloadJob


logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Video metadata extracted from YouTube."""
    title: str
    duration: int  # seconds
    channel_name: str
    upload_date: datetime
    view_count: int
    like_count: int
    description: str
    thumbnail_url: str
    video_id: str
    formats_available: List[str]
    subtitles_available: List[str]


@dataclass
class DownloadOptions:
    """Configuration options for video download."""
    quality: str = "best"  # best, worst, 720p, 1080p, 1440p, 2160p
    include_transcription: bool = True
    audio_only: bool = False
    output_format: str = "mp4"  # mp4, mkv, webm
    subtitle_languages: List[str] = None
    extract_thumbnail: bool = True
    
    def __post_init__(self):
        if self.subtitle_languages is None:
            self.subtitle_languages = ["en"]


@dataclass
class TranscriptionFile:
    """Transcription/subtitle file information."""
    language: str
    format: str  # srt, vtt, txt
    file_path: str
    is_auto_generated: bool


@dataclass
class DownloadResult:
    """Result of a completed download operation."""
    success: bool
    video_path: Optional[str] = None
    transcription_files: List[TranscriptionFile] = None
    thumbnail_path: Optional[str] = None
    metadata: Optional[VideoMetadata] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.transcription_files is None:
            self.transcription_files = []


class YouTubeDownloader:
    """
    YouTube video downloader service using yt-dlp.
    
    Provides comprehensive video downloading capabilities with metadata extraction,
    transcription support, and progress tracking.
    """
    
    def __init__(self):
        self.storage_handler = get_storage_handler()
        self.temp_dir = Path("/tmp/youtube_downloads")
        self.temp_dir.mkdir(exist_ok=True)
    
    async def extract_metadata(self, url: str) -> VideoMetadata:
        """
        Extract video metadata without downloading.
        
        Args:
            url: YouTube video URL
            
        Returns:
            VideoMetadata object with video information
            
        Raises:
            DownloadError: If URL is invalid or video is inaccessible
        """
        logger.info(f"Extracting metadata for URL: {url}")
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, ydl.extract_info, url, False
                )
                
            # Parse upload date
            upload_date_str = info.get('upload_date', '')
            upload_date = None
            if upload_date_str:
                try:
                    upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                except ValueError:
                    logger.warning(f"Could not parse upload date: {upload_date_str}")
            
            # Extract available formats
            formats = []
            if 'formats' in info:
                for fmt in info['formats']:
                    if fmt.get('height') and fmt.get('ext'):
                        formats.append(f"{fmt['height']}p-{fmt['ext']}")
            
            # Extract available subtitles
            subtitles = []
            if 'subtitles' in info:
                subtitles = list(info['subtitles'].keys())
            if 'automatic_captions' in info:
                auto_subs = list(info['automatic_captions'].keys())
                subtitles.extend([f"{lang} (auto)" for lang in auto_subs])
            
            metadata = VideoMetadata(
                title=info.get('title', 'Unknown'),
                duration=info.get('duration', 0),
                channel_name=info.get('uploader', 'Unknown'),
                upload_date=upload_date,
                view_count=info.get('view_count', 0),
                like_count=info.get('like_count', 0),
                description=info.get('description', ''),
                thumbnail_url=info.get('thumbnail', ''),
                video_id=info.get('id', ''),
                formats_available=formats,
                subtitles_available=subtitles
            )
            
            logger.info(f"Successfully extracted metadata for: {metadata.title}")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract metadata for {url}: {str(e)}")
            raise DownloadError(f"Could not extract metadata: {str(e)}")
    
    async def download_video(
        self, 
        job_id: str, 
        url: str, 
        options: DownloadOptions,
        progress_callback: Optional[Callable[[Dict], None]] = None
    ) -> DownloadResult:
        """
        Download video with specified options.
        
        Args:
            job_id: Unique job identifier
            url: YouTube video URL
            options: Download configuration options
            progress_callback: Optional callback for progress updates
            
        Returns:
            DownloadResult with paths to downloaded files
        """
        logger.info(f"Starting download for job {job_id}: {url}")
        
        # Sanitize job_id for directory creation
        safe_job_id = self._sanitize_job_id(job_id)
        job_temp_dir = self.temp_dir / safe_job_id
        
        try:
            # Create temporary download directory for this job
            job_temp_dir.mkdir(exist_ok=True)
            
            # First extract metadata
            metadata = await self.extract_metadata(url)
            
            # Configure yt-dlp options
            ydl_opts = self._configure_yt_dlp_options(
                options, job_temp_dir, progress_callback
            )
            
            # Download video
            video_path = None
            transcription_files = []
            thumbnail_path = None
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download the video
                await asyncio.get_event_loop().run_in_executor(
                    None, ydl.download, [url]
                )
                
                # Find downloaded files
                downloaded_files = list(job_temp_dir.glob("*"))
                
                for file_path in downloaded_files:
                    if file_path.suffix.lower() in ['.mp4', '.mkv', '.webm', '.m4a', '.mp3']:
                        # Main video/audio file
                        final_path = await self._store_file(file_path, job_id, "video")
                        video_path = final_path
                        
                    elif file_path.suffix.lower() in ['.srt', '.vtt', '.txt']:
                        # Transcription file
                        final_path = await self._store_file(file_path, job_id, "transcription")
                        
                        # Determine language from filename (yt-dlp includes lang code)
                        lang = "en"  # default
                        filename = file_path.stem
                        if "." in filename:
                            parts = filename.split(".")
                            if len(parts) > 1:
                                lang = parts[-1]
                        
                        transcription_files.append(TranscriptionFile(
                            language=lang,
                            format=file_path.suffix[1:],  # remove dot
                            file_path=final_path,
                            is_auto_generated="auto" in filename.lower()
                        ))
                        
                    elif file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                        # Thumbnail file
                        final_path = await self._store_file(file_path, job_id, "thumbnail")
                        thumbnail_path = final_path
            
            result = DownloadResult(
                success=True,
                video_path=video_path,
                transcription_files=transcription_files,
                thumbnail_path=thumbnail_path,
                metadata=metadata
            )
            
            logger.info(f"Successfully completed download for job {job_id}")
            return result
            
        except Exception as e:
            logger.error(f"Download failed for job {job_id}: {str(e)}")
            
            return DownloadResult(
                success=False,
                error_message=str(e)
            )
            
        finally:
            # Always clean up temporary directory
            if job_temp_dir.exists():
                await self._cleanup_temp_directory(job_temp_dir)
    
    def _configure_yt_dlp_options(
        self, 
        options: DownloadOptions, 
        output_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Configure yt-dlp options based on download preferences."""
        
        # Base output template
        output_template = str(output_dir / "%(title)s.%(ext)s")
        
        # Quality/format selection
        if options.audio_only:
            format_selector = 'bestaudio/best'
        elif options.quality == "best":
            format_selector = 'best'
        elif options.quality == "worst":
            format_selector = 'worst'
        else:
            # Specific quality (e.g., "720p")
            height = options.quality.replace('p', '')
            format_selector = f'best[height<={height}]'
        
        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_template,
            'writesubtitles': options.include_transcription,
            'writeautomaticsub': options.include_transcription,
            'subtitleslangs': options.subtitle_languages,
            'writethumbnail': options.extract_thumbnail,
            'ignoreerrors': False,
            'no_warnings': False,
        }
        
        # Add progress hook if provided
        if progress_callback:
            ydl_opts['progress_hooks'] = [progress_callback]
        
        # Format-specific options
        if not options.audio_only and options.output_format != 'best':
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': options.output_format,
            }]
        
        return ydl_opts
    
    def _sanitize_job_id(self, job_id: str) -> str:
        """Sanitize job ID to prevent path traversal attacks."""
        # Remove any path traversal sequences and non-alphanumeric characters
        # Keep only alphanumeric, hyphens, and underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', job_id)
        
        # Ensure it's not empty after sanitization
        if not sanitized:
            sanitized = 'unknown'
            
        # Limit length to prevent excessively long paths
        return sanitized[:50]
    
    async def _store_file(self, file_path: Path, job_id: str, file_type: str) -> str:
        """Store downloaded file using the configured storage handler."""
        
        # Sanitize job ID to prevent path traversal
        safe_job_id = self._sanitize_job_id(job_id)
        
        # Generate storage key based on file type
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = file_path.suffix
        
        if file_type == "video":
            storage_key = f"videos/{safe_job_id}/{timestamp}_video{extension}"
        elif file_type == "transcription":
            language = file_path.stem.split('.')[-1] if '.' in file_path.stem else 'en'
            storage_key = f"transcriptions/{safe_job_id}/{timestamp}_{language}{extension}"
        elif file_type == "thumbnail":
            storage_key = f"thumbnails/{safe_job_id}/{timestamp}_thumbnail{extension}"
        else:
            storage_key = f"misc/{safe_job_id}/{timestamp}{extension}"
        
        # Store file
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        await self.storage_handler.save_file(storage_key, file_data)
        
        # Return the access URL
        return await self.storage_handler.get_file_url(storage_key)
    
    async def _cleanup_temp_directory(self, temp_dir: Path):
        """Clean up temporary download directory."""
        try:
            import shutil
            await asyncio.get_event_loop().run_in_executor(
                None, shutil.rmtree, temp_dir
            )
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up {temp_dir}: {str(e)}")


# Factory function for easy instantiation
def create_youtube_downloader() -> YouTubeDownloader:
    """Create a new YouTubeDownloader instance."""
    return YouTubeDownloader()