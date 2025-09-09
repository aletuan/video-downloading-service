import asyncio
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Callable
import uuid
import json

import aiofiles
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.core.config import settings
from app.core.storage import init_storage
from app.core.cookie_manager import CookieManager, CookieDownloadError, CookieValidationError, CookieExpiredError, CookieRateLimitError, CookieIntegrityError
from app.models.database import DownloadJob

logger = logging.getLogger(__name__)


class DownloadProgress:
    """Progress tracking for downloads."""
    
    def __init__(self, job_id: str, progress_callback: Optional[Callable] = None):
        self.job_id = job_id
        self.progress_callback = progress_callback
        self.current_progress = 0.0
        
    def __call__(self, d: Dict[str, Any]):
        """Progress hook called by yt-dlp during download."""
        try:
            if d['status'] == 'downloading':
                # Calculate progress percentage
                if 'total_bytes' in d and d['total_bytes']:
                    progress = (d.get('downloaded_bytes', 0) / d['total_bytes']) * 100
                elif '_total_bytes_estimate' in d and d['_total_bytes_estimate']:
                    progress = (d.get('downloaded_bytes', 0) / d['_total_bytes_estimate']) * 100
                else:
                    # Use fragment info if available
                    if 'fragment_index' in d and 'fragment_count' in d:
                        progress = (d['fragment_index'] / d['fragment_count']) * 100
                    else:
                        progress = self.current_progress
                
                self.current_progress = min(progress, 100.0)
                
                # Call progress callback if provided
                if self.progress_callback:
                    self.progress_callback(self.current_progress, f"Downloading: {self.current_progress:.1f}%")
                    
                logger.debug(f"Download progress for {self.job_id}: {self.current_progress:.1f}%")
                
            elif d['status'] == 'finished':
                self.current_progress = 100.0
                if self.progress_callback:
                    self.progress_callback(100.0, "Download completed")
                logger.info(f"Download finished for {self.job_id}: {d.get('filename', 'unknown')}")
                
        except Exception as e:
            logger.error(f"Error in progress hook: {e}")


class YouTubeDownloader:
    """
    YouTube video downloader service using yt-dlp.
    
    Handles video downloading, metadata extraction, transcription
    extraction, and format conversion.
    """
    
    def __init__(self, storage_handler=None, cookie_manager=None):
        """
        Initialize the YouTube downloader.
        
        Args:
            storage_handler: Storage handler instance, defaults to global storage
            cookie_manager: Cookie manager instance for authenticated downloads
        """
        self.storage = storage_handler or init_storage()
        self.temp_dir = Path(tempfile.gettempdir()) / "youtube_service"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Initialize cookie manager for anti-bot protection
        try:
            self.cookie_manager = cookie_manager or CookieManager()
            self.cookies_enabled = True
            logger.info("Cookie manager initialized for authenticated downloads")
        except Exception as e:
            logger.warning(f"Cookie manager initialization failed: {e}")
            self.cookie_manager = None
            self.cookies_enabled = False
        
        # Cookie-related metrics
        self.cookie_stats = {
            'successful_downloads': 0,
            'failed_downloads': 0,
            'cookie_fallbacks': 0,
            'rate_limit_hits': 0,
            'integrity_failures': 0
        }
        
        logger.info(f"YouTubeDownloader initialized with storage: {type(self.storage).__name__}, cookies_enabled: {self.cookies_enabled}")
    
    async def _get_yt_dlp_options(
        self, 
        output_path: str, 
        quality: str = "best",
        output_format: str = "mp4",
        extract_subtitles: bool = True,
        subtitle_langs: Optional[List[str]] = None,
        progress_hook: Optional[Callable] = None,
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Get yt-dlp options based on user preferences.
        
        Args:
            output_path: Path where files should be saved
            quality: Video quality (best, worst, 720p, 1080p, etc.)
            output_format: Output format (mp4, mkv, webm, etc.)
            extract_subtitles: Whether to extract subtitles
            subtitle_langs: List of subtitle languages to extract
            progress_hook: Progress callback function
            session_id: Session identifier for rate limiting
            
        Returns:
            dict: yt-dlp options with secure cookie integration
        """
        # Base options
        options = {
            'outtmpl': str(Path(output_path) / '%(title)s.%(ext)s'),
            'format': self._get_format_selector(quality, output_format),
            'writeinfojson': True,  # Write metadata
            'writethumbnail': True,  # Download thumbnail
            'embedsubs': False,  # Don't embed subs, extract separately
            'writesubtitles': extract_subtitles,
            'writeautomaticsub': extract_subtitles,
            'subtitleslangs': subtitle_langs or ['en', 'en-US'],
            'subtitlesformat': 'srt/vtt/best',
            'ignoreerrors': False,
            'no_warnings': False,
            'extractflat': False,
            'updatetime': settings.yt_dlp_update_check,
        }
        
        # Add progress hook if provided
        if progress_hook:
            options['progress_hooks'] = [progress_hook]
            
        # Format-specific options
        if output_format in ['mp4', 'mkv']:
            options['merge_output_format'] = output_format
        
        # Integrate secure cookie authentication
        if self.cookies_enabled and self.cookie_manager:
            try:
                logger.info(f"Attempting to get secure cookies for session: {session_id}")
                cookie_file_path = await self.cookie_manager.get_active_cookies(session_id)
                options['cookiefile'] = cookie_file_path
                logger.info(f"Successfully integrated cookies from: {cookie_file_path}")
                
            except CookieRateLimitError as e:
                logger.warning(f"Cookie rate limit hit for session {session_id}: {e}")
                self.cookie_stats['rate_limit_hits'] += 1
                # Continue without cookies - will handle rate limiting at higher level
                
            except CookieIntegrityError as e:
                logger.error(f"Cookie integrity validation failed: {e}")
                self.cookie_stats['integrity_failures'] += 1
                # Continue without cookies - integrity issues need manual intervention
                
            except (CookieDownloadError, CookieValidationError, CookieExpiredError) as e:
                logger.warning(f"Cookie error for session {session_id}: {e}")
                self.cookie_stats['failed_downloads'] += 1
                
                # Try backup cookies as fallback
                try:
                    logger.info("Attempting fallback to backup cookies")
                    cookie_file_path = await self.cookie_manager.get_backup_cookies(session_id)
                    options['cookiefile'] = cookie_file_path
                    self.cookie_stats['cookie_fallbacks'] += 1
                    logger.info(f"Successfully integrated backup cookies from: {cookie_file_path}")
                    
                except Exception as backup_error:
                    logger.error(f"Backup cookies also failed: {backup_error}")
                    # Continue without cookies
                    
            except Exception as e:
                logger.error(f"Unexpected cookie error: {e}")
                # Continue without cookies
        else:
            logger.info("Cookie authentication disabled or unavailable")
            
        return options
    
    def _get_format_selector(self, quality: str, output_format: str) -> str:
        """
        Get yt-dlp format selector string based on quality and format preferences.
        
        Args:
            quality: Quality preference (best, worst, 720p, 1080p, etc.)
            output_format: Preferred output format
            
        Returns:
            str: Format selector string
        """
        if quality == "best":
            return f"best[ext={output_format}]/best"
        elif quality == "worst":
            return f"worst[ext={output_format}]/worst"
        elif quality.endswith('p'):
            # Specific resolution (e.g., "720p", "1080p")
            height = quality[:-1]
            return f"best[height<={height}][ext={output_format}]/best[height<={height}]/best"
        else:
            # Default to best
            return f"best[ext={output_format}]/best"
    
    async def extract_info(self, url: str) -> Dict[str, Any]:
        """
        Extract video information without downloading.
        
        Args:
            url: YouTube video URL
            
        Returns:
            dict: Video metadata
        """
        try:
            options = {
                'quiet': True,
                'no_warnings': True,
                'extractflat': False,
            }
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def _extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract)
            
            # Extract relevant metadata
            metadata = {
                'id': info.get('id'),
                'title': info.get('title'),
                'description': info.get('description'),
                'duration': info.get('duration'),
                'upload_date': info.get('upload_date'),
                'uploader': info.get('uploader'),
                'uploader_id': info.get('uploader_id'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'comment_count': info.get('comment_count'),
                'thumbnail': info.get('thumbnail'),
                'tags': info.get('tags', []),
                'categories': info.get('categories', []),
                'language': info.get('language'),
                'available_formats': len(info.get('formats', [])),
                'has_subtitles': bool(info.get('subtitles')),
                'available_subtitles': list(info.get('subtitles', {}).keys()),
                'automatic_captions': list(info.get('automatic_captions', {}).keys()),
            }
            
            logger.info(f"Extracted info for video: {metadata.get('title', 'Unknown')}")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract video info from {url}: {e}")
            raise DownloadError(f"Failed to extract video info: {str(e)}")
    
    async def download_video(
        self,
        url: str,
        job_id: str,
        quality: str = "best",
        output_format: str = "mp4",
        audio_only: bool = False,
        include_transcription: bool = True,
        subtitle_languages: Optional[List[str]] = None,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Download a YouTube video with specified options.
        
        Args:
            url: YouTube video URL
            job_id: Unique job identifier
            quality: Video quality preference
            output_format: Output format preference  
            audio_only: Download audio only
            include_transcription: Extract subtitles/transcriptions
            subtitle_languages: List of subtitle languages
            progress_callback: Progress update callback
            
        Returns:
            dict: Download results with file paths and metadata
        """
        temp_output_dir = self.temp_dir / job_id
        temp_output_dir.mkdir(exist_ok=True)
        
        try:
            # Update progress
            if progress_callback:
                progress_callback(5.0, "Extracting video information...")
            
            # Extract video info first
            info = await self.extract_info(url)
            
            if progress_callback:
                progress_callback(10.0, "Preparing download...")
            
            # Create progress tracker
            progress_tracker = DownloadProgress(job_id, progress_callback)
            
            # Configure yt-dlp options with secure cookie integration
            options = await self._get_yt_dlp_options(
                output_path=str(temp_output_dir),
                quality=quality if not audio_only else "bestaudio",
                output_format="mp3" if audio_only else output_format,
                extract_subtitles=include_transcription,
                subtitle_langs=subtitle_languages,
                progress_hook=progress_tracker,
                session_id=job_id  # Use job_id as session identifier
            )
            
            if audio_only:
                options['format'] = 'bestaudio/best'
                options['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            
            # Download the video with enhanced error handling
            download_success = False
            loop = asyncio.get_event_loop()
            
            def _download():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.download([url])
            
            try:
                await loop.run_in_executor(None, _download)
                download_success = True
                
                # Track successful cookie usage
                if 'cookiefile' in options and self.cookies_enabled:
                    self.cookie_stats['successful_downloads'] += 1
                    logger.info(f"Download succeeded with cookies for job {job_id}")
                    
            except (DownloadError, ExtractorError) as e:
                error_msg = str(e)
                
                # Check if this is a cookie-related authentication error
                if self._is_cookie_related_error(error_msg):
                    logger.warning(f"Cookie-related download error detected: {error_msg}")
                    
                    # Try without cookies as fallback
                    if 'cookiefile' in options:
                        logger.info("Attempting download without cookies as fallback")
                        fallback_options = options.copy()
                        del fallback_options['cookiefile']
                        
                        try:
                            def _fallback_download():
                                with yt_dlp.YoutubeDL(fallback_options) as ydl:
                                    return ydl.download([url])
                            
                            await loop.run_in_executor(None, _fallback_download)
                            download_success = True
                            logger.info(f"Fallback download without cookies succeeded for job {job_id}")
                            
                        except Exception as fallback_error:
                            logger.error(f"Fallback download also failed: {fallback_error}")
                            raise
                    else:
                        raise
                else:
                    # Non-cookie related error, re-raise
                    raise
            
            if progress_callback:
                progress_callback(80.0, "Processing downloaded files...")
            
            # Process downloaded files
            result = await self._process_downloaded_files(
                temp_output_dir, job_id, info, audio_only
            )
            
            if progress_callback:
                progress_callback(95.0, "Uploading to storage...")
            
            # Upload files to storage
            storage_result = await self._upload_to_storage(result, job_id)
            
            if progress_callback:
                progress_callback(100.0, "Download completed successfully!")
            
            return {
                **result,
                **storage_result,
                'metadata': info
            }
            
        except Exception as e:
            logger.error(f"Download failed for job {job_id}: {e}")
            raise
        finally:
            # Clean up temporary files
            await self._cleanup_temp_files(temp_output_dir)
    
    async def _process_downloaded_files(
        self, 
        temp_dir: Path, 
        job_id: str, 
        info: Dict[str, Any],
        audio_only: bool
    ) -> Dict[str, Any]:
        """
        Process downloaded files and organize them.
        
        Args:
            temp_dir: Temporary directory with downloaded files
            job_id: Job identifier
            info: Video metadata
            audio_only: Whether this was audio-only download
            
        Returns:
            dict: Processed file information
        """
        result = {
            'video_file': None,
            'audio_file': None,
            'thumbnail_file': None,
            'info_file': None,
            'subtitle_files': [],
            'file_size': 0
        }
        
        try:
            # Find downloaded files
            for file_path in temp_dir.iterdir():
                if file_path.is_file():
                    file_size = file_path.stat().st_size
                    
                    if file_path.suffix.lower() in ['.mp4', '.mkv', '.webm', '.avi']:
                        result['video_file'] = str(file_path)
                        result['file_size'] += file_size
                    elif file_path.suffix.lower() in ['.mp3', '.m4a', '.wav', '.flac']:
                        result['audio_file'] = str(file_path)
                        result['file_size'] += file_size
                    elif file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                        result['thumbnail_file'] = str(file_path)
                    elif file_path.suffix.lower() == '.json' and 'info' in file_path.name:
                        result['info_file'] = str(file_path)
                    elif file_path.suffix.lower() in ['.srt', '.vtt', '.ass']:
                        result['subtitle_files'].append(str(file_path))
            
            # Set primary file based on download type
            if audio_only:
                result['primary_file'] = result['audio_file']
                result['file_type'] = 'audio'
            else:
                result['primary_file'] = result['video_file']
                result['file_type'] = 'video'
            
            logger.info(f"Processed files for job {job_id}: {len([f for f in result.values() if f])} files")
            return result
            
        except Exception as e:
            logger.error(f"Error processing downloaded files: {e}")
            raise
    
    async def _upload_to_storage(self, file_info: Dict[str, Any], job_id: str) -> Dict[str, Any]:
        """
        Upload processed files to storage.
        
        Args:
            file_info: Information about downloaded files
            job_id: Job identifier
            
        Returns:
            dict: Storage paths and URLs
        """
        storage_result = {
            'video_path': None,
            'audio_path': None,
            'thumbnail_path': None,
            'subtitle_paths': [],
            'video_url': None,
            'audio_url': None,
            'thumbnail_url': None,
        }
        
        try:
            # Upload primary file (video or audio)
            if file_info.get('primary_file') and Path(file_info['primary_file']).exists():
                primary_file = Path(file_info['primary_file'])
                storage_path = f"downloads/{job_id}/{primary_file.name}"
                
                # Read and upload file
                async with aiofiles.open(primary_file, 'rb') as f:
                    content = await f.read()
                
                success = await self.storage.save_file(storage_path, content)
                if success:
                    url = await self.storage.get_file_url(storage_path)
                    if file_info['file_type'] == 'video':
                        storage_result['video_path'] = storage_path
                        storage_result['video_url'] = url
                    else:
                        storage_result['audio_path'] = storage_path
                        storage_result['audio_url'] = url
            
            # Upload thumbnail
            if file_info.get('thumbnail_file') and Path(file_info['thumbnail_file']).exists():
                thumbnail_file = Path(file_info['thumbnail_file'])
                storage_path = f"downloads/{job_id}/thumbnail{thumbnail_file.suffix}"
                
                async with aiofiles.open(thumbnail_file, 'rb') as f:
                    content = await f.read()
                
                success = await self.storage.save_file(storage_path, content)
                if success:
                    storage_result['thumbnail_path'] = storage_path
                    storage_result['thumbnail_url'] = await self.storage.get_file_url(storage_path)
            
            # Upload subtitles
            for subtitle_file_path in file_info.get('subtitle_files', []):
                if Path(subtitle_file_path).exists():
                    subtitle_file = Path(subtitle_file_path)
                    storage_path = f"downloads/{job_id}/subtitles/{subtitle_file.name}"
                    
                    async with aiofiles.open(subtitle_file, 'rb') as f:
                        content = await f.read()
                    
                    success = await self.storage.save_file(storage_path, content)
                    if success:
                        storage_result['subtitle_paths'].append(storage_path)
            
            logger.info(f"Uploaded files to storage for job {job_id}")
            return storage_result
            
        except Exception as e:
            logger.error(f"Error uploading files to storage: {e}")
            raise
    
    async def _cleanup_temp_files(self, temp_dir: Path):
        """Clean up temporary files after processing."""
        try:
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {e}")
        
        # Clean up cookie temporary files
        if self.cookies_enabled and self.cookie_manager:
            try:
                await self.cookie_manager.cleanup_temporary_files(max_age_hours=1)
            except Exception as e:
                logger.warning(f"Failed to cleanup cookie temporary files: {e}")
    
    def _is_cookie_related_error(self, error_message: str) -> bool:
        """
        Check if the error message indicates a cookie-related authentication issue.
        
        Args:
            error_message: Error message from yt-dlp
            
        Returns:
            bool: True if error is likely cookie-related
        """
        cookie_error_patterns = [
            'sign in',
            'login required',
            'authentication',
            'unavailable',
            'private video',
            'age-restricted',
            'content warning',
            'verify your account',
            '403',
            'forbidden',
            'blocked',
            'rate limit',
            'too many requests'
        ]
        
        error_lower = error_message.lower()
        return any(pattern in error_lower for pattern in cookie_error_patterns)
    
    def get_cookie_statistics(self) -> Dict[str, Any]:
        """
        Get cookie usage statistics for monitoring.
        
        Returns:
            dict: Cookie usage statistics
        """
        total_attempts = (
            self.cookie_stats['successful_downloads'] + 
            self.cookie_stats['failed_downloads']
        )
        
        success_rate = (
            (self.cookie_stats['successful_downloads'] / total_attempts * 100) 
            if total_attempts > 0 else 0
        )
        
        return {
            'cookies_enabled': self.cookies_enabled,
            'total_download_attempts': total_attempts,
            'successful_downloads': self.cookie_stats['successful_downloads'],
            'failed_downloads': self.cookie_stats['failed_downloads'],
            'cookie_fallbacks': self.cookie_stats['cookie_fallbacks'],
            'rate_limit_hits': self.cookie_stats['rate_limit_hits'],
            'integrity_failures': self.cookie_stats['integrity_failures'],
            'success_rate_percent': round(success_rate, 2),
            'fallback_rate_percent': round(
                (self.cookie_stats['cookie_fallbacks'] / total_attempts * 100) 
                if total_attempts > 0 else 0, 2
            )
        }
    
    async def get_available_formats(self, url: str) -> List[Dict[str, Any]]:
        """
        Get available formats for a video.
        
        Args:
            url: YouTube video URL
            
        Returns:
            list: Available formats with quality and size information
        """
        try:
            info = await self.extract_info(url)
            formats = []
            
            # Extract format information from yt-dlp
            loop = asyncio.get_event_loop()
            
            def _get_formats():
                options = {'quiet': True, 'listformats': True}
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(url, download=False)
            
            detailed_info = await loop.run_in_executor(None, _get_formats)
            
            for fmt in detailed_info.get('formats', []):
                if fmt.get('vcodec') != 'none':  # Has video
                    formats.append({
                        'format_id': fmt.get('format_id'),
                        'quality': f"{fmt.get('height', 'unknown')}p" if fmt.get('height') else 'unknown',
                        'ext': fmt.get('ext'),
                        'filesize': fmt.get('filesize'),
                        'fps': fmt.get('fps'),
                        'vcodec': fmt.get('vcodec'),
                        'acodec': fmt.get('acodec'),
                    })
            
            return formats
            
        except Exception as e:
            logger.error(f"Error getting available formats: {e}")
            return []
    
    def is_valid_youtube_url(self, url: str) -> bool:
        """
        Check if URL is a valid YouTube URL.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if valid YouTube URL
        """
        youtube_domains = [
            'youtube.com', 'www.youtube.com', 'm.youtube.com',
            'youtu.be', 'www.youtu.be'
        ]
        
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return any(domain in parsed.netloc for domain in youtube_domains)
        except:
            return False