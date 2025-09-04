"""
Shared test fixtures and utilities for the YouTube Download Service test suite.

This module provides common fixtures, mock factories, and test utilities
used across unit and integration tests.
"""

import asyncio
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, List
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Test environment setup
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.main import app
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.storage import StorageHandler
from app.models.database import Base, DownloadJob
from app.models.download import DownloadRequest, VideoQuality, VideoFormat
from app.services.downloader import YouTubeDownloader, DownloadOptions, VideoMetadata
from app.services.video_processor import VideoProcessor


# ================================
# Configuration Fixtures
# ================================

@pytest.fixture
def test_settings():
    """Test configuration settings."""
    return Settings(
        environment="test",
        debug=True,
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/1",
        download_base_path="./test_downloads",
        max_concurrent_downloads=1,
        yt_dlp_update_check=False
    )


# ================================
# Database Fixtures
# ================================

@pytest.fixture
def test_db_engine():
    """Create test database engine."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
async def async_test_db_engine():
    """Create async test database engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    await engine.dispose()


@pytest.fixture
async def test_db_session(async_test_db_engine):
    """Create test database session."""
    async_session = sessionmaker(
        async_test_db_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
def sample_download_job():
    """Create a sample DownloadJob for testing."""
    return DownloadJob(
        id=uuid.uuid4(),
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        status="queued",
        quality="720p",
        include_transcription=True,
        audio_only=False,
        output_format="mp4",
        title="Never Gonna Give You Up",
        duration=213,
        channel_name="RickAstleyVEVO",
        view_count=1000000,
        like_count=50000,
        created_at=datetime.now(timezone.utc)
    )


# ================================
# API Testing Fixtures
# ================================

@pytest.fixture
def test_client():
    """FastAPI test client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
async def async_test_client():
    """Async FastAPI test client."""
    from httpx import AsyncClient
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ================================
# Mock Fixtures
# ================================

@pytest.fixture
def mock_storage_handler():
    """Mock storage handler for testing."""
    mock_storage = Mock(spec=StorageHandler)
    mock_storage.save_file = AsyncMock(return_value=None)
    mock_storage.get_file = AsyncMock(return_value=b"test data")
    mock_storage.file_exists = AsyncMock(return_value=True)
    mock_storage.get_file_url = AsyncMock(return_value="http://test.com/file.mp4")
    mock_storage.get_file_size = AsyncMock(return_value=1024)
    mock_storage.delete_file = AsyncMock(return_value=None)
    mock_storage.list_files = AsyncMock(return_value=["file1.mp4", "file2.mp4"])
    return mock_storage


@pytest.fixture
def mock_youtube_downloader():
    """Mock YouTube downloader for testing."""
    mock_downloader = Mock(spec=YouTubeDownloader)
    
    # Mock metadata
    mock_metadata = VideoMetadata(
        title="Test Video",
        duration=300,
        channel_name="Test Channel",
        upload_date=datetime.now(timezone.utc),
        view_count=1000,
        like_count=50,
        description="Test description",
        thumbnail_url="http://test.com/thumb.jpg",
        video_id="test123",
        formats_available=["720p-mp4", "1080p-mp4"],
        subtitles_available=["en", "es"]
    )
    
    mock_downloader.extract_metadata = AsyncMock(return_value=mock_metadata)
    mock_downloader.download_video = AsyncMock()
    
    return mock_downloader


@pytest.fixture
def mock_video_processor():
    """Mock video processor for testing."""
    mock_processor = Mock(spec=VideoProcessor)
    
    from app.services.video_processor import ProcessingResult
    mock_result = ProcessingResult(
        success=True,
        output_path="/test/output.mp4",
        file_size=1024000,
        duration=300.0,
        resolution=(1280, 720)
    )
    
    mock_processor.process_video = AsyncMock(return_value=mock_result)
    mock_processor.convert_format = AsyncMock(return_value=mock_result)
    mock_processor.extract_audio = AsyncMock(return_value=mock_result)
    mock_processor.generate_thumbnail = AsyncMock(return_value=mock_result)
    
    return mock_processor


@pytest.fixture
def mock_yt_dlp():
    """Mock yt-dlp for testing."""
    mock_yt_dlp = MagicMock()
    mock_info = {
        'title': 'Test Video',
        'duration': 300,
        'uploader': 'Test Channel',
        'upload_date': '20231201',
        'view_count': 1000,
        'like_count': 50,
        'description': 'Test description',
        'thumbnail': 'http://test.com/thumb.jpg',
        'id': 'test123',
        'formats': [
            {'height': 720, 'ext': 'mp4'},
            {'height': 1080, 'ext': 'mp4'}
        ],
        'subtitles': {'en': [], 'es': []},
        'automatic_captions': {'en': []}
    }
    
    mock_yt_dlp_instance = MagicMock()
    mock_yt_dlp_instance.extract_info.return_value = mock_info
    mock_yt_dlp_instance.download.return_value = None
    
    mock_yt_dlp.return_value.__enter__.return_value = mock_yt_dlp_instance
    
    return mock_yt_dlp


@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing."""
    mock_task = Mock()
    mock_task.delay = Mock(return_value=Mock(id="test-task-id"))
    mock_task.apply_async = Mock()
    return mock_task


# ================================
# Temporary File Fixtures
# ================================

@pytest.fixture
def temp_directory():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_video_file(temp_directory):
    """Create temporary video file for tests."""
    video_file = temp_directory / "test_video.mp4"
    video_file.write_bytes(b"fake video content")
    return video_file


@pytest.fixture
def temp_audio_file(temp_directory):
    """Create temporary audio file for tests."""
    audio_file = temp_directory / "test_audio.mp3"
    audio_file.write_bytes(b"fake audio content")
    return audio_file


# ================================
# Sample Data Fixtures
# ================================

@pytest.fixture
def sample_download_request():
    """Sample download request for testing."""
    return DownloadRequest(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        quality=VideoQuality.HD,
        include_transcription=True,
        audio_only=False,
        output_format=VideoFormat.MP4,
        subtitle_languages=["en"],
        extract_thumbnail=True
    )


@pytest.fixture
def sample_download_options():
    """Sample download options for testing."""
    return DownloadOptions(
        quality="720p",
        include_transcription=True,
        audio_only=False,
        output_format="mp4",
        subtitle_languages=["en"],
        extract_thumbnail=True
    )


@pytest.fixture
def youtube_urls():
    """Collection of test YouTube URLs."""
    return {
        "valid": [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=test123",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=test123"
        ],
        "invalid": [
            "https://vimeo.com/123456",
            "https://example.com/video",
            "not-a-url",
            ""
        ]
    }


# ================================
# Async Utilities
# ================================

@pytest_asyncio.fixture
async def event_loop():
    """Create an asyncio event loop for testing."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ================================
# Test Data Generators
# ================================

def generate_download_job(**kwargs) -> DownloadJob:
    """Generate a DownloadJob with default or custom values."""
    defaults = {
        "id": uuid.uuid4(),
        "url": "https://www.youtube.com/watch?v=test123",
        "status": "queued",
        "quality": "720p",
        "include_transcription": True,
        "audio_only": False,
        "output_format": "mp4",
        "created_at": datetime.now(timezone.utc)
    }
    defaults.update(kwargs)
    return DownloadJob(**defaults)


def generate_video_metadata(**kwargs) -> VideoMetadata:
    """Generate VideoMetadata with default or custom values."""
    defaults = {
        "title": "Test Video",
        "duration": 300,
        "channel_name": "Test Channel",
        "upload_date": datetime.now(timezone.utc),
        "view_count": 1000,
        "like_count": 50,
        "description": "Test description",
        "thumbnail_url": "http://test.com/thumb.jpg",
        "video_id": "test123",
        "formats_available": ["720p-mp4"],
        "subtitles_available": ["en"]
    }
    defaults.update(kwargs)
    return VideoMetadata(**defaults)


# ================================
# Test Markers
# ================================

# Mark slow tests
slow = pytest.mark.slow

# Mark database tests  
database = pytest.mark.database

# Mark integration tests
integration = pytest.mark.integration

# Mark external service tests
external = pytest.mark.external