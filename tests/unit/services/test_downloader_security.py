"""
Security tests for the YouTube downloader service.

Tests security vulnerabilities and fixes:
- Path traversal attacks through job_id sanitization  
- Memory leak prevention through proper cleanup
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.downloader import YouTubeDownloader


class TestDownloaderSecurity:
    """Test security aspects of the downloader service."""

    @pytest.fixture
    def downloader(self):
        """Create a downloader instance for testing."""
        with patch('app.services.downloader.get_storage_handler') as mock_storage:
            mock_storage_handler = AsyncMock()
            mock_storage_handler.save_file = AsyncMock()
            mock_storage_handler.get_file_url = AsyncMock(return_value="http://example.com/file")
            mock_storage.return_value = mock_storage_handler
            
            downloader = YouTubeDownloader()
            downloader.storage_handler = mock_storage_handler
            return downloader

    def test_sanitize_job_id_prevents_path_traversal(self, downloader):
        """Test that job ID sanitization prevents path traversal attacks."""
        # Test various path traversal attempts
        test_cases = [
            ("../../../etc/passwd", "etcpasswd"),
            ("..\\..\\windows\\system32", "windowssystem32"),
            ("normal-job-123", "normal-job-123"),
            ("job_with_underscores", "job_with_underscores"),
            ("job/with/slashes", "jobwithslashes"),
            ("job\\with\\backslashes", "jobwithbackslashes"),
            ("job<>:|?*", "job"),
            ("", "unknown"),  # Empty string should become 'unknown'
            ("a" * 100, "a" * 50),  # Long strings should be truncated
        ]
        
        for malicious_id, expected_safe_id in test_cases:
            safe_id = downloader._sanitize_job_id(malicious_id)
            assert safe_id == expected_safe_id
            assert len(safe_id) <= 50
            assert not any(char in safe_id for char in ['/', '\\', '..', '<', '>', ':', '|', '?', '*'])

    def test_sanitized_job_id_used_in_storage_keys(self, downloader):
        """Test that sanitized job IDs are used in storage key generation."""
        # Create a temporary file to test with
        with tempfile.NamedTemporaryFile(suffix='.mp4') as temp_file:
            temp_path = Path(temp_file.name)
            
            # Mock file reading
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = b'fake video data'
                
                # Test with malicious job ID
                malicious_job_id = "../../../etc/passwd"
                
                # Run the async function
                async def run_test():
                    storage_key = await downloader._store_file(temp_path, malicious_job_id, "video")
                    
                    # Check that the storage handler was called with a sanitized path
                    downloader.storage_handler.save_file.assert_called_once()
                    called_storage_key = downloader.storage_handler.save_file.call_args[0][0]
                    
                    # Verify the storage key uses sanitized job ID
                    assert "etcpasswd" in called_storage_key
                    assert "../" not in called_storage_key
                    assert "videos/etcpasswd/" in called_storage_key
                    
                asyncio.run(run_test())

    def test_temp_directory_cleanup_in_success_case(self, downloader):
        """Test that temp directories are cleaned up on successful download."""
        with patch.object(downloader, 'extract_metadata') as mock_extract, \
             patch.object(downloader, '_configure_yt_dlp_options') as mock_configure, \
             patch.object(downloader, '_store_file') as mock_store, \
             patch.object(downloader, '_cleanup_temp_directory') as mock_cleanup, \
             patch('app.services.downloader.yt_dlp.YoutubeDL') as mock_ydl_class, \
             patch('asyncio.get_event_loop') as mock_loop:
            
            # Setup mocks
            mock_extract.return_value = {"title": "Test Video", "duration": 120}
            mock_configure.return_value = {}
            mock_store.return_value = "http://example.com/video.mp4"
            mock_cleanup.return_value = None
            
            # Mock YoutubeDL instance
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            mock_ydl.download = MagicMock()
            
            # Mock event loop
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor = mock_executor
            
            # Mock glob to return fake downloaded files
            with patch('pathlib.Path.glob') as mock_glob:
                mock_file = MagicMock()
                mock_file.suffix = '.mp4'
                mock_glob.return_value = [mock_file]
                
                # Mock mkdir and exists
                with patch('pathlib.Path.mkdir'), \
                     patch('pathlib.Path.exists', return_value=True):
                    
                    async def run_test():
                        from app.models.download import DownloadOptions
                        options = DownloadOptions()
                        
                        result = await downloader.download_video(
                            "test-job-123", 
                            "https://youtube.com/watch?v=test", 
                            options
                        )
                        
                        # Verify cleanup was called
                        mock_cleanup.assert_called_once()
                        assert result.success is True
                        
                    asyncio.run(run_test())

    def test_temp_directory_cleanup_in_failure_case(self, downloader):
        """Test that temp directories are cleaned up even when download fails."""
        with patch.object(downloader, 'extract_metadata') as mock_extract, \
             patch.object(downloader, '_cleanup_temp_directory') as mock_cleanup, \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.exists', return_value=True):
            
            # Make extract_metadata raise an exception
            mock_extract.side_effect = Exception("Download failed")
            mock_cleanup.return_value = None
            
            async def run_test():
                from app.models.download import DownloadOptions
                options = DownloadOptions()
                
                result = await downloader.download_video(
                    "test-job-123", 
                    "https://youtube.com/watch?v=test", 
                    options
                )
                
                # Verify cleanup was called even though download failed
                mock_cleanup.assert_called_once()
                assert result.success is False
                
            asyncio.run(run_test())

    def test_sanitized_job_id_used_in_temp_directory(self, downloader):
        """Test that sanitized job IDs are used for temp directory creation."""
        with patch.object(downloader, 'extract_metadata') as mock_extract, \
             patch.object(downloader, '_cleanup_temp_directory') as mock_cleanup, \
             patch('pathlib.Path.exists', return_value=True):
            
            # Make extract_metadata raise an exception to exit early
            mock_extract.side_effect = Exception("Early exit")
            mock_cleanup.return_value = None
            
            malicious_job_id = "../../../etc/passwd"
            
            with patch('pathlib.Path.mkdir') as mock_mkdir:
                async def run_test():
                    from app.models.download import DownloadOptions
                    options = DownloadOptions()
                    
                    await downloader.download_video(
                        malicious_job_id, 
                        "https://youtube.com/watch?v=test", 
                        options
                    )
                    
                    # Check that mkdir was called on the sanitized path
                    mock_mkdir.assert_called_once()
                    
                    # Verify cleanup was called with sanitized path
                    mock_cleanup.assert_called_once()
                    called_path = mock_cleanup.call_args[0][0]
                    
                    # The path should contain the sanitized job ID, not the malicious one
                    assert "etcpasswd" in str(called_path)
                    assert "../" not in str(called_path)
                    
                asyncio.run(run_test())