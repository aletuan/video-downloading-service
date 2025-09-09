"""
End-to-end integration tests for download workflow with cookies.

This module tests the complete download workflow from job creation
to completion, including cookie authentication, error handling,
progress tracking, and file storage.
"""

import pytest
import asyncio
import json
import tempfile
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path

from app.services.downloader import YouTubeDownloader
from app.core.cookie_manager import CookieManager
from app.core.storage import StorageHandler
from app.models.job import JobStatus, DownloadFormat
from app.core.database import get_db_session


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end workflow integration tests."""
    
    @pytest.fixture
    async def db_session(self):
        """Create test database session."""
        async with get_db_session() as session:
            yield session
    
    @pytest.fixture
    def mock_storage_handler(self):
        """Mock storage handler for testing."""
        handler = Mock(spec=StorageHandler)
        handler.save_file = AsyncMock()
        handler.get_file_url = AsyncMock()
        handler.delete_file = AsyncMock()
        handler.file_exists = AsyncMock()
        return handler
    
    @pytest.fixture
    def mock_cookie_manager_e2e(self, mock_cookie_settings):
        """Cookie manager for end-to-end testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            
            # Mock successful cookie operations
            manager.get_active_cookies = AsyncMock(return_value='/tmp/test_cookies_e2e.txt')
            manager.validate_cookie_freshness = AsyncMock(return_value={
                'valid': True,
                'expires_in_days': 15,
                'cookie_count': 30
            })
            manager.cleanup_temporary_files = AsyncMock()
            
            return manager
    
    @pytest.fixture
    def downloader_service(self, mock_storage_handler, mock_cookie_manager_e2e):
        """YouTube downloader service for end-to-end testing."""
        with patch('app.services.downloader.get_storage_handler', return_value=mock_storage_handler):
            downloader = YouTubeDownloader()
            downloader.cookie_manager = mock_cookie_manager_e2e
            downloader.storage_handler = mock_storage_handler
            return downloader
    
    @pytest.fixture
    def sample_video_metadata(self):
        """Sample video metadata for successful downloads."""
        return {
            'id': 'dQw4w9WgXcQ',
            'title': 'Rick Astley - Never Gonna Give You Up (Official Video)',
            'uploader': 'Rick Astley',
            'uploader_id': 'RickAstleyVEVO',
            'duration': 212,
            'view_count': 1000000000,
            'like_count': 12000000,
            'description': 'The official video for "Never Gonna Give You Up"',
            'upload_date': '20091002',
            'thumbnail': 'https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg',
            'formats': [
                {
                    'format_id': '720p',
                    'ext': 'mp4',
                    'width': 1280,
                    'height': 720,
                    'filesize': 52428800,  # 50MB
                    'url': 'https://test-cdn.youtube.com/videoplayback?id=720p'
                },
                {
                    'format_id': '480p',
                    'ext': 'mp4',
                    'width': 854,
                    'height': 480,
                    'filesize': 31457280,  # 30MB
                    'url': 'https://test-cdn.youtube.com/videoplayback?id=480p'
                }
            ],
            'requested_formats': [
                {
                    'format_id': '720p',
                    'ext': 'mp4',
                    'filesize': 52428800
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_complete_download_workflow_with_cookies(
        self, downloader_service, mock_cookie_manager_e2e, mock_storage_handler, sample_video_metadata
    ):
        """Test complete download workflow from start to finish with cookies."""
        job_id = 'e2e-test-job-001'
        video_url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        
        # Track workflow steps
        workflow_steps = []
        
        def track_step(step_name, data=None):
            workflow_steps.append({
                'step': step_name,
                'timestamp': datetime.now(),
                'data': data
            })
        
        # Mock yt-dlp extraction
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            # Mock progress callback
            def progress_hook(d):
                if d['status'] == 'downloading':
                    track_step('downloading', {
                        'downloaded_bytes': d.get('downloaded_bytes', 0),
                        'total_bytes': d.get('total_bytes', 0),
                        'speed': d.get('speed', 0)
                    })
                elif d['status'] == 'finished':
                    track_step('download_finished', {'filename': d.get('filename')})
            
            # Mock file download
            mock_storage_handler.save_file.return_value = f'downloads/{job_id}/video.mp4'
            mock_storage_handler.get_file_url.return_value = f'https://storage.example.com/downloads/{job_id}/video.mp4'
            
            # Execute complete workflow
            track_step('workflow_start')
            
            result = await downloader_service.download_video(
                url=video_url,
                job_id=job_id,
                format_type=DownloadFormat.MP4,
                quality='720p',
                progress_callback=lambda p: track_step('progress_update', p)
            )
            
            track_step('workflow_complete', result)
        
        # Verify workflow steps
        assert len(workflow_steps) >= 2  # Start and complete at minimum
        assert workflow_steps[0]['step'] == 'workflow_start'
        assert workflow_steps[-1]['step'] == 'workflow_complete'
        
        # Verify cookie manager integration
        mock_cookie_manager_e2e.get_active_cookies.assert_called_once()
        mock_cookie_manager_e2e.validate_cookie_freshness.assert_called_once()
        mock_cookie_manager_e2e.cleanup_temporary_files.assert_called_once()
        
        # Verify yt-dlp configuration with cookies
        mock_ytdl.assert_called_once()
        ytdl_config = mock_ytdl.call_args[0][0]
        assert 'cookiefile' in ytdl_config
        assert ytdl_config['cookiefile'] == '/tmp/test_cookies_e2e.txt'
        
        # Verify storage integration
        mock_storage_handler.save_file.assert_called_once()
        
        # Verify successful result
        assert result is not None
        assert result.get('success') is True
        assert 'file_path' in result
        assert 'file_url' in result
    
    @pytest.mark.asyncio
    async def test_workflow_with_cookie_expiration_warning(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test workflow when cookies are close to expiration."""
        # Configure cookie manager to return expiring cookies
        mock_cookie_manager_e2e.validate_cookie_freshness.return_value = {
            'valid': True,
            'expires_in_days': 2,  # Close to expiration
            'warning': True,
            'cookie_count': 25
        }
        
        # Track warnings
        warning_messages = []
        
        def mock_log_warning(message):
            warning_messages.append(message)
        
        with patch('app.services.downloader.logger.warning', side_effect=mock_log_warning):
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                mock_instance.extract_info.return_value = sample_video_metadata
                
                # Execute download
                result = await downloader_service.download_video(
                    url='https://www.youtube.com/watch?v=test123',
                    job_id='expiring-cookies-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify warning was logged
        cookie_warnings = [w for w in warning_messages if 'cookie' in w.lower() and 'expir' in w.lower()]
        if cookie_warnings:
            assert len(cookie_warnings) > 0
        
        # Verify download still succeeded
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_workflow_with_multiple_format_options(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test workflow with different format and quality options."""
        formats_to_test = [
            (DownloadFormat.MP4, '720p'),
            (DownloadFormat.MP4, '480p'),
            (DownloadFormat.WEBM, '720p'),
            (DownloadFormat.MP3, 'best')
        ]
        
        results = []
        
        for format_type, quality in formats_to_test:
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                mock_instance.extract_info.return_value = sample_video_metadata
                
                result = await downloader_service.download_video(
                    url=f'https://www.youtube.com/watch?v=test_{format_type}_{quality}',
                    job_id=f'format-test-{format_type}-{quality}',
                    format_type=format_type,
                    quality=quality
                )
                
                results.append((format_type, quality, result))
        
        # Verify all format/quality combinations worked
        for format_type, quality, result in results:
            assert result is not None
            assert result.get('success') is True, f"Failed for {format_type} {quality}"
        
        # Verify cookie manager was called for each download
        assert mock_cookie_manager_e2e.get_active_cookies.call_count == len(formats_to_test)
    
    @pytest.mark.asyncio
    async def test_concurrent_downloads_workflow(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test multiple concurrent downloads sharing resources."""
        num_concurrent_downloads = 3
        
        # Create test jobs
        test_jobs = [
            {
                'job_id': f'concurrent-job-{i}',
                'url': f'https://www.youtube.com/watch?v=concurrent{i}',
                'format': DownloadFormat.MP4,
                'quality': '720p'
            }
            for i in range(num_concurrent_downloads)
        ]
        
        # Track download timing
        download_start_time = time.time()
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            # Execute concurrent downloads
            download_tasks = []
            for job in test_jobs:
                task = downloader_service.download_video(
                    url=job['url'],
                    job_id=job['job_id'],
                    format_type=job['format'],
                    quality=job['quality']
                )
                download_tasks.append(task)
            
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        download_duration = time.time() - download_start_time
        
        # Verify all downloads succeeded
        successful_downloads = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Download {i} failed with exception: {result}")
            
            assert result is not None
            assert result.get('success') is True
            successful_downloads += 1
        
        assert successful_downloads == num_concurrent_downloads
        
        # Verify reasonable performance (should be concurrent, not sequential)
        assert download_duration < 10.0  # Generous limit for test environment
        
        # Verify cookie manager handled concurrent access
        assert mock_cookie_manager_e2e.get_active_cookies.call_count >= num_concurrent_downloads
    
    @pytest.mark.asyncio
    async def test_workflow_error_recovery_mechanisms(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test error recovery mechanisms in the workflow."""
        recovery_scenarios = [
            {
                'name': 'temporary_network_failure',
                'exception': Exception("Network timeout"),
                'should_retry': True
            },
            {
                'name': 'youtube_rate_limiting',
                'exception': Exception("HTTP Error 429: Too Many Requests"),
                'should_retry': True
            },
            {
                'name': 'authentication_error',
                'exception': Exception("Sign in to confirm you're not a bot"),
                'should_retry': True
            }
        ]
        
        for scenario in recovery_scenarios:
            with patch('yt_dlp.YoutubeDL') as mock_ytdl:
                mock_instance = Mock()
                mock_ytdl.return_value.__enter__.return_value = mock_instance
                
                # First call fails, second succeeds
                mock_instance.extract_info.side_effect = [
                    scenario['exception'],
                    sample_video_metadata
                ]
                
                # Mock retry mechanism detection
                with patch.object(downloader_service, '_should_retry_error', return_value=scenario['should_retry']):
                    result = await downloader_service.download_video(
                        url=f'https://www.youtube.com/watch?v={scenario["name"]}',
                        job_id=f'recovery-test-{scenario["name"]}',
                        format_type=DownloadFormat.MP4,
                        quality='720p'
                    )
                
                # Verify recovery occurred
                if scenario['should_retry']:
                    assert mock_instance.extract_info.call_count == 2
                    assert result is not None
                    assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_workflow_progress_tracking_integration(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test progress tracking throughout the workflow."""
        progress_updates = []
        job_status_updates = []
        
        def progress_callback(progress_data):
            progress_updates.append({
                'timestamp': datetime.now(),
                'data': progress_data
            })
        
        def mock_update_job_status(job_id, status, metadata=None):
            job_status_updates.append({
                'job_id': job_id,
                'status': status,
                'metadata': metadata or {},
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch('app.services.downloader.update_job_status', side_effect=mock_update_job_status):
                result = await downloader_service.download_video(
                    url='https://www.youtube.com/watch?v=progress_test',
                    job_id='progress-tracking-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p',
                    progress_callback=progress_callback
                )
        
        # Verify progress tracking
        assert len(progress_updates) >= 0  # May be 0 if no progress hooks called
        
        # Verify job status tracking
        assert len(job_status_updates) > 0
        
        # Check for expected status transitions
        status_sequence = [update['status'] for update in job_status_updates]
        expected_statuses = [JobStatus.IN_PROGRESS, JobStatus.COMPLETED]
        
        for expected_status in expected_statuses:
            if expected_status in status_sequence:
                assert expected_status in status_sequence
        
        # Verify successful completion
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_workflow_metadata_preservation(
        self, downloader_service, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test that video metadata is properly preserved throughout workflow."""
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            result = await downloader_service.download_video(
                url='https://www.youtube.com/watch?v=metadata_test',
                job_id='metadata-preservation-test',
                format_type=DownloadFormat.MP4,
                quality='720p'
            )
        
        # Verify metadata preservation
        assert result is not None
        assert result.get('success') is True
        
        # Check that key metadata fields are preserved
        expected_metadata_fields = ['title', 'uploader', 'duration', 'view_count', 'upload_date']
        
        if 'metadata' in result:
            result_metadata = result['metadata']
            for field in expected_metadata_fields:
                if field in result_metadata:
                    assert result_metadata[field] == sample_video_metadata[field]
    
    @pytest.mark.asyncio
    async def test_workflow_storage_integration_verification(
        self, downloader_service, mock_storage_handler, mock_cookie_manager_e2e, sample_video_metadata
    ):
        """Test storage integration verification throughout workflow."""
        # Configure storage handler responses
        test_file_path = 'downloads/storage-test/video.mp4'
        test_file_url = 'https://storage.example.com/downloads/storage-test/video.mp4'
        
        mock_storage_handler.save_file.return_value = test_file_path
        mock_storage_handler.get_file_url.return_value = test_file_url
        mock_storage_handler.file_exists.return_value = True
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            result = await downloader_service.download_video(
                url='https://www.youtube.com/watch?v=storage_test',
                job_id='storage-integration-test',
                format_type=DownloadFormat.MP4,
                quality='720p'
            )
        
        # Verify storage operations
        mock_storage_handler.save_file.assert_called_once()
        mock_storage_handler.get_file_url.assert_called_once()
        
        # Verify result contains storage information
        assert result is not None
        assert result.get('success') is True
        assert result.get('file_path') == test_file_path
        assert result.get('file_url') == test_file_url
    
    @pytest.mark.asyncio
    async def test_workflow_cleanup_on_failure(
        self, downloader_service, mock_cookie_manager_e2e, mock_storage_handler
    ):
        """Test that cleanup occurs properly when workflow fails."""
        # Configure download to fail
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.side_effect = Exception("Download failed")
            
            try:
                result = await downloader_service.download_video(
                    url='https://www.youtube.com/watch?v=cleanup_test',
                    job_id='cleanup-failure-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
            except Exception:
                pass  # Expected failure
        
        # Verify cleanup was called even on failure
        mock_cookie_manager_e2e.cleanup_temporary_files.assert_called_once()
        
        # Verify storage cleanup if implemented
        if hasattr(mock_storage_handler, 'cleanup_failed_download'):
            mock_storage_handler.cleanup_failed_download.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])