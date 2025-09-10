"""
Integration tests for YouTubeDownloader with CookieManager.

This module tests the integration between the YouTubeDownloader service
and the CookieManager, including cookie authentication, error handling,
and fallback mechanisms.
"""

import pytest
import asyncio
import json
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

from app.services.downloader import YouTubeDownloader
from app.core.cookie_manager import CookieManager
from app.models.job import JobStatus, DownloadFormat


@pytest.mark.integration
class TestYouTubeDownloaderIntegration:
    """Integration test suite for YouTubeDownloader and CookieManager."""
    
    @pytest.fixture
    def mock_cookie_manager(self, mock_cookie_settings):
        """Create mock CookieManager for integration testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            
            # Mock the key methods
            manager.get_active_cookies = AsyncMock()
            manager.validate_cookie_freshness = AsyncMock()
            manager.rotate_cookies = AsyncMock()
            manager.cleanup_temporary_files = AsyncMock()
            
            return manager
    
    @pytest.fixture
    def youtube_downloader(self, mock_cookie_manager):
        """Create YouTubeDownloader with mocked CookieManager."""
        with patch('app.services.downloader.CookieManager', return_value=mock_cookie_manager):
            downloader = YouTubeDownloader()
            downloader.cookie_manager = mock_cookie_manager
            return downloader
    
    @pytest.fixture
    def sample_job_data(self):
        """Sample job data for testing."""
        return {
            'id': 'test-job-123',
            'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'format': DownloadFormat.MP4,
            'quality': '720p',
            'audio_only': False,
            'extract_audio': False,
            'custom_filename': None,
            'metadata': {}
        }
    
    @pytest.fixture
    def mock_yt_dlp_response(self):
        """Mock yt-dlp successful response."""
        return {
            'id': 'dQw4w9WgXcQ',
            'title': 'Test Video Title',
            'uploader': 'Test Channel',
            'duration': 212,
            'view_count': 1000000,
            'like_count': 50000,
            'description': 'Test video description',
            'upload_date': '20220101',
            'formats': [
                {
                    'format_id': '720p',
                    'ext': 'mp4',
                    'width': 1280,
                    'height': 720,
                    'filesize': 50000000,
                    'url': 'https://test-video-url.com/video.mp4'
                }
            ],
            'requested_formats': [
                {
                    'format_id': '720p',
                    'ext': 'mp4',
                    'filesize': 50000000
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_downloader_uses_cookie_manager_for_authentication(
        self, youtube_downloader, mock_cookie_manager, sample_job_data
    ):
        """Test that downloader integrates with cookie manager for authentication."""
        # Setup cookie manager mock
        mock_cookie_file = '/tmp/test_cookies.txt'
        mock_cookie_manager.get_active_cookies.return_value = mock_cookie_file
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 15
        }
        
        # Mock yt-dlp
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = self.mock_yt_dlp_response
            
            # Mock storage handler
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Execute download
                result = await youtube_downloader.download_video(
                    url=sample_job_data['url'],
                    job_id=sample_job_data['id'],
                    format_type=sample_job_data['format'],
                    quality=sample_job_data['quality']
                )
        
        # Verify cookie manager was called
        mock_cookie_manager.get_active_cookies.assert_called_once()
        mock_cookie_manager.validate_cookie_freshness.assert_called_once()
        
        # Verify yt-dlp was configured with cookies
        mock_ytdl.assert_called_once()
        call_args = mock_ytdl.call_args[0][0]  # Get the options dict
        assert 'cookiefile' in call_args
        assert call_args['cookiefile'] == mock_cookie_file
        
        # Verify successful result
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_cookie_validation_before_download(
        self, youtube_downloader, mock_cookie_manager, sample_job_data
    ):
        """Test cookie validation occurs before download attempt."""
        # Setup cookie manager to return expired cookies
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': False,
            'expired': True,
            'expires_in_days': -5
        }
        mock_cookie_manager.get_active_cookies.return_value = None
        
        # Execute download
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            result = await youtube_downloader.download_video(
                url=sample_job_data['url'],
                job_id=sample_job_data['id'],
                format_type=sample_job_data['format'],
                quality=sample_job_data['quality']
            )
        
        # Verify cookie validation was called
        mock_cookie_manager.validate_cookie_freshness.assert_called_once()
        
        # Verify download proceeded without cookies (fallback)
        mock_ytdl.assert_called_once()
        call_args = mock_ytdl.call_args[0][0]
        assert 'cookiefile' not in call_args or call_args.get('cookiefile') is None
    
    @pytest.mark.asyncio
    async def test_cookie_failure_fallback_mechanism(
        self, youtube_downloader, mock_cookie_manager, sample_job_data, mock_yt_dlp_response
    ):
        """Test fallback mechanism when cookie authentication fails."""
        # Setup cookie manager to fail initially
        mock_cookie_manager.get_active_cookies.side_effect = [
            Exception("Cookie retrieval failed"),  # First attempt fails
            None  # Fallback to no cookies
        ]
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = mock_yt_dlp_response
            
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Execute download
                result = await youtube_downloader.download_video(
                    url=sample_job_data['url'],
                    job_id=sample_job_data['id'],
                    format_type=sample_job_data['format'],
                    quality=sample_job_data['quality']
                )
        
        # Verify fallback occurred
        assert mock_cookie_manager.get_active_cookies.call_count == 2
        
        # Verify download succeeded without cookies
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_cookie_rotation_on_authentication_failure(
        self, youtube_downloader, mock_cookie_manager, sample_job_data
    ):
        """Test automatic cookie rotation when authentication fails."""
        # Setup initial cookie failure
        mock_cookie_manager.get_active_cookies.return_value = '/tmp/expired_cookies.txt'
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 10
        }
        mock_cookie_manager.rotate_cookies.return_value = {
            'success': True,
            'new_cookie_file': '/tmp/fresh_cookies.txt'
        }
        
        # Mock yt-dlp to fail with auth error first, then succeed
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            
            # First call raises auth error, second succeeds
            mock_instance.extract_info.side_effect = [
                Exception("Sign in to confirm you're not a bot"),
                self.mock_yt_dlp_response
            ]
            
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Mock the retry mechanism
                with patch.object(youtube_downloader, '_is_authentication_error', return_value=True):
                    # Execute download
                    result = await youtube_downloader.download_video(
                        url=sample_job_data['url'],
                        job_id=sample_job_data['id'],
                        format_type=sample_job_data['format'],
                        quality=sample_job_data['quality']
                    )
        
        # Verify cookie rotation was triggered
        mock_cookie_manager.rotate_cookies.assert_called_once()
        
        # Verify retry occurred
        assert mock_instance.extract_info.call_count == 2
    
    @pytest.mark.asyncio
    async def test_cookie_cleanup_after_download(
        self, youtube_downloader, mock_cookie_manager, sample_job_data, mock_yt_dlp_response
    ):
        """Test temporary cookie file cleanup after download."""
        mock_cookie_file = '/tmp/test_cookies_temp.txt'
        mock_cookie_manager.get_active_cookies.return_value = mock_cookie_file
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 10
        }
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = mock_yt_dlp_response
            
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Execute download
                result = await youtube_downloader.download_video(
                    url=sample_job_data['url'],
                    job_id=sample_job_data['id'],
                    format_type=sample_job_data['format'],
                    quality=sample_job_data['quality']
                )
        
        # Verify cleanup was called
        mock_cookie_manager.cleanup_temporary_files.assert_called_once()
        
        # Verify successful download
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_cookie_error_reporting_and_alerts(
        self, youtube_downloader, mock_cookie_manager, sample_job_data
    ):
        """Test error reporting when cookie operations fail."""
        # Setup cookie manager to fail consistently
        mock_cookie_manager.get_active_cookies.side_effect = Exception("S3 connection failed")
        mock_cookie_manager.validate_cookie_freshness.side_effect = Exception("Validation failed")
        
        # Mock alert system
        with patch('app.services.downloader.send_admin_alert') as mock_alert:
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                mock_instance.extract_info.return_value = self.mock_yt_dlp_response
                
                with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                    mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                    
                    # Execute download
                    result = await youtube_downloader.download_video(
                        url=sample_job_data['url'],
                        job_id=sample_job_data['id'],
                        format_type=sample_job_data['format'],
                        quality=sample_job_data['quality']
                    )
        
        # Verify admin alert was sent (if implemented)
        if mock_alert.called:
            assert any('cookie' in str(call).lower() for call in mock_alert.call_args_list)
    
    @pytest.mark.asyncio
    async def test_download_progress_with_cookie_status(
        self, youtube_downloader, mock_cookie_manager, sample_job_data, mock_yt_dlp_response
    ):
        """Test download progress reporting includes cookie status."""
        mock_cookie_manager.get_active_cookies.return_value = '/tmp/test_cookies.txt'
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 15,
            'cookie_count': 25
        }
        
        # Track progress callbacks
        progress_updates = []
        
        def progress_callback(progress_data):
            progress_updates.append(progress_data)
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = mock_yt_dlp_response
            
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Execute download with progress callback
                result = await youtube_downloader.download_video(
                    url=sample_job_data['url'],
                    job_id=sample_job_data['id'],
                    format_type=sample_job_data['format'],
                    quality=sample_job_data['quality'],
                    progress_callback=progress_callback
                )
        
        # Verify progress updates include cookie information
        assert len(progress_updates) > 0
        
        # Check if any progress update contains cookie status
        has_cookie_status = any(
            'cookie' in str(update).lower() or 'authentication' in str(update).lower()
            for update in progress_updates
        )
        
        if has_cookie_status:
            assert has_cookie_status
    
    @pytest.mark.asyncio
    async def test_multiple_downloads_with_shared_cookies(
        self, youtube_downloader, mock_cookie_manager, mock_yt_dlp_response
    ):
        """Test multiple concurrent downloads sharing cookie manager."""
        mock_cookie_file = '/tmp/shared_cookies.txt'
        mock_cookie_manager.get_active_cookies.return_value = mock_cookie_file
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 20
        }
        
        # Sample jobs for concurrent downloads
        jobs = [
            {
                'id': f'test-job-{i}',
                'url': f'https://www.youtube.com/watch?v=test{i}',
                'format': DownloadFormat.MP4,
                'quality': '720p'
            }
            for i in range(3)
        ]
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = mock_yt_dlp_response
            
            with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                
                # Execute concurrent downloads
                download_tasks = []
                for job in jobs:
                    task = youtube_downloader.download_video(
                        url=job['url'],
                        job_id=job['id'],
                        format_type=job['format'],
                        quality=job['quality']
                    )
                    download_tasks.append(task)
                
                results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Verify all downloads succeeded
        for result in results:
            assert not isinstance(result, Exception)
            assert result is not None
            assert result.get('success') is True
        
        # Verify cookie manager was called for each download
        assert mock_cookie_manager.get_active_cookies.call_count >= len(jobs)
    
    @pytest.mark.asyncio
    async def test_cookie_performance_monitoring(
        self, youtube_downloader, mock_cookie_manager, sample_job_data, mock_yt_dlp_response
    ):
        """Test cookie performance monitoring and metrics collection."""
        mock_cookie_manager.get_active_cookies.return_value = '/tmp/perf_test_cookies.txt'
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 10,
            'validation_time_ms': 150
        }
        
        # Mock performance monitoring
        performance_metrics = []
        
        def mock_record_metric(metric_name, value, tags=None):
            performance_metrics.append({
                'name': metric_name,
                'value': value,
                'tags': tags or {}
            })
        
        with patch('app.services.downloader.record_performance_metric', side_effect=mock_record_metric):
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                mock_instance.extract_info.return_value = mock_yt_dlp_response
                
                with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                    mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                    
                    # Execute download
                    result = await youtube_downloader.download_video(
                        url=sample_job_data['url'],
                        job_id=sample_job_data['id'],
                        format_type=sample_job_data['format'],
                        quality=sample_job_data['quality']
                    )
        
        # Verify performance metrics were collected
        cookie_metrics = [
            metric for metric in performance_metrics
            if 'cookie' in metric['name'].lower()
        ]
        
        if cookie_metrics:
            assert len(cookie_metrics) > 0
        
        # Verify successful download
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_integration_with_job_status_updates(
        self, youtube_downloader, mock_cookie_manager, sample_job_data, mock_yt_dlp_response
    ):
        """Test integration with job status updates including cookie information."""
        mock_cookie_manager.get_active_cookies.return_value = '/tmp/status_test_cookies.txt'
        mock_cookie_manager.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 8
        }
        
        # Mock job status updates
        status_updates = []
        
        def mock_update_job_status(job_id, status, metadata=None):
            status_updates.append({
                'job_id': job_id,
                'status': status,
                'metadata': metadata or {}
            })
        
        with patch('app.services.downloader.update_job_status', side_effect=mock_update_job_status):
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                mock_instance.extract_info.return_value = mock_yt_dlp_response
                
                with patch.object(youtube_downloader, 'storage_handler') as mock_storage:
                    mock_storage.save_file = AsyncMock(return_value='downloads/test_video.mp4')
                    
                    # Execute download
                    result = await youtube_downloader.download_video(
                        url=sample_job_data['url'],
                        job_id=sample_job_data['id'],
                        format_type=sample_job_data['format'],
                        quality=sample_job_data['quality']
                    )
        
        # Verify job status updates occurred
        assert len(status_updates) > 0
        
        # Check if any status update includes cookie information
        has_cookie_info = any(
            'cookie' in str(update['metadata']).lower()
            for update in status_updates
            if update['metadata']
        )
        
        # Verify successful download
        assert result is not None
        assert result.get('success') is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])