"""
Unit tests for Pydantic download models.

Tests validation, serialization, and model behavior for download request/response models.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.models.download import (
    DownloadRequest, DownloadJobResponse, DownloadProgressUpdate,
    TranscriptionFileInfo, VideoMetadataInfo, DownloadJobsList,
    SystemStatusResponse, ErrorResponse,
    VideoQuality, VideoFormat, AudioFormat, SubtitleFormat, JobStatus
)


class TestVideoQuality:
    """Test VideoQuality enum."""
    
    def test_video_quality_values(self):
        """Test all video quality enum values."""
        assert VideoQuality.BEST == "best"
        assert VideoQuality.WORST == "worst"
        assert VideoQuality.ULTRA_HD == "2160p"
        assert VideoQuality.FULL_HD == "1080p"
        assert VideoQuality.HD == "720p"
        assert VideoQuality.SD == "480p"
        assert VideoQuality.LOW == "360p"
    
    def test_video_quality_string_conversion(self):
        """Test video quality string conversion."""
        assert str(VideoQuality.HD) == "720p"
        assert str(VideoQuality.BEST) == "best"


class TestVideoFormat:
    """Test VideoFormat enum."""
    
    def test_video_format_values(self):
        """Test all video format enum values."""
        assert VideoFormat.MP4 == "mp4"
        assert VideoFormat.MKV == "mkv"
        assert VideoFormat.WEBM == "webm"
        assert VideoFormat.AVI == "avi"
        assert VideoFormat.MOV == "mov"


class TestDownloadRequest:
    """Test DownloadRequest model validation and behavior."""
    
    def test_valid_download_request_creation(self, sample_download_request):
        """Test creating a valid download request."""
        request = sample_download_request
        
        assert request.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert request.quality == VideoQuality.HD
        assert request.include_transcription is True
        assert request.audio_only is False
        assert request.output_format == VideoFormat.MP4
        assert request.subtitle_languages == ["en"]
        assert request.extract_thumbnail is True
    
    def test_download_request_defaults(self):
        """Test download request default values."""
        request = DownloadRequest(url="https://www.youtube.com/watch?v=test")
        
        assert request.quality == VideoQuality.BEST
        assert request.include_transcription is True
        assert request.audio_only is False
        assert request.output_format == VideoFormat.MP4
        assert request.subtitle_languages == ["en"]
        assert request.extract_thumbnail is True
    
    def test_youtube_url_validation_valid_urls(self, youtube_urls):
        """Test YouTube URL validation with valid URLs."""
        for url in youtube_urls["valid"]:
            request = DownloadRequest(url=url)
            assert request.url == url
    
    def test_youtube_url_validation_invalid_urls(self, youtube_urls):
        """Test YouTube URL validation with invalid URLs."""
        for url in youtube_urls["invalid"]:
            with pytest.raises(ValidationError) as exc_info:
                DownloadRequest(url=url)
            
            if url == "":
                assert "URL is required" in str(exc_info.value)
            else:
                assert "URL must be a valid YouTube URL" in str(exc_info.value)
    
    def test_subtitle_languages_validation_valid(self):
        """Test subtitle languages validation with valid codes."""
        valid_languages = ["en", "es", "fr", "de", "ja"]
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            subtitle_languages=valid_languages
        )
        # Should be converted to lowercase
        assert request.subtitle_languages == valid_languages
    
    def test_subtitle_languages_validation_invalid(self):
        """Test subtitle languages validation with invalid codes."""
        # Invalid length
        with pytest.raises(ValidationError) as exc_info:
            DownloadRequest(
                url="https://www.youtube.com/watch?v=test",
                subtitle_languages=["eng", "spa"]  # 3 characters
            )
        assert "Invalid language code" in str(exc_info.value)
        
        # Invalid code
        with pytest.raises(ValidationError) as exc_info:
            DownloadRequest(
                url="https://www.youtube.com/watch?v=test",
                subtitle_languages=["xx"]  # Non-existent code
            )
        assert "Invalid language code" in str(exc_info.value)
    
    def test_subtitle_languages_empty_defaults_to_en(self):
        """Test empty subtitle languages defaults to ['en']."""
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            subtitle_languages=[]
        )
        assert request.subtitle_languages == ["en"]
    
    def test_subtitle_languages_case_normalization(self):
        """Test subtitle languages are normalized to lowercase."""
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            subtitle_languages=["EN", "ES", "Fr"]
        )
        assert request.subtitle_languages == ["en", "es", "fr"]
    
    def test_model_validator_audio_only_format(self):
        """Test model validator for audio-only format compatibility."""
        # This should not raise an error (MP4 is allowed for audio-only)
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            audio_only=True,
            output_format=VideoFormat.MP4
        )
        assert request.audio_only is True
        assert request.output_format == VideoFormat.MP4
        
        # WEBM should also be allowed
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            audio_only=True,
            output_format=VideoFormat.WEBM
        )
        assert request.output_format == VideoFormat.WEBM
    
    def test_json_serialization(self):
        """Test JSON serialization of download request."""
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            quality=VideoQuality.HD,
            subtitle_languages=["en", "es"]
        )
        
        json_data = request.model_dump()
        
        assert json_data["url"] == "https://www.youtube.com/watch?v=test"
        assert json_data["quality"] == "720p"
        assert json_data["subtitle_languages"] == ["en", "es"]
    
    def test_json_deserialization(self):
        """Test JSON deserialization to download request."""
        json_data = {
            "url": "https://www.youtube.com/watch?v=test",
            "quality": "1080p",
            "include_transcription": False,
            "audio_only": True,
            "output_format": "webm",
            "subtitle_languages": ["fr", "de"],
            "extract_thumbnail": False
        }
        
        request = DownloadRequest(**json_data)
        
        assert request.url == "https://www.youtube.com/watch?v=test"
        assert request.quality == VideoQuality.FULL_HD
        assert request.include_transcription is False
        assert request.audio_only is True
        assert request.output_format == VideoFormat.WEBM
        assert request.subtitle_languages == ["fr", "de"]
        assert request.extract_thumbnail is False


class TestTranscriptionFileInfo:
    """Test TranscriptionFileInfo model."""
    
    def test_transcription_file_info_creation(self):
        """Test creating transcription file info."""
        info = TranscriptionFileInfo(
            language="en",
            format=SubtitleFormat.SRT,
            file_path="/path/to/subtitles.srt",
            is_auto_generated=True
        )
        
        assert info.language == "en"
        assert info.format == SubtitleFormat.SRT
        assert info.file_path == "/path/to/subtitles.srt"
        assert info.is_auto_generated is True
    
    def test_transcription_file_info_serialization(self):
        """Test transcription file info JSON serialization."""
        info = TranscriptionFileInfo(
            language="es",
            format=SubtitleFormat.VTT,
            file_path="/path/to/subtitles.vtt",
            is_auto_generated=False
        )
        
        json_data = info.model_dump()
        
        assert json_data["language"] == "es"
        assert json_data["format"] == "vtt"
        assert json_data["file_path"] == "/path/to/subtitles.vtt"
        assert json_data["is_auto_generated"] is False


class TestVideoMetadataInfo:
    """Test VideoMetadataInfo model."""
    
    def test_video_metadata_creation(self):
        """Test creating video metadata."""
        upload_date = datetime.now(timezone.utc)
        
        metadata = VideoMetadataInfo(
            title="Test Video",
            duration=300,
            channel_name="Test Channel",
            upload_date=upload_date,
            view_count=1000,
            like_count=50,
            description="Test description",
            thumbnail_url="http://test.com/thumb.jpg",
            video_id="test123"
        )
        
        assert metadata.title == "Test Video"
        assert metadata.duration == 300
        assert metadata.channel_name == "Test Channel"
        assert metadata.upload_date == upload_date
        assert metadata.view_count == 1000
        assert metadata.like_count == 50
        assert metadata.description == "Test description"
        assert metadata.thumbnail_url == "http://test.com/thumb.jpg"
        assert metadata.video_id == "test123"
    
    def test_video_metadata_optional_fields(self):
        """Test video metadata with optional fields."""
        metadata = VideoMetadataInfo(
            title="Test Video",
            duration=300,
            channel_name="Test Channel",
            video_id="test123"
        )
        
        assert metadata.upload_date is None
        assert metadata.view_count is None
        assert metadata.like_count is None
        assert metadata.description is None
        assert metadata.thumbnail_url is None


class TestDownloadJobResponse:
    """Test DownloadJobResponse model."""
    
    def test_download_job_response_creation(self):
        """Test creating download job response."""
        job_id = uuid4()
        created_at = datetime.now(timezone.utc)
        
        response = DownloadJobResponse(
            id=job_id,
            url="https://www.youtube.com/watch?v=test",
            status=JobStatus.COMPLETED,
            progress=1.0,
            quality="720p",
            include_transcription=True,
            audio_only=False,
            output_format="mp4",
            title="Test Video",
            duration=300,
            channel_name="Test Channel",
            video_path="/path/to/video.mp4",
            transcription_path="/path/to/subtitles.srt",
            thumbnail_path="/path/to/thumbnail.jpg",
            created_at=created_at,
            retry_count=0
        )
        
        assert response.id == job_id
        assert response.url == "https://www.youtube.com/watch?v=test"
        assert response.status == JobStatus.COMPLETED
        assert response.progress == 1.0
        assert response.quality == "720p"
        assert response.title == "Test Video"
        assert response.video_path == "/path/to/video.mp4"
        assert response.created_at == created_at
        assert response.retry_count == 0
    
    def test_download_job_response_with_uuid_serialization(self):
        """Test download job response with UUID serialization."""
        job_id = uuid4()
        
        response = DownloadJobResponse(
            id=job_id,
            url="https://www.youtube.com/watch?v=test",
            status=JobStatus.QUEUED,
            progress=0.0,
            quality="720p",
            include_transcription=True,
            audio_only=False,
            output_format="mp4",
            created_at=datetime.now(timezone.utc),
            retry_count=0
        )
        
        json_data = response.model_dump()
        assert json_data["id"] == str(job_id)  # UUID serialized as string
        assert json_data["status"] == "queued"


class TestDownloadProgressUpdate:
    """Test DownloadProgressUpdate model."""
    
    def test_download_progress_update_creation(self):
        """Test creating download progress update."""
        job_id = uuid4()
        
        update = DownloadProgressUpdate(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress=0.5,
            message="Downloading video...",
            downloaded_bytes=1024000,
            total_bytes=2048000,
            download_speed=102400,
            eta=10
        )
        
        assert update.job_id == job_id
        assert update.status == JobStatus.PROCESSING
        assert update.progress == 0.5
        assert update.message == "Downloading video..."
        assert update.downloaded_bytes == 1024000
        assert update.total_bytes == 2048000
        assert update.download_speed == 102400
        assert update.eta == 10
    
    def test_download_progress_update_with_defaults(self):
        """Test download progress update with default timestamp."""
        job_id = uuid4()
        
        update = DownloadProgressUpdate(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress=0.5,
            message="Processing..."
        )
        
        # Timestamp should be automatically set
        assert update.timestamp is not None
        assert isinstance(update.timestamp, datetime)


class TestDownloadJobsList:
    """Test DownloadJobsList model."""
    
    def test_download_jobs_list_creation(self):
        """Test creating download jobs list."""
        job1 = DownloadJobResponse(
            id=uuid4(),
            url="https://www.youtube.com/watch?v=test1",
            status=JobStatus.COMPLETED,
            progress=1.0,
            quality="720p",
            include_transcription=True,
            audio_only=False,
            output_format="mp4",
            created_at=datetime.now(timezone.utc),
            retry_count=0
        )
        
        job2 = DownloadJobResponse(
            id=uuid4(),
            url="https://www.youtube.com/watch?v=test2",
            status=JobStatus.PROCESSING,
            progress=0.5,
            quality="1080p",
            include_transcription=False,
            audio_only=True,
            output_format="mp3",
            created_at=datetime.now(timezone.utc),
            retry_count=1
        )
        
        jobs_list = DownloadJobsList(
            jobs=[job1, job2],
            total=2,
            page=1,
            per_page=10,
            pages=1
        )
        
        assert len(jobs_list.jobs) == 2
        assert jobs_list.total == 2
        assert jobs_list.page == 1
        assert jobs_list.per_page == 10
        assert jobs_list.pages == 1


class TestSystemStatusResponse:
    """Test SystemStatusResponse model."""
    
    def test_system_status_response_creation(self):
        """Test creating system status response."""
        from app.models.download import QualityPresetInfo
        
        preset_info = QualityPresetInfo(
            name="high",
            video_bitrate="5M",
            audio_bitrate="320k",
            max_resolution="1440p"
        )
        
        status = SystemStatusResponse(
            status="healthy",
            active_downloads=2,
            queue_length=5,
            available_qualities=[VideoQuality.HD, VideoQuality.FULL_HD],
            available_formats=[VideoFormat.MP4, VideoFormat.WEBM],
            audio_formats=[AudioFormat.MP3, AudioFormat.M4A],
            quality_presets=[preset_info],
            max_concurrent_downloads=3,
            storage_type="local"
        )
        
        assert status.status == "healthy"
        assert status.active_downloads == 2
        assert status.queue_length == 5
        assert len(status.available_qualities) == 2
        assert len(status.available_formats) == 2
        assert len(status.audio_formats) == 2
        assert len(status.quality_presets) == 1
        assert status.max_concurrent_downloads == 3
        assert status.storage_type == "local"


class TestErrorResponse:
    """Test ErrorResponse model."""
    
    def test_error_response_creation(self):
        """Test creating error response."""
        error = ErrorResponse(
            error="ValidationError",
            message="Invalid input data",
            details={"field": "url", "issue": "Invalid YouTube URL"}
        )
        
        assert error.error == "ValidationError"
        assert error.message == "Invalid input data"
        assert error.details == {"field": "url", "issue": "Invalid YouTube URL"}
        assert isinstance(error.timestamp, datetime)
    
    def test_error_response_without_details(self):
        """Test error response without details."""
        error = ErrorResponse(
            error="NotFoundError",
            message="Resource not found"
        )
        
        assert error.error == "NotFoundError"
        assert error.message == "Resource not found"
        assert error.details is None
        assert isinstance(error.timestamp, datetime)