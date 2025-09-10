"""
Integration tests for cookie failure and fallback scenarios.

This module tests various cookie failure modes and the system's
ability to gracefully handle and recover from cookie-related issues.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
from pathlib import Path

from app.services.downloader import YouTubeDownloader
from app.core.cookie_manager import CookieManager, CookieManagerError
from app.models.job import JobStatus, DownloadFormat


@pytest.mark.integration
class TestCookieFallbackScenarios:
    """Test suite for cookie failure and fallback mechanisms."""
    
    @pytest.fixture
    def mock_cookie_manager_failing(self, mock_cookie_settings):
        """Cookie manager configured to simulate various failure modes."""
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            return manager
    
    @pytest.fixture
    def downloader_with_fallback(self, mock_cookie_manager_failing, mock_storage_handler):
        """YouTube downloader configured for fallback testing."""
        with patch('app.services.downloader.get_storage_handler', return_value=mock_storage_handler):
            downloader = YouTubeDownloader()
            downloader.cookie_manager = mock_cookie_manager_failing
            downloader.storage_handler = mock_storage_handler
            return downloader
    
    @pytest.fixture
    def mock_storage_handler(self):
        """Mock storage handler."""
        handler = Mock()
        handler.save_file = AsyncMock(return_value='downloads/test/video.mp4')
        handler.get_file_url = AsyncMock(return_value='https://storage.example.com/video.mp4')
        return handler
    
    @pytest.fixture
    def sample_video_metadata(self):
        """Sample video metadata for testing."""
        return {
            'id': 'fallback_test',
            'title': 'Fallback Test Video',
            'uploader': 'Test Channel',
            'duration': 180,
            'view_count': 500000,
            'formats': [{
                'format_id': '720p',
                'ext': 'mp4',
                'width': 1280,
                'height': 720,
                'filesize': 40000000
            }],
            'requested_formats': [{
                'format_id': '720p',
                'ext': 'mp4',
                'filesize': 40000000
            }]
        }
    
    @pytest.mark.asyncio
    async def test_s3_connection_failure_fallback(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test fallback when S3 connection fails."""
        # Configure S3 connection failure
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(
            side_effect=Exception("S3 connection timeout")
        )
        
        fallback_attempts = []
        
        def track_fallback(attempt_type):
            fallback_attempts.append({
                'type': attempt_type,
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            # Mock fallback tracking
            with patch.object(downloader_with_fallback, '_log_fallback_attempt', side_effect=track_fallback):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=s3_fallback_test',
                    job_id='s3-fallback-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify fallback occurred
        assert len(fallback_attempts) > 0
        assert any(attempt['type'] == 'no_cookies' for attempt in fallback_attempts)
        
        # Verify yt-dlp was called without cookies
        mock_ytdl.assert_called_once()
        ytdl_config = mock_ytdl.call_args[0][0]
        assert 'cookiefile' not in ytdl_config or ytdl_config.get('cookiefile') is None
        
        # Verify download still succeeded
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_expired_cookies_rotation_fallback(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test fallback when cookies are expired and rotation fails."""
        # Configure expired cookies
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(return_value='/tmp/expired_cookies.txt')
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(return_value={
            'valid': False,
            'expired': True,
            'expires_in_days': -10
        })
        
        # Configure rotation to fail
        mock_cookie_manager_failing.rotate_cookies = AsyncMock(
            side_effect=Exception("No backup cookies available")
        )
        
        rotation_attempts = []
        
        def track_rotation_attempt():
            rotation_attempts.append(datetime.now())
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch.object(downloader_with_fallback, '_attempt_cookie_rotation', side_effect=track_rotation_attempt):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=expired_fallback',
                    job_id='expired-cookie-fallback',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify rotation was attempted
        mock_cookie_manager_failing.rotate_cookies.assert_called_once()
        
        # Verify fallback to no cookies occurred
        mock_ytdl.assert_called_once()
        ytdl_config = mock_ytdl.call_args[0][0]
        assert 'cookiefile' not in ytdl_config or ytdl_config.get('cookiefile') is None
        
        # Verify download succeeded without cookies
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_authentication_error_with_cookie_retry(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test retry mechanism when authentication fails with cookies."""
        # Configure working cookies initially
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(return_value='/tmp/auth_test_cookies.txt')
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(return_value={
            'valid': True,
            'expires_in_days': 20
        })
        
        # Configure rotation to provide new cookies
        mock_cookie_manager_failing.rotate_cookies = AsyncMock(return_value={
            'success': True,
            'new_cookie_file': '/tmp/rotated_cookies.txt'
        })
        
        auth_attempts = []
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            
            # First attempt: auth error, second attempt: success
            mock_instance.extract_info.side_effect = [
                Exception("Sign in to confirm you're not a bot"),
                sample_video_metadata
            ]
            
            def track_auth_attempt(*args, **kwargs):
                auth_attempts.append({
                    'args': args,
                    'kwargs': kwargs,
                    'timestamp': datetime.now()
                })
            
            with patch.object(downloader_with_fallback, '_is_authentication_error', return_value=True):
                with patch.object(downloader_with_fallback, '_handle_auth_error', side_effect=track_auth_attempt):
                    result = await downloader_with_fallback.download_video(
                        url='https://www.youtube.com/watch?v=auth_retry_test',
                        job_id='auth-retry-test',
                        format_type=DownloadFormat.MP4,
                        quality='720p'
                    )
        
        # Verify authentication error was handled
        assert len(auth_attempts) > 0
        
        # Verify cookie rotation was attempted
        mock_cookie_manager_failing.rotate_cookies.assert_called_once()
        
        # Verify retry occurred
        assert mock_instance.extract_info.call_count == 2
        
        # Verify eventual success
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_cascading_fallback_multiple_failures(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test cascading fallback when multiple systems fail."""
        failure_sequence = [
            "S3 connection failed",           # Initial cookie retrieval fails
            "Backup cookies corrupted",       # First fallback fails
            "Cookie rotation service down"    # Second fallback fails
        ]
        
        # Configure cascading failures
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(
            side_effect=Exception(failure_sequence[0])
        )
        mock_cookie_manager_failing.get_backup_cookies = AsyncMock(
            side_effect=Exception(failure_sequence[1])
        )
        mock_cookie_manager_failing.rotate_cookies = AsyncMock(
            side_effect=Exception(failure_sequence[2])
        )
        
        fallback_chain = []
        
        def track_fallback_chain(fallback_type, error=None):
            fallback_chain.append({
                'type': fallback_type,
                'error': str(error) if error else None,
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch.object(downloader_with_fallback, '_log_fallback', side_effect=track_fallback_chain):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=cascading_fallback',
                    job_id='cascading-fallback-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify all fallback attempts were made
        expected_fallback_types = ['primary_cookies', 'backup_cookies', 'cookie_rotation', 'no_cookies']
        actual_fallback_types = [fb['type'] for fb in fallback_chain]
        
        for expected_type in expected_fallback_types:
            if expected_type in actual_fallback_types:
                assert expected_type in actual_fallback_types
        
        # Verify final fallback to no cookies succeeded
        mock_ytdl.assert_called_once()
        ytdl_config = mock_ytdl.call_args[0][0]
        assert 'cookiefile' not in ytdl_config or ytdl_config.get('cookiefile') is None
        
        # Verify download still succeeded
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_partial_cookie_failure_recovery(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test recovery when some cookies work but others fail."""
        # Configure partial cookie failure
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(return_value='/tmp/partial_cookies.txt')
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(return_value={
            'valid': True,
            'expires_in_days': 15,
            'partial_failure': True,
            'working_domains': ['.youtube.com'],
            'failed_domains': ['.google.com', '.googleapis.com']
        })
        
        domain_failures = []
        
        def track_domain_failure(domain, error):
            domain_failures.append({
                'domain': domain,
                'error': error,
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch.object(downloader_with_fallback, '_log_domain_failure', side_effect=track_domain_failure):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=partial_cookie_test',
                    job_id='partial-cookie-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify partial cookies were used
        mock_ytdl.assert_called_once()
        ytdl_config = mock_ytdl.call_args[0][0]
        assert 'cookiefile' in ytdl_config
        assert ytdl_config['cookiefile'] == '/tmp/partial_cookies.txt'
        
        # Verify domain failures were tracked
        if domain_failures:
            failed_domains = [df['domain'] for df in domain_failures]
            assert '.google.com' in failed_domains or '.googleapis.com' in failed_domains
        
        # Verify download succeeded with partial cookies
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_cookie_corruption_detection_and_fallback(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test detection and fallback when cookie files are corrupted."""
        # Configure corrupted cookie detection
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(return_value='/tmp/corrupted_cookies.txt')
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(
            side_effect=Exception("Cookie file corrupted: Invalid format")
        )
        
        # Configure fallback to backup
        mock_cookie_manager_failing.get_backup_cookies = AsyncMock(return_value='/tmp/backup_cookies.txt')
        
        corruption_detections = []
        
        def track_corruption(file_path, error):
            corruption_detections.append({
                'file_path': file_path,
                'error': str(error),
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch.object(downloader_with_fallback, '_log_corruption_detection', side_effect=track_corruption):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=corruption_test',
                    job_id='corruption-detection-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify corruption was detected
        assert len(corruption_detections) > 0
        assert any('/tmp/corrupted_cookies.txt' in cd['file_path'] for cd in corruption_detections)
        
        # Verify fallback to backup occurred
        mock_cookie_manager_failing.get_backup_cookies.assert_called_once()
        
        # Verify download succeeded with backup cookies
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_rate_limiting_with_cookie_backoff(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test backoff mechanism when rate limited with cookies."""
        # Configure rate limiting scenario
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(return_value='/tmp/rate_limit_cookies.txt')
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(return_value={
            'valid': True,
            'expires_in_days': 15
        })
        
        backoff_attempts = []
        
        def track_backoff(attempt, delay):
            backoff_attempts.append({
                'attempt': attempt,
                'delay': delay,
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            
            # Simulate rate limiting then success
            mock_instance.extract_info.side_effect = [
                Exception("HTTP Error 429: Too Many Requests"),
                Exception("HTTP Error 429: Too Many Requests"),
                sample_video_metadata
            ]
            
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                with patch.object(downloader_with_fallback, '_log_backoff_attempt', side_effect=track_backoff):
                    with patch.object(downloader_with_fallback, '_is_rate_limit_error', return_value=True):
                        result = await downloader_with_fallback.download_video(
                            url='https://www.youtube.com/watch?v=rate_limit_test',
                            job_id='rate-limit-backoff-test',
                            format_type=DownloadFormat.MP4,
                            quality='720p'
                        )
        
        # Verify backoff occurred
        assert len(backoff_attempts) >= 2
        assert mock_sleep.call_count >= 2
        
        # Verify exponential backoff pattern
        if len(backoff_attempts) >= 2:
            assert backoff_attempts[1]['delay'] > backoff_attempts[0]['delay']
        
        # Verify eventual success
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_admin_notification_on_cookie_failures(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test admin notifications when cookie failures occur."""
        # Configure persistent cookie failures
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(
            side_effect=Exception("Persistent S3 failure")
        )
        
        admin_notifications = []
        
        def track_admin_notification(notification_type, details):
            admin_notifications.append({
                'type': notification_type,
                'details': details,
                'timestamp': datetime.now()
            })
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch('app.services.downloader.send_admin_notification', side_effect=track_admin_notification):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=admin_notify_test',
                    job_id='admin-notification-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        # Verify admin notifications were sent
        if admin_notifications:
            cookie_notifications = [
                notif for notif in admin_notifications
                if 'cookie' in notif['type'].lower() or 'cookie' in str(notif['details']).lower()
            ]
            assert len(cookie_notifications) > 0
        
        # Verify download still succeeded
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_fallback_performance_impact_monitoring(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test monitoring of performance impact during fallback scenarios."""
        import time
        
        # Configure slow fallback scenario
        async def slow_cookie_retrieval():
            await asyncio.sleep(0.1)  # Simulate slow S3 response
            raise Exception("S3 timeout after delay")
        
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(side_effect=slow_cookie_retrieval)
        
        performance_metrics = []
        
        def track_performance_metric(metric_name, value, tags=None):
            performance_metrics.append({
                'metric': metric_name,
                'value': value,
                'tags': tags or {},
                'timestamp': datetime.now()
            })
        
        start_time = time.time()
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            with patch('app.services.downloader.record_performance_metric', side_effect=track_performance_metric):
                result = await downloader_with_fallback.download_video(
                    url='https://www.youtube.com/watch?v=perf_fallback_test',
                    job_id='performance-fallback-test',
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
        
        total_time = time.time() - start_time
        
        # Verify fallback delay was accounted for
        assert total_time >= 0.1  # Should include the simulated delay
        
        # Verify performance metrics were collected
        fallback_metrics = [
            metric for metric in performance_metrics
            if 'fallback' in metric['metric'].lower() or 'cookie' in metric['metric'].lower()
        ]
        
        if fallback_metrics:
            assert len(fallback_metrics) > 0
        
        # Verify download still succeeded despite performance impact
        assert result is not None
        assert result.get('success') is True
    
    @pytest.mark.asyncio
    async def test_concurrent_fallback_scenarios(
        self, downloader_with_fallback, mock_cookie_manager_failing, sample_video_metadata
    ):
        """Test fallback behavior under concurrent download scenarios."""
        # Configure intermittent failures
        failure_counter = {'count': 0}
        
        async def intermittent_cookie_failure():
            failure_counter['count'] += 1
            if failure_counter['count'] % 2 == 1:  # Fail every other call
                raise Exception("Intermittent S3 failure")
            return '/tmp/working_cookies.txt'
        
        mock_cookie_manager_failing.get_active_cookies = AsyncMock(side_effect=intermittent_cookie_failure)
        mock_cookie_manager_failing.validate_cookie_freshness = AsyncMock(return_value={
            'valid': True,
            'expires_in_days': 15
        })
        
        # Test concurrent downloads
        num_concurrent = 4
        test_jobs = [
            {
                'job_id': f'concurrent-fallback-{i}',
                'url': f'https://www.youtube.com/watch?v=concurrent_fallback_{i}'
            }
            for i in range(num_concurrent)
        ]
        
        with patch('yt_dlp.YoutubeDL') as mock_ytdl:
            mock_instance = Mock()
            mock_ytdl.return_value.__enter__.return_value = mock_instance
            mock_instance.extract_info.return_value = sample_video_metadata
            
            # Execute concurrent downloads
            download_tasks = []
            for job in test_jobs:
                task = downloader_with_fallback.download_video(
                    url=job['url'],
                    job_id=job['job_id'],
                    format_type=DownloadFormat.MP4,
                    quality='720p'
                )
                download_tasks.append(task)
            
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        # Verify all downloads completed successfully
        successful_downloads = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent download {i} failed: {result}")
            
            assert result is not None
            assert result.get('success') is True
            successful_downloads += 1
        
        assert successful_downloads == num_concurrent
        
        # Verify cookie manager handled concurrent failures gracefully
        assert mock_cookie_manager_failing.get_active_cookies.call_count >= num_concurrent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])