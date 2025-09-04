"""
Unit tests for the YouTubeDownloader core service.

Covers:
- extract_metadata (success and failure)
- download_video workflow (happy path and failure)
- _configure_yt_dlp_options variations
- _store_file path/key generation and storage integration
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.downloader import (
    YouTubeDownloader,
    DownloadOptions,
    VideoMetadata,
    DownloadResult,
    DownloadError,
)

# Comprehensive unit tests for YouTubeDownloader service


class TestYouTubeDownloader:
    @pytest.fixture
    def downloader(self):
        """Provide a downloader with a mocked storage handler."""
        with patch("app.services.downloader.get_storage_handler") as mock_factory:
            mock_storage = AsyncMock()
            mock_storage.save_file = AsyncMock()
            mock_storage.get_file_url = AsyncMock(return_value="http://example.com/file")
            mock_factory.return_value = mock_storage

            d = YouTubeDownloader()
            d.storage_handler = mock_storage
            return d

    # -----------------------------
    # extract_metadata
    # -----------------------------
    @pytest.mark.asyncio
    async def test_extract_metadata_success(self, downloader):
        mock_info = {
            "title": "Test Video",
            "duration": 300,
            "uploader": "Test Channel",
            "upload_date": "20240115",
            "view_count": 1000,
            "like_count": 50,
            "description": "Desc",
            "thumbnail": "http://thumb.jpg",
            "id": "vid123",
            "formats": [{"height": 720, "ext": "mp4"}, {"height": 1080, "ext": "mp4"}],
            "subtitles": {"en": []},
            "automatic_captions": {"es": []},
        }

        with patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("asyncio.get_event_loop") as mock_loop:
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            # Simulate extract_info in executor
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_info)

            md: VideoMetadata = await downloader.extract_metadata("https://youtube.com/watch?v=vid123")

        assert md.title == "Test Video"
        assert md.duration == 300
        assert md.channel_name == "Test Channel"
        assert md.video_id == "vid123"
        assert "720p-mp4" in md.formats_available
        # includes auto subtitles labeling
        assert any("es" in s for s in md.subtitles_available)
        assert md.upload_date is not None

    @pytest.mark.asyncio
    async def test_extract_metadata_failure_raises_download_error(self, downloader):
        with patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("asyncio.get_event_loop") as mock_loop:
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("boom"))

            with pytest.raises(DownloadError):
                await downloader.extract_metadata("bad-url")

    # -----------------------------
    # _configure_yt_dlp_options
    # -----------------------------
    def test_configure_options_variants(self, downloader):
        outdir = Path("/tmp/test_dl")

        # audio only
        opts = DownloadOptions(audio_only=True)
        cfg = downloader._configure_yt_dlp_options(opts, outdir)
        assert cfg["format"] == "bestaudio/best"

        # best quality
        opts = DownloadOptions(quality="best")
        cfg = downloader._configure_yt_dlp_options(opts, outdir)
        assert cfg["format"] == "best"

        # specific height
        opts = DownloadOptions(quality="720p")
        cfg = downloader._configure_yt_dlp_options(opts, outdir)
        assert "best[height<=720]" in cfg["format"]

        # conversion postprocessor when not audio_only and format specified
        opts = DownloadOptions(audio_only=False, output_format="mkv")
        cfg = downloader._configure_yt_dlp_options(opts, outdir)
        assert any(pp.get("key") == "FFmpegVideoConvertor" for pp in cfg.get("postprocessors", []))

    # -----------------------------
    # _store_file
    # -----------------------------
    @pytest.mark.asyncio
    async def test_store_file_sends_bytes_and_returns_url(self, downloader):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            p = Path(tmp.name)
            p.write_bytes(b"data")

            url = await downloader._store_file(p, "../../../etc/passwd", "video")

        # save_file called with sanitized key and proper bytes
        downloader.storage_handler.save_file.assert_awaited()
        key, data = downloader.storage_handler.save_file.call_args[0]
        assert "etcpasswd" in key
        assert isinstance(data, (bytes, bytearray))
        assert url == "http://example.com/file"

    # -----------------------------
    # download_video
    # -----------------------------
    @pytest.mark.asyncio
    async def test_download_video_happy_path(self, downloader):
        # Mocks
        with patch.object(downloader, "extract_metadata", return_value=VideoMetadata(
            title="T", duration=1, channel_name="C", upload_date=None, view_count=0, like_count=0,
            description="", thumbnail_url="", video_id="id", formats_available=[], subtitles_available=[]
        )), \
            patch.object(downloader, "_configure_yt_dlp_options", return_value={}), \
            patch.object(downloader, "_store_file", side_effect=[
                "http://example.com/video.mp4",   # video
                "http://example.com/subs.srt",    # transcription
                "http://example.com/thumb.jpg",   # thumbnail
            ]), \
            patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("pathlib.Path.glob") as mock_glob, \
            patch("pathlib.Path.mkdir"):

            # Fake downloaded files in temp dir
            v = MagicMock(); v.suffix = ".mp4"; v.stem = "video"
            s = MagicMock(); s.suffix = ".srt"; s.stem = "video.en"
            t = MagicMock(); t.suffix = ".jpg"; t.stem = "thumb"
            mock_glob.return_value = [v, s, t]

            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            # Simulate executor download call
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

                result: DownloadResult = await downloader.download_video(
                    job_id="job-123",
                    url="https://youtube.com/watch?v=abc",
                    options=DownloadOptions(),
                )

        assert result.success is True
        assert result.video_path == "http://example.com/video.mp4"
        assert result.thumbnail_path == "http://example.com/thumb.jpg"
        assert result.transcription_files and result.transcription_files[0].language in {"en", "auto"}
        assert result.metadata is not None

    @pytest.mark.asyncio
    async def test_download_video_failure_returns_error(self, downloader):
        with patch.object(downloader, "extract_metadata", side_effect=Exception("x")), \
            patch("pathlib.Path.mkdir"), \
            patch("pathlib.Path.exists", return_value=True), \
            patch.object(downloader, "_cleanup_temp_directory") as mock_cleanup:
            mock_cleanup.return_value = None

            result = await downloader.download_video(
                job_id="job-err",
                url="https://youtube.com/watch?v=abc",
                options=DownloadOptions(),
            )

        assert result.success is False
        assert "x" in (result.error_message or "")
        mock_cleanup.assert_called_once()

    # -----------------------------
    # Additional edge cases
    # -----------------------------
    @pytest.mark.asyncio
    async def test_extract_metadata_missing_fields_uses_defaults(self, downloader):
        """Test that missing metadata fields use sensible defaults."""
        minimal_info = {
            "title": "Minimal Video",
            # Missing most fields
        }

        with patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("asyncio.get_event_loop") as mock_loop:
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=minimal_info)

            md = await downloader.extract_metadata("https://youtube.com/watch?v=minimal")

        assert md.title == "Minimal Video"
        assert md.duration == 0  # default
        assert md.channel_name == "Unknown"  # default
        assert md.video_id == ""  # default
        assert md.formats_available == []  # default
        assert md.upload_date is None  # no date provided

    @pytest.mark.asyncio 
    async def test_extract_metadata_invalid_upload_date_logs_warning(self, downloader):
        """Test that invalid upload dates are handled gracefully."""
        info_bad_date = {
            "title": "Bad Date Video", 
            "upload_date": "invalid-date-format",
        }

        with patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("asyncio.get_event_loop") as mock_loop, \
            patch("app.services.downloader.logger") as mock_logger:
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=info_bad_date)

            md = await downloader.extract_metadata("https://youtube.com/watch?v=baddate")

        assert md.upload_date is None
        mock_logger.warning.assert_called()

    def test_configure_options_with_progress_callback(self, downloader):
        """Test that progress callback is properly added to yt-dlp options."""
        callback = MagicMock()
        opts = DownloadOptions()
        outdir = Path("/tmp")
        
        cfg = downloader._configure_yt_dlp_options(opts, outdir, callback)
        
        assert "progress_hooks" in cfg
        assert callback in cfg["progress_hooks"]

    def test_configure_options_subtitle_settings(self, downloader):
        """Test subtitle-related configuration options."""
        opts = DownloadOptions(
            include_transcription=True,
            subtitle_languages=["en", "es", "fr"]
        )
        cfg = downloader._configure_yt_dlp_options(opts, Path("/tmp"))
        
        assert cfg["writesubtitles"] is True
        assert cfg["writeautomaticsub"] is True
        assert cfg["subtitleslangs"] == ["en", "es", "fr"]

    def test_configure_options_no_transcription(self, downloader):
        """Test configuration when transcription is disabled."""
        opts = DownloadOptions(include_transcription=False)
        cfg = downloader._configure_yt_dlp_options(opts, Path("/tmp"))
        
        assert cfg["writesubtitles"] is False
        assert cfg["writeautomaticsub"] is False

    @pytest.mark.asyncio
    async def test_store_file_different_types_generate_correct_keys(self, downloader):
        """Test storage key generation for different file types."""
        with tempfile.NamedTemporaryFile(suffix=".srt") as tmp:
            p = Path(tmp.name)
            p.write_bytes(b"subtitle data")

            await downloader._store_file(p, "job-123", "transcription")

        key = downloader.storage_handler.save_file.call_args[0][0]
        assert "transcriptions/job-123/" in key
        assert key.endswith("_en.srt")  # language detection

    @pytest.mark.asyncio
    async def test_store_file_thumbnail_type(self, downloader):
        """Test storage key generation for thumbnail files."""
        with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
            p = Path(tmp.name)
            p.write_bytes(b"image data")

            await downloader._store_file(p, "job-456", "thumbnail")

        key = downloader.storage_handler.save_file.call_args[0][0]
        assert "thumbnails/job-456/" in key
        assert "_thumbnail.jpg" in key

    @pytest.mark.asyncio
    async def test_download_video_only_audio_file_processed(self, downloader):
        """Test download with only audio file (no video, subtitles, or thumbnails)."""
        with patch.object(downloader, "extract_metadata", return_value=VideoMetadata(
            title="Audio Only", duration=120, channel_name="Test", upload_date=None, 
            view_count=0, like_count=0, description="", thumbnail_url="", video_id="audio123",
            formats_available=[], subtitles_available=[]
        )), \
            patch.object(downloader, "_configure_yt_dlp_options", return_value={}), \
            patch.object(downloader, "_store_file", return_value="http://example.com/audio.mp3"), \
            patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("pathlib.Path.glob") as mock_glob, \
            patch("pathlib.Path.mkdir"), \
            patch("asyncio.get_event_loop") as mock_loop:

            # Only audio file downloaded
            audio_file = MagicMock()
            audio_file.suffix = ".mp3"
            mock_glob.return_value = [audio_file]
            
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            result = await downloader.download_video(
                "audio-job", "https://youtube.com/watch?v=audio", 
                DownloadOptions(audio_only=True)
            )

        assert result.success is True
        assert result.video_path == "http://example.com/audio.mp3"
        assert result.transcription_files == []  # no subtitle files
        assert result.thumbnail_path is None  # no thumbnail

    @pytest.mark.asyncio
    async def test_download_video_cleanup_called_even_on_storage_failure(self, downloader):
        """Test cleanup happens even when storage operations fail."""
        with patch.object(downloader, "extract_metadata", return_value=VideoMetadata(
            title="T", duration=1, channel_name="C", upload_date=None, view_count=0, 
            like_count=0, description="", thumbnail_url="", video_id="id", 
            formats_available=[], subtitles_available=[]
        )), \
            patch.object(downloader, "_configure_yt_dlp_options", return_value={}), \
            patch.object(downloader, "_store_file", side_effect=Exception("Storage error")), \
            patch("app.services.downloader.yt_dlp.YoutubeDL") as mock_ydl, \
            patch("pathlib.Path.glob") as mock_glob, \
            patch("pathlib.Path.mkdir"), \
            patch("pathlib.Path.exists", return_value=True), \
            patch.object(downloader, "_cleanup_temp_directory") as mock_cleanup, \
            patch("asyncio.get_event_loop") as mock_loop:

            v = MagicMock(); v.suffix = ".mp4"
            mock_glob.return_value = [v]
            ydl_instance = MagicMock()
            mock_ydl.return_value.__enter__.return_value = ydl_instance
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
            mock_cleanup.return_value = None

            result = await downloader.download_video(
                "storage-fail-job", "https://youtube.com/watch?v=fail", DownloadOptions()
            )

        # Should fail due to storage error but still cleanup
        assert result.success is False
        assert "Storage error" in (result.error_message or "")
        mock_cleanup.assert_called_once()

    def test_sanitize_job_id_comprehensive_cases(self, downloader):
        """Test job ID sanitization with comprehensive malicious inputs."""
        test_cases = [
            # (input, expected_output)
            ("normal-job-123", "normal-job-123"),
            ("../../../etc/passwd", "etcpasswd"),
            ("job\\with\\backslashes", "jobwithbackslashes"),
            ("job/with/slashes", "jobwithslashes"),
            ("job<>:|?*with!@#$%^&()+=special", "jobwithspecial"),
            ("", "unknown"),  # empty string
            ("a" * 100, "a" * 50),  # truncation
            ("Mixed_Case-123", "Mixed_Case-123"),  # preserves valid chars
        ]

        for malicious_input, expected in test_cases:
            result = downloader._sanitize_job_id(malicious_input)
            assert result == expected
            assert len(result) <= 50
            # Ensure no dangerous characters remain
            dangerous_chars = ['/', '\\', '..', '<', '>', ':', '|', '?', '*']
            assert not any(char in result for char in dangerous_chars)

