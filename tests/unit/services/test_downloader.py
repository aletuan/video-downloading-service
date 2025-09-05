import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call
from datetime import datetime
from yt_dlp.utils import DownloadError, ExtractorError

from app.services.downloader import DownloadProgress, YouTubeDownloader
from app.core.storage import LocalStorageHandler


class TestDownloadProgress:
    """Test cases for DownloadProgress class."""

    def test_download_progress_init(self):
        """Test DownloadProgress initialization."""
        callback = MagicMock()
        progress = DownloadProgress("job-123", callback)
        
        assert progress.job_id == "job-123"
        assert progress.progress_callback == callback
        assert progress.current_progress == 0.0

    def test_download_progress_init_no_callback(self):
        """Test DownloadProgress initialization without callback."""
        progress = DownloadProgress("job-456")
        
        assert progress.job_id == "job-456"
        assert progress.progress_callback is None
        assert progress.current_progress == 0.0

    def test_download_progress_downloading_with_total_bytes(self):
        """Test progress calculation with total_bytes."""
        callback = MagicMock()
        progress = DownloadProgress("job-123", callback)
        
        # Simulate download progress
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 1024000,  # 1MB
            'total_bytes': 5120000,       # 5MB
        }
        
        progress(progress_data)
        
        assert progress.current_progress == 20.0  # 1MB/5MB = 20%
        callback.assert_called_once_with(20.0, "Downloading: 20.0%")

    def test_download_progress_downloading_with_estimate(self):
        """Test progress calculation with total bytes estimate."""
        callback = MagicMock()
        progress = DownloadProgress("job-123", callback)
        
        # Simulate download progress with estimate
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 2560000,  # 2.5MB
            '_total_bytes_estimate': 10240000,  # 10MB estimate
        }
        
        progress(progress_data)
        
        assert progress.current_progress == 25.0  # 2.5MB/10MB = 25%
        callback.assert_called_once_with(25.0, "Downloading: 25.0%")

    def test_download_progress_downloading_with_fragments(self):
        """Test progress calculation with fragment info."""
        callback = MagicMock()
        progress = DownloadProgress("job-123", callback)
        
        # Simulate fragment-based download
        progress_data = {
            'status': 'downloading',
            'fragment_index': 25,
            'fragment_count': 100
        }
        
        progress(progress_data)
        
        assert progress.current_progress == 25.0  # 25/100 = 25%
        callback.assert_called_once_with(25.0, "Downloading: 25.0%")

    def test_download_progress_finished(self):
        """Test progress when download is finished."""
        callback = MagicMock()
        progress = DownloadProgress("job-123", callback)
        
        # Simulate finished download
        progress_data = {
            'status': 'finished',
            'filename': '/tmp/video.mp4'
        }
        
        progress(progress_data)
        
        assert progress.current_progress == 100.0
        callback.assert_called_once_with(100.0, "Download completed")

    def test_download_progress_no_callback(self):
        """Test progress without callback."""
        progress = DownloadProgress("job-123")
        
        # Should not raise exception
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 1024,
            'total_bytes': 2048
        }
        
        progress(progress_data)
        
        assert progress.current_progress == 50.0

    def test_download_progress_exception_handling(self):
        """Test progress hook handles exceptions gracefully."""
        callback = MagicMock(side_effect=Exception("Callback error"))
        progress = DownloadProgress("job-123", callback)
        
        progress_data = {
            'status': 'downloading',
            'downloaded_bytes': 1024,
            'total_bytes': 2048
        }
        
        # Should not raise exception
        progress(progress_data)
        
        # Progress should still be updated
        assert progress.current_progress == 50.0


class TestYouTubeDownloader:
    """Test cases for YouTubeDownloader class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_path:
            yield Path(temp_path)

    @pytest.fixture
    def mock_storage(self):
        """Create a mock storage handler."""
        return MagicMock(spec=LocalStorageHandler)

    @pytest.fixture
    def downloader(self, mock_storage):
        """Create a YouTubeDownloader instance with mock storage."""
        with patch('app.services.downloader.init_storage', return_value=mock_storage):
            return YouTubeDownloader()

    def test_youtube_downloader_init_with_storage(self, mock_storage):
        """Test YouTubeDownloader initialization with provided storage."""
        downloader = YouTubeDownloader(storage_handler=mock_storage)
        
        assert downloader.storage == mock_storage
        assert downloader.temp_dir.exists()
        assert downloader.temp_dir.name == "youtube_service"

    @patch('app.services.downloader.init_storage')
    def test_youtube_downloader_init_default_storage(self, mock_init_storage):
        """Test YouTubeDownloader initialization with default storage."""
        mock_storage = MagicMock()
        mock_init_storage.return_value = mock_storage
        
        downloader = YouTubeDownloader()
        
        assert downloader.storage == mock_storage
        mock_init_storage.assert_called_once()

    def test_get_format_selector_best(self, downloader):
        """Test format selector for 'best' quality."""
        format_selector = downloader._get_format_selector("best", "mp4")
        expected = "best[ext=mp4]/best"
        assert format_selector == expected

    def test_get_format_selector_worst(self, downloader):
        """Test format selector for 'worst' quality."""
        format_selector = downloader._get_format_selector("worst", "webm")
        expected = "worst[ext=webm]/worst"
        assert format_selector == expected

    def test_get_format_selector_specific_quality(self, downloader):
        """Test format selector for specific quality."""
        format_selector = downloader._get_format_selector("720p", "mp4")
        expected = "best[height<=720][ext=mp4]/best[height<=720]/best"
        assert format_selector == expected

    def test_get_yt_dlp_options_basic(self, downloader, temp_dir):
        """Test basic yt-dlp options generation."""
        options = downloader._get_yt_dlp_options(str(temp_dir))
        
        assert options['outtmpl'] == str(temp_dir / '%(title)s.%(ext)s')
        assert options['format'] == "best[ext=mp4]/best"
        assert options['writesubtitles'] is True
        assert options['writeautomaticsub'] is True
        assert options['subtitleslangs'] == ['en', 'en-US']
        assert options['writeinfojson'] is True
        assert options['writethumbnail'] is True
        assert 'progress_hooks' not in options  # No progress hook by default

    def test_get_yt_dlp_options_custom(self, downloader, temp_dir):
        """Test yt-dlp options with custom parameters."""
        progress_hook = MagicMock()
        
        options = downloader._get_yt_dlp_options(
            str(temp_dir),
            quality="1080p",
            output_format="mkv",
            extract_subtitles=False,
            subtitle_langs=["en", "es", "fr"],
            progress_hook=progress_hook
        )
        
        assert options['format'] == "best[height<=1080][ext=mkv]/best[height<=1080]/best"
        assert options['writesubtitles'] is False
        assert options['writeautomaticsub'] is False
        assert options['subtitleslangs'] == ['en', 'es', 'fr']
        assert options['merge_output_format'] == 'mkv'
        assert progress_hook in options['progress_hooks']

    def test_is_valid_youtube_url_valid(self, downloader):
        """Test YouTube URL validation with valid URLs."""
        valid_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
        ]
        
        for url in valid_urls:
            assert downloader.is_valid_youtube_url(url) is True

    def test_is_valid_youtube_url_invalid(self, downloader):
        """Test YouTube URL validation with invalid URLs."""
        invalid_urls = [
            "https://www.google.com",
            "https://www.vimeo.com/12345",
            "not-a-url",
            "",
        ]
        
        for url in invalid_urls:
            assert downloader.is_valid_youtube_url(url) is False
        
        # Note: https://www.youtube.com is actually valid per the implementation
        # since it contains youtube.com domain, even without video ID

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_extract_info_success(self, mock_yt_dlp_class, downloader):
        """Test successful video info extraction."""
        # Mock yt-dlp instance and extract_info method
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        
        mock_raw_info = {
            'id': 'dQw4w9WgXcQ',
            'title': 'Test Video',
            'duration': 212,
            'uploader': 'Test Channel',
            'view_count': 1000000,
            'formats': [{'format_id': '22'}, {'format_id': '18'}],
            'subtitles': {'en': [], 'es': []},
            'automatic_captions': {'en': []},
            'tags': ['music', 'video'],
            'categories': ['Entertainment']
        }
        mock_yt_dlp.extract_info.return_value = mock_raw_info
        
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        result = await downloader.extract_info(url)
        
        # Check the processed metadata
        assert result['id'] == 'dQw4w9WgXcQ'
        assert result['title'] == 'Test Video'
        assert result['duration'] == 212
        assert result['uploader'] == 'Test Channel'
        assert result['view_count'] == 1000000
        assert result['available_formats'] == 2  # len(formats)
        assert result['has_subtitles'] is True
        assert 'en' in result['available_subtitles']
        assert 'es' in result['available_subtitles']
        assert 'en' in result['automatic_captions']
        assert result['tags'] == ['music', 'video']
        assert result['categories'] == ['Entertainment']
        
        mock_yt_dlp.extract_info.assert_called_once_with(url, download=False)

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_extract_info_failure(self, mock_yt_dlp_class, downloader):
        """Test video info extraction failure."""
        # Mock yt-dlp to raise an exception
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        mock_yt_dlp.extract_info.side_effect = ExtractorError("Video not available")
        
        url = "https://www.youtube.com/watch?v=invalid"
        
        with pytest.raises(Exception) as exc_info:
            await downloader.extract_info(url)
        
        assert "Failed to extract video info" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_get_available_formats_success(self, mock_yt_dlp_class, downloader):
        """Test successful format extraction."""
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        
        # Mock the first extract_info call (for metadata)
        mock_info = {
            'id': 'dQw4w9WgXcQ',
            'title': 'Test Video',
        }
        
        # Mock the second extract_info call (for formats)
        mock_detailed_info = {
            'formats': [
                {
                    'format_id': '22', 
                    'ext': 'mp4', 
                    'height': 720, 
                    'filesize': 50000000,
                    'vcodec': 'avc1.64001F',
                    'acodec': 'mp4a.40.2'
                },
                {
                    'format_id': '18', 
                    'ext': 'mp4', 
                    'height': 360, 
                    'filesize': 25000000,
                    'vcodec': 'avc1.42001E',
                    'acodec': 'mp4a.40.2'
                },
            ]
        }
        
        # Configure mock to return different values for different calls
        mock_yt_dlp.extract_info.side_effect = [mock_info, mock_detailed_info]
        
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        formats = await downloader.get_available_formats(url)
        
        assert len(formats) == 2
        assert formats[0]['format_id'] == '22'
        assert formats[0]['quality'] == '720p'  # This is the transformed field
        assert formats[0]['ext'] == 'mp4'
        assert formats[1]['format_id'] == '18'
        assert formats[1]['quality'] == '360p'
        assert formats[1]['ext'] == 'mp4'

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_get_available_formats_no_formats(self, mock_yt_dlp_class, downloader):
        """Test format extraction when no formats are available."""
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        
        mock_info = {}  # No formats key
        mock_yt_dlp.extract_info.return_value = mock_info
        
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        formats = await downloader.get_available_formats(url)
        
        assert formats == []

    @pytest.mark.asyncio
    @patch('app.services.downloader.uuid.uuid4')
    @patch('yt_dlp.YoutubeDL')
    async def test_download_video_success(self, mock_yt_dlp_class, mock_uuid, downloader, temp_dir):
        """Test successful video download."""
        # Setup mocks
        mock_uuid.return_value.hex = "test-job-id"
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        
        # Mock download result
        mock_yt_dlp.download.return_value = None
        
        # Mock storage upload
        downloader.storage.save_file = AsyncMock(return_value=True)
        downloader.storage.get_file_url = AsyncMock(return_value="https://storage.example.com/video.mp4")
        
        # Create mock downloaded files
        video_file = temp_dir / "test_video.mp4"
        video_file.write_text("fake video content")
        
        with patch.object(downloader, '_process_downloaded_files') as mock_process:
            mock_process.return_value = {
                'video_file': str(video_file),
                'video_size': 1024,
                'title': 'Test Video'
            }
            
            with patch.object(downloader, '_upload_to_storage') as mock_upload:
                mock_upload.return_value = {
                    'video_url': 'https://storage.example.com/video.mp4',
                    'video_path': 'downloads/video.mp4'
                }
                
                url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                result = await downloader.download_video(url, "test-job-id")
                
                assert 'video_url' in result
                assert 'video_path' in result
                assert result['video_url'] == 'https://storage.example.com/video.mp4'

    @pytest.mark.asyncio
    @patch('yt_dlp.YoutubeDL')
    async def test_download_video_yt_dlp_error(self, mock_yt_dlp_class, downloader):
        """Test video download with yt-dlp error."""
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        mock_yt_dlp.download.side_effect = DownloadError("Download failed")
        
        url = "https://www.youtube.com/watch?v=invalid"
        
        with pytest.raises(Exception) as exc_info:
            await downloader.download_video(url, "test-job-id")
        
        assert "Download failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cleanup_temp_files(self, downloader, temp_dir):
        """Test cleanup of temporary files."""
        # Create some test files
        test_files = [
            temp_dir / "video.mp4",
            temp_dir / "audio.m4a",
            temp_dir / "subtitle.srt"
        ]
        
        for file_path in test_files:
            file_path.write_text("test content")
            assert file_path.exists()
        
        assert temp_dir.exists()
        
        # Test cleanup - this removes the entire directory
        await downloader._cleanup_temp_files(temp_dir)
        
        # Entire directory should be removed
        assert not temp_dir.exists()

    @pytest.mark.asyncio
    async def test_cleanup_temp_files_nonexistent(self, downloader):
        """Test cleanup of non-existent directory."""
        nonexistent_dir = Path("/tmp/nonexistent_dir_12345")
        
        # Should not raise exception
        await downloader._cleanup_temp_files(nonexistent_dir)

    @pytest.mark.asyncio
    async def test_upload_to_storage_success(self, downloader, temp_dir):
        """Test successful file upload to storage."""
        downloader.storage.save_file = AsyncMock(return_value=True)
        downloader.storage.get_file_url = AsyncMock(return_value="https://storage.example.com/video.mp4")
        
        # Create a temporary video file
        video_file = temp_dir / "video.mp4"
        video_file.write_bytes(b"fake video content")
        
        file_info = {
            'primary_file': str(video_file),
            'file_type': 'video',
            'title': 'Test Video'
        }
        
        result = await downloader._upload_to_storage(file_info, "job-123")
        
        assert 'video_url' in result
        assert result['video_url'] == "https://storage.example.com/video.mp4"
        assert 'video_path' in result
        downloader.storage.save_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_to_storage_no_file(self, downloader):
        """Test upload when no file exists."""
        downloader.storage.save_file = AsyncMock()
        
        file_info = {
            'primary_file': '/tmp/nonexistent.mp4',
            'file_type': 'video',
            'title': 'Test Video'
        }
        
        result = await downloader._upload_to_storage(file_info, "job-123")
        
        # Should return default structure when no file exists
        assert result['video_url'] is None
        assert result['video_path'] is None
        assert 'audio_url' in result
        assert 'thumbnail_url' in result
        downloader.storage.save_file.assert_not_called()