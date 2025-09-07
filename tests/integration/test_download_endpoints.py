"""
Integration tests for video download endpoints.

Tests the core video download functionality including job creation,
status tracking, video info extraction, and job listing.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import uuid


class TestDownloadEndpoints:
    """Test video download endpoints."""
    
    def test_download_endpoint_requires_auth(self, client, mock_database, mock_storage):
        """Test that download endpoint requires authentication."""
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
        
        # Should get 401 or 403 for missing authentication
        assert response.status_code in [401, 403]
    
    def test_download_endpoint_invalid_api_key(self, client, mock_database, mock_storage):
        """Test download endpoint with invalid API key."""
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers={"X-API-Key": "invalid_key"}
        )
        
        assert response.status_code in [401, 403]
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.routers.downloads.queue_download_task")
    def test_download_endpoint_success(self, mock_queue, mock_validate, client, mock_database, mock_storage, download_api_key):
        """Test successful video download request."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="download",
            is_valid=True
        )
        
        # Mock task queuing
        job_id = str(uuid.uuid4())
        mock_queue.return_value = job_id
        
        response = client.post(
            "/api/v1/download",
            json={
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "quality": "720p",
                "output_format": "mp4"
            },
            headers={"X-API-Key": download_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert "message" in data
    
    @patch("app.routers.downloads.validate_api_key")
    def test_download_endpoint_invalid_url(self, mock_validate, client, mock_database, mock_storage, download_api_key):
        """Test download endpoint with invalid YouTube URL."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="download",
            is_valid=True
        )
        
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.google.com"},  # Invalid YouTube URL
            headers={"X-API-Key": download_api_key}
        )
        
        assert response.status_code == 422  # Validation error
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.core.database.get_db")
    def test_status_endpoint_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test job status endpoint with valid job."""
        # Mock API key validation (admin key for read access)
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query
        job_id = str(uuid.uuid4())
        mock_session = AsyncMock()
        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.status = "completed"
        mock_job.to_dict.return_value = {
            "job_id": job_id,
            "status": "completed",
            "video_path": "downloads/test.mp4"
        }
        mock_session.get.return_value = mock_job
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            f"/api/v1/status/{job_id}",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.core.database.get_db")
    def test_status_endpoint_job_not_found(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test job status endpoint with non-existent job."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query returning None
        job_id = str(uuid.uuid4())
        mock_session = AsyncMock()
        mock_session.get.return_value = None
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            f"/api/v1/status/{job_id}",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    @patch("app.routers.downloads.validate_api_key")
    @patch("app.routers.downloads.YouTubeDownloader")
    def test_info_endpoint_success(self, mock_downloader, mock_validate, client, mock_database, mock_storage):
        """Test video info endpoint with valid YouTube URL."""
        # Mock YouTube downloader
        mock_dl_instance = MagicMock()
        mock_dl_instance.extract_info.return_value = {
            "id": "dQw4w9WgXcQ",
            "title": "Rick Astley - Never Gonna Give You Up",
            "duration": 213,
            "view_count": 1000000
        }
        mock_downloader.return_value = mock_dl_instance
        
        response = client.get(
            "/api/v1/info",
            params={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["metadata"]["id"] == "dQw4w9WgXcQ"
        assert data["metadata"]["title"] == "Rick Astley - Never Gonna Give You Up"
    
    def test_info_endpoint_invalid_url(self, client, mock_database, mock_storage):
        """Test video info endpoint with invalid URL."""
        response = client.get(
            "/api/v1/info",
            params={"url": "https://www.google.com"}
        )
        
        assert response.status_code == 422  # Validation error
    
    @patch("app.routers.downloads.validate_api_key")  
    @patch("app.core.database.get_db")
    def test_jobs_endpoint_success(self, mock_get_db, mock_validate, client, mock_database, mock_storage, admin_api_key):
        """Test jobs listing endpoint."""
        # Mock API key validation
        mock_validate.return_value = MagicMock(
            permission_level="admin",
            is_valid=True
        )
        
        # Mock database query
        mock_session = AsyncMock()
        mock_result = MagicMock()
        
        # Mock job objects
        mock_job1 = MagicMock()
        mock_job1.to_dict.return_value = {"job_id": "job1", "status": "completed"}
        mock_job2 = MagicMock()
        mock_job2.to_dict.return_value = {"job_id": "job2", "status": "processing"}
        
        mock_result.scalars.return_value.all.return_value = [mock_job1, mock_job2]
        mock_session.execute.return_value = mock_result
        
        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2
        mock_session.execute.return_value = mock_count_result
        
        mock_get_db.return_value.__aenter__.return_value = mock_session
        
        response = client.get(
            "/api/v1/jobs",
            headers={"X-API-Key": admin_api_key}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert len(data["jobs"]) == 2