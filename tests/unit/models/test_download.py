import pytest
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock
from pydantic import ValidationError, HttpUrl

from app.models.download import (
    DownloadStatus,
    VideoQuality,
    OutputFormat,
    DownloadRequest,
    DownloadResponse,
    VideoMetadata,
    JobProgress,
    DownloadJobStatus,
    DownloadJobList,
    VideoInfo,
    ErrorResponse,
    HealthStatus,
    WebSocketMessage,
    ProgressMessage,
    StatusMessage,
    ErrorMessage
)


class TestEnums:
    """Test cases for enum classes."""

    def test_download_status_values(self):
        """Test DownloadStatus enum values."""
        assert DownloadStatus.QUEUED == "queued"
        assert DownloadStatus.PROCESSING == "processing"
        assert DownloadStatus.COMPLETED == "completed"
        assert DownloadStatus.FAILED == "failed"
        
        # Test all values are present
        expected_values = {"queued", "processing", "completed", "failed"}
        actual_values = {status.value for status in DownloadStatus}
        assert actual_values == expected_values

    def test_video_quality_values(self):
        """Test VideoQuality enum values."""
        assert VideoQuality.BEST == "best"
        assert VideoQuality.WORST == "worst"
        assert VideoQuality.P480 == "480p"
        assert VideoQuality.P720 == "720p"
        assert VideoQuality.P1080 == "1080p"
        assert VideoQuality.P1440 == "1440p"
        assert VideoQuality.P2160 == "2160p"
        
        # Test count
        assert len(VideoQuality) == 7

    def test_output_format_values(self):
        """Test OutputFormat enum values."""
        assert OutputFormat.MP4 == "mp4"
        assert OutputFormat.MKV == "mkv"
        assert OutputFormat.WEBM == "webm"
        assert OutputFormat.MP3 == "mp3"
        assert OutputFormat.M4A == "m4a"
        
        # Test count
        assert len(OutputFormat) == 5


class TestDownloadRequest:
    """Test cases for DownloadRequest model."""

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    @patch('app.core.validation.InputValidator.validate_subtitle_languages')
    def test_download_request_valid(self, mock_validate_subtitles, mock_validate_url):
        """Test valid DownloadRequest creation."""
        mock_validate_url.return_value = {'canonical_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        mock_validate_subtitles.return_value = ['en', 'es']
        
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            quality=VideoQuality.P720,
            output_format=OutputFormat.MP4,
            audio_only=False,
            include_transcription=True,
            subtitle_languages=["en", "es"]
        )
        
        assert str(request.url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert request.quality == VideoQuality.P720
        assert request.output_format == OutputFormat.MP4
        assert request.audio_only is False
        assert request.include_transcription is True
        assert request.subtitle_languages == ["en", "es"]

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    @patch('app.core.validation.InputValidator.validate_subtitle_languages')
    def test_download_request_defaults(self, mock_validate_subtitles, mock_validate_url):
        """Test DownloadRequest with default values."""
        mock_validate_url.return_value = {'canonical_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        mock_validate_subtitles.return_value = ['en']
        
        request = DownloadRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        
        assert request.quality == VideoQuality.BEST
        assert request.output_format == OutputFormat.MP4
        assert request.audio_only is False
        assert request.include_transcription is True
        assert request.subtitle_languages == ["en"]

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    def test_download_request_invalid_url(self, mock_validate_url):
        """Test DownloadRequest with invalid URL format."""
        # Pydantic will catch malformed URLs before our validator
        with pytest.raises(ValidationError) as exc_info:
            DownloadRequest(url="not-a-youtube-url")
        
        assert "valid URL" in str(exc_info.value)

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    def test_download_request_invalid_youtube_url(self, mock_validate_url):
        """Test DownloadRequest with valid URL but invalid YouTube URL."""
        mock_validate_url.side_effect = ValueError("Invalid YouTube URL")
        
        with pytest.raises(ValidationError) as exc_info:
            DownloadRequest(url="https://www.example.com/not-youtube")
        
        assert "Invalid YouTube URL" in str(exc_info.value)

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    @patch('app.core.validation.InputValidator.validate_subtitle_languages')
    def test_download_request_invalid_subtitles(self, mock_validate_subtitles, mock_validate_url):
        """Test DownloadRequest with invalid subtitle languages."""
        mock_validate_url.return_value = {'canonical_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        mock_validate_subtitles.side_effect = ValueError("Invalid language codes")
        
        with pytest.raises(ValidationError) as exc_info:
            DownloadRequest(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                subtitle_languages=["invalid"]
            )
        
        assert "Invalid subtitle languages" in str(exc_info.value)

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    @patch('app.core.validation.InputValidator.validate_subtitle_languages')
    def test_download_request_empty_subtitles(self, mock_validate_subtitles, mock_validate_url):
        """Test DownloadRequest with empty subtitle languages."""
        mock_validate_url.return_value = {'canonical_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        mock_validate_subtitles.return_value = ['en']
        
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            subtitle_languages=[]
        )
        
        assert request.subtitle_languages == ["en"]


class TestDownloadResponse:
    """Test cases for DownloadResponse model."""

    def test_download_response_creation(self):
        """Test DownloadResponse model creation."""
        response = DownloadResponse(
            job_id="test-job-123",
            status=DownloadStatus.QUEUED,
            message="Download job queued successfully",
            estimated_time=300
        )
        
        assert response.job_id == "test-job-123"
        assert response.status == DownloadStatus.QUEUED
        assert response.message == "Download job queued successfully"
        assert response.estimated_time == 300

    def test_download_response_optional_fields(self):
        """Test DownloadResponse with optional fields."""
        response = DownloadResponse(
            job_id="test-job-123",
            status=DownloadStatus.COMPLETED,
            message="Download completed"
        )
        
        assert response.estimated_time is None


class TestVideoMetadata:
    """Test cases for VideoMetadata model."""

    def test_video_metadata_creation(self):
        """Test VideoMetadata model creation."""
        metadata = VideoMetadata(
            id="dQw4w9WgXcQ",
            title="Test Video",
            description="A test video",
            duration=180,
            uploader="TestChannel",
            view_count=1000000,
            tags=["music", "test"],
            categories=["Entertainment"],
            has_subtitles=True,
            available_subtitles=["en", "es"]
        )
        
        assert metadata.id == "dQw4w9WgXcQ"
        assert metadata.title == "Test Video"
        assert metadata.duration == 180
        assert metadata.view_count == 1000000
        assert metadata.tags == ["music", "test"]
        assert metadata.has_subtitles is True
        assert metadata.available_subtitles == ["en", "es"]

    def test_video_metadata_defaults(self):
        """Test VideoMetadata with default values."""
        metadata = VideoMetadata()
        
        assert metadata.id is None
        assert metadata.title is None
        assert metadata.tags == []
        assert metadata.categories == []
        assert metadata.available_subtitles == []
        assert metadata.automatic_captions == []


class TestJobProgress:
    """Test cases for JobProgress model."""

    def test_job_progress_creation(self):
        """Test JobProgress model creation."""
        progress = JobProgress(
            current=45.5,
            total=100,
            status="Downloading video...",
            eta=120
        )
        
        assert progress.current == 45.5
        assert progress.total == 100
        assert progress.status == "Downloading video..."
        assert progress.eta == 120

    def test_job_progress_validation(self):
        """Test JobProgress validation constraints."""
        # Test valid range
        progress = JobProgress(current=50, status="Processing")
        assert progress.current == 50
        
        # Test out of range
        with pytest.raises(ValidationError):
            JobProgress(current=-10, status="Invalid")
        
        with pytest.raises(ValidationError):
            JobProgress(current=150, status="Invalid")

    def test_job_progress_defaults(self):
        """Test JobProgress with default values."""
        progress = JobProgress(current=25, status="Working")
        
        assert progress.total == 100
        assert progress.eta is None


class TestDownloadJobStatus:
    """Test cases for DownloadJobStatus model."""

    def test_download_job_status_complete(self):
        """Test DownloadJobStatus with all fields."""
        created_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)
        
        progress = JobProgress(current=100, status="Completed")
        metadata = VideoMetadata(id="test123", title="Test Video")
        
        job_status = DownloadJobStatus(
            job_id="job-123",
            url="https://www.youtube.com/watch?v=test123",
            status=DownloadStatus.COMPLETED,
            progress=progress,
            metadata=metadata,
            video_path="/downloads/video.mp4",
            video_url="https://cdn.example.com/video.mp4",
            file_size=1048576,
            file_size_formatted="1.0 MB",
            created_at=created_at,
            completed_at=completed_at,
            retry_count=0
        )
        
        assert job_status.job_id == "job-123"
        assert job_status.status == DownloadStatus.COMPLETED
        assert job_status.progress == progress
        assert job_status.metadata == metadata
        assert job_status.video_path == "/downloads/video.mp4"
        assert job_status.file_size == 1048576
        assert job_status.retry_count == 0
        assert job_status.max_retries == 3  # default
        assert job_status.can_retry is False  # default


class TestDownloadJobList:
    """Test cases for DownloadJobList model."""

    def test_download_job_list_creation(self):
        """Test DownloadJobList model creation."""
        progress = JobProgress(current=50, status="Processing")
        job1 = DownloadJobStatus(
            job_id="job-1",
            url="https://www.youtube.com/watch?v=test1",
            status=DownloadStatus.PROCESSING,
            progress=progress,
            created_at=datetime.now(timezone.utc)
        )
        job2 = DownloadJobStatus(
            job_id="job-2",
            url="https://www.youtube.com/watch?v=test2",
            status=DownloadStatus.COMPLETED,
            progress=JobProgress(current=100, status="Done"),
            created_at=datetime.now(timezone.utc)
        )
        
        job_list = DownloadJobList(
            jobs=[job1, job2],
            total=25,
            page=1,
            per_page=10,
            total_pages=3
        )
        
        assert len(job_list.jobs) == 2
        assert job_list.total == 25
        assert job_list.page == 1
        assert job_list.per_page == 10
        assert job_list.total_pages == 3

    def test_download_job_list_validation(self):
        """Test DownloadJobList validation constraints."""
        with pytest.raises(ValidationError):
            DownloadJobList(
                jobs=[],
                total=-1,  # Invalid negative total
                page=1,
                per_page=10,
                total_pages=1
            )
        
        with pytest.raises(ValidationError):
            DownloadJobList(
                jobs=[],
                total=10,
                page=0,  # Invalid page number
                per_page=10,
                total_pages=1
            )


class TestVideoInfo:
    """Test cases for VideoInfo model."""

    def test_video_info_creation(self):
        """Test VideoInfo model creation."""
        metadata = VideoMetadata(id="test123", title="Test Video")
        formats = [
            {"format_id": "22", "ext": "mp4", "height": 720},
            {"format_id": "18", "ext": "mp4", "height": 360}
        ]
        
        video_info = VideoInfo(
            url="https://www.youtube.com/watch?v=test123",
            metadata=metadata,
            available_formats=formats,
            recommended_quality="720p"
        )
        
        assert video_info.url == "https://www.youtube.com/watch?v=test123"
        assert video_info.metadata == metadata
        assert len(video_info.available_formats) == 2
        assert video_info.recommended_quality == "720p"

    def test_video_info_defaults(self):
        """Test VideoInfo with default values."""
        metadata = VideoMetadata()
        video_info = VideoInfo(
            url="https://www.youtube.com/watch?v=test",
            metadata=metadata
        )
        
        assert video_info.available_formats == []
        assert video_info.recommended_quality == "720p"


class TestErrorResponse:
    """Test cases for ErrorResponse model."""

    def test_error_response_creation(self):
        """Test ErrorResponse model creation."""
        timestamp = datetime.now(timezone.utc)
        error = ErrorResponse(
            error="BadRequest",
            message="Invalid input provided",
            details={"field": "url", "issue": "not_youtube"},
            timestamp=timestamp
        )
        
        assert error.error == "BadRequest"
        assert error.message == "Invalid input provided"
        assert error.details["field"] == "url"
        assert error.timestamp == timestamp

    def test_error_response_auto_timestamp(self):
        """Test ErrorResponse with automatic timestamp."""
        error = ErrorResponse(
            error="TestError",
            message="Test message"
        )
        
        assert error.details is None
        assert isinstance(error.timestamp, datetime)


class TestHealthStatus:
    """Test cases for HealthStatus model."""

    def test_health_status_creation(self):
        """Test HealthStatus model creation."""
        checks = {
            "database": {"status": "healthy"},
            "storage": {"status": "healthy"}
        }
        
        health = HealthStatus(
            status="healthy",
            environment="localhost",
            version="1.0.0",
            checks=checks
        )
        
        assert health.status == "healthy"
        assert health.environment == "localhost"
        assert health.version == "1.0.0"
        assert health.checks == checks

    def test_health_status_optional_fields(self):
        """Test HealthStatus with optional fields."""
        health = HealthStatus(
            status="degraded",
            environment="production",
            version="2.0.0"
        )
        
        assert health.timestamp is None
        assert health.checks is None


class TestWebSocketMessages:
    """Test cases for WebSocket message models."""

    def test_websocket_message_base(self):
        """Test base WebSocketMessage model."""
        message = WebSocketMessage(type="test")
        
        assert message.type == "test"
        assert isinstance(message.timestamp, datetime)

    def test_progress_message(self):
        """Test ProgressMessage model."""
        progress = JobProgress(current=75, status="Almost done")
        message = ProgressMessage(
            job_id="job-123",
            progress=progress
        )
        
        assert message.type == "progress"
        assert message.job_id == "job-123"
        assert message.progress == progress

    def test_status_message(self):
        """Test StatusMessage model."""
        message = StatusMessage(
            job_id="job-456",
            status=DownloadStatus.COMPLETED,
            message="Download finished"
        )
        
        assert message.type == "status"
        assert message.job_id == "job-456"
        assert message.status == DownloadStatus.COMPLETED
        assert message.message == "Download finished"

    def test_error_message(self):
        """Test ErrorMessage model."""
        message = ErrorMessage(
            job_id="job-789",
            error="Download failed due to network error"
        )
        
        assert message.type == "error"
        assert message.job_id == "job-789"
        assert message.error == "Download failed due to network error"

    def test_error_message_no_job_id(self):
        """Test ErrorMessage without job ID."""
        message = ErrorMessage(error="General system error")
        
        assert message.type == "error"
        assert message.job_id is None
        assert message.error == "General system error"


class TestModelSerialization:
    """Test model serialization and deserialization."""

    @patch('app.core.validation.InputValidator.validate_youtube_url')
    @patch('app.core.validation.InputValidator.validate_subtitle_languages')
    def test_download_request_json_serialization(self, mock_validate_subtitles, mock_validate_url):
        """Test DownloadRequest JSON serialization."""
        mock_validate_url.return_value = {'canonical_url': 'https://www.youtube.com/watch?v=test'}
        mock_validate_subtitles.return_value = ['en']
        
        request = DownloadRequest(
            url="https://www.youtube.com/watch?v=test",
            quality=VideoQuality.P720,
            audio_only=True
        )
        
        # Test serialization
        json_data = request.model_dump()
        assert json_data["quality"] == "720p"
        assert json_data["audio_only"] is True
        
        # Test deserialization
        new_request = DownloadRequest.model_validate(json_data)
        assert new_request.quality == VideoQuality.P720
        assert new_request.audio_only is True

    def test_video_metadata_serialization(self):
        """Test VideoMetadata JSON serialization."""
        metadata = VideoMetadata(
            id="test123",
            title="Test Video",
            tags=["test", "video"],
            duration=180
        )
        
        json_data = metadata.model_dump()
        assert json_data["id"] == "test123"
        assert json_data["title"] == "Test Video"
        assert json_data["tags"] == ["test", "video"]
        
        # Test deserialization
        new_metadata = VideoMetadata.model_validate(json_data)
        assert new_metadata.id == "test123"
        assert new_metadata.title == "Test Video"
        assert new_metadata.tags == ["test", "video"]