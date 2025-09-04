"""
Unit tests for storage handlers.

Tests abstract storage interface, local storage, S3 storage, and factory functions.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Optional

from botocore.exceptions import ClientError, NoCredentialsError

from app.core.storage import (
    StorageHandler, LocalStorageHandler, S3StorageHandler,
    get_storage_handler, init_storage, health_check_storage
)


class TestStorageHandlerAbstractInterface:
    """Test the abstract StorageHandler interface."""
    
    def test_cannot_instantiate_abstract_class(self):
        """Test that StorageHandler cannot be directly instantiated."""
        with pytest.raises(TypeError):
            StorageHandler()
    
    def test_abstract_methods_defined(self):
        """Test that all required abstract methods are defined."""
        abstract_methods = StorageHandler.__abstractmethods__
        expected_methods = {
            'save_file', 'get_file', 'delete_file', 'file_exists',
            'get_file_url', 'get_file_size', 'list_files'
        }
        assert abstract_methods == expected_methods
    
    def test_subclass_must_implement_all_methods(self):
        """Test that subclasses must implement all abstract methods."""
        class IncompleteHandler(StorageHandler):
            async def save_file(self, file_path: str, content: bytes) -> bool:
                return True
        
        # Should fail because not all abstract methods are implemented
        with pytest.raises(TypeError):
            IncompleteHandler()


class TestLocalStorageHandler:
    """Test LocalStorageHandler functionality."""
    
    @pytest.fixture
    def temp_base_path(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
    
    @pytest.fixture
    def local_handler(self, temp_base_path):
        """Create LocalStorageHandler with temporary base path."""
        return LocalStorageHandler(base_path=temp_base_path)
    
    def test_initialization_with_custom_path(self, temp_base_path):
        """Test LocalStorageHandler initialization with custom path."""
        handler = LocalStorageHandler(base_path=temp_base_path)
        
        assert handler.base_path == Path(temp_base_path)
        assert handler.base_path.exists()
        assert handler.base_url.startswith("http://")
    
    def test_initialization_with_default_path(self):
        """Test LocalStorageHandler initialization with default settings path."""
        with patch('app.core.storage.settings') as mock_settings:
            mock_settings.download_base_path = "./test_downloads"
            mock_settings.host = "localhost"
            mock_settings.port = 8080
            
            handler = LocalStorageHandler()
            
            assert str(handler.base_path).endswith("test_downloads")
            assert "localhost:8080" in handler.base_url
    
    def test_get_full_path(self, local_handler):
        """Test _get_full_path helper method."""
        # Test with leading slash
        result = local_handler._get_full_path("/videos/test.mp4")
        expected = local_handler.base_path / "videos" / "test.mp4"
        assert result == expected
        
        # Test without leading slash
        result = local_handler._get_full_path("videos/test.mp4")
        expected = local_handler.base_path / "videos" / "test.mp4"
        assert result == expected
        
        # Test with empty path
        result = local_handler._get_full_path("")
        expected = local_handler.base_path
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_save_file_success(self, local_handler):
        """Test successful file saving."""
        test_content = b"Hello, World!"
        file_path = "test/hello.txt"
        
        result = await local_handler.save_file(file_path, test_content)
        
        assert result is True
        
        # Verify file was actually created
        full_path = local_handler._get_full_path(file_path)
        assert full_path.exists()
        assert full_path.read_bytes() == test_content
    
    @pytest.mark.asyncio
    async def test_save_file_creates_directories(self, local_handler):
        """Test that save_file creates parent directories."""
        test_content = b"Test content"
        file_path = "deep/nested/directory/structure/file.txt"
        
        result = await local_handler.save_file(file_path, test_content)
        
        assert result is True
        full_path = local_handler._get_full_path(file_path)
        assert full_path.exists()
        assert full_path.parent.exists()
    
    @pytest.mark.asyncio
    async def test_save_file_failure(self, local_handler):
        """Test file saving failure handling."""
        # Mock aiofiles.open to raise an exception
        with patch('app.core.storage.aiofiles.open', side_effect=PermissionError("Access denied")):
            result = await local_handler.save_file("test.txt", b"content")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_file_success(self, local_handler):
        """Test successful file retrieval."""
        test_content = b"Hello, World!"
        file_path = "test/hello.txt"
        
        # First save the file
        await local_handler.save_file(file_path, test_content)
        
        # Then retrieve it
        result = await local_handler.get_file(file_path)
        
        assert result == test_content
    
    @pytest.mark.asyncio
    async def test_get_file_not_exists(self, local_handler):
        """Test getting non-existent file."""
        result = await local_handler.get_file("nonexistent.txt")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_file_failure(self, local_handler):
        """Test file retrieval failure handling."""
        # Create a file first
        await local_handler.save_file("test.txt", b"content")
        
        # Mock aiofiles.open to raise an exception
        with patch('app.core.storage.aiofiles.open', side_effect=PermissionError("Access denied")):
            result = await local_handler.get_file("test.txt")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_file_success(self, local_handler):
        """Test successful file deletion."""
        test_content = b"Hello, World!"
        file_path = "test/hello.txt"
        
        # First save the file
        await local_handler.save_file(file_path, test_content)
        full_path = local_handler._get_full_path(file_path)
        assert full_path.exists()
        
        # Then delete it
        result = await local_handler.delete_file(file_path)
        
        assert result is True
        assert not full_path.exists()
    
    @pytest.mark.asyncio
    async def test_delete_file_not_exists(self, local_handler):
        """Test deleting non-existent file."""
        result = await local_handler.delete_file("nonexistent.txt")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_file_failure(self, local_handler):
        """Test file deletion failure handling."""
        # Create a file first
        await local_handler.save_file("test.txt", b"content")
        
        # Mock Path.unlink to raise an exception
        with patch('pathlib.Path.unlink', side_effect=PermissionError("Access denied")):
            result = await local_handler.delete_file("test.txt")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_file_exists(self, local_handler):
        """Test file existence checking."""
        file_path = "test/hello.txt"
        
        # File doesn't exist yet
        assert await local_handler.file_exists(file_path) is False
        
        # Create the file
        await local_handler.save_file(file_path, b"content")
        
        # Now it should exist
        assert await local_handler.file_exists(file_path) is True
    
    @pytest.mark.asyncio
    async def test_file_exists_failure(self, local_handler):
        """Test file existence checking failure handling."""
        with patch('pathlib.Path.exists', side_effect=PermissionError("Access denied")):
            result = await local_handler.file_exists("test.txt")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_file_url(self, local_handler):
        """Test file URL generation."""
        file_path = "test/hello.txt"
        
        # Create the file
        await local_handler.save_file(file_path, b"content")
        
        # Get URL
        url = await local_handler.get_file_url(file_path)
        
        assert url is not None
        assert url.startswith("http://")
        assert "test/hello.txt" in url
    
    @pytest.mark.asyncio
    async def test_get_file_url_not_exists(self, local_handler):
        """Test URL generation for non-existent file."""
        url = await local_handler.get_file_url("nonexistent.txt")
        assert url is None
    
    @pytest.mark.asyncio
    async def test_get_file_size(self, local_handler):
        """Test file size retrieval."""
        test_content = b"Hello, World!"
        file_path = "test/hello.txt"
        
        # Create the file
        await local_handler.save_file(file_path, test_content)
        
        # Get size
        size = await local_handler.get_file_size(file_path)
        
        assert size == len(test_content)
    
    @pytest.mark.asyncio
    async def test_get_file_size_not_exists(self, local_handler):
        """Test file size for non-existent file."""
        size = await local_handler.get_file_size("nonexistent.txt")
        assert size is None
    
    @pytest.mark.asyncio
    async def test_get_file_size_failure(self, local_handler):
        """Test file size retrieval failure handling."""
        await local_handler.save_file("test.txt", b"content")
        
        with patch('pathlib.Path.stat', side_effect=PermissionError("Access denied")):
            size = await local_handler.get_file_size("test.txt")
            assert size is None
    
    @pytest.mark.asyncio
    async def test_list_files(self, local_handler):
        """Test file listing."""
        # Create some test files
        files = [
            "videos/video1.mp4",
            "videos/video2.mp4", 
            "audio/audio1.mp3",
            "documents/readme.txt"
        ]
        
        for file_path in files:
            await local_handler.save_file(file_path, b"content")
        
        # List all files
        all_files = await local_handler.list_files()
        assert len(all_files) == 4
        
        # List files in videos directory
        video_files = await local_handler.list_files("videos")
        assert len(video_files) == 2
        assert "videos/video1.mp4" in video_files
        assert "videos/video2.mp4" in video_files
        
        # List with pattern
        mp4_files = await local_handler.list_files("", "*.mp4")
        assert len(mp4_files) == 2
    
    @pytest.mark.asyncio
    async def test_list_files_empty_directory(self, local_handler):
        """Test listing files in empty directory."""
        files = await local_handler.list_files("nonexistent")
        assert files == []
    
    @pytest.mark.asyncio
    async def test_list_files_failure(self, local_handler):
        """Test file listing failure handling."""
        with patch('pathlib.Path.glob', side_effect=PermissionError("Access denied")):
            files = await local_handler.list_files()
            assert files == []


class TestS3StorageHandler:
    """Test S3StorageHandler functionality."""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Mock S3 client."""
        mock_client = Mock()
        
        # Mock successful responses
        mock_client.head_bucket.return_value = {}
        mock_client.put_object.return_value = {'ETag': '"mock-etag"'}
        mock_client.get_object.return_value = {
            'Body': Mock(read=Mock(return_value=b"test content"))
        }
        mock_client.delete_object.return_value = {}
        mock_client.head_object.return_value = {'ContentLength': 12}
        mock_client.list_objects_v2.return_value = {
            'Contents': [
                {'Key': 'videos/test1.mp4'},
                {'Key': 'videos/test2.mp4'}
            ]
        }
        mock_client.generate_presigned_url.return_value = "https://signed-url.com/test"
        
        return mock_client
    
    @patch('app.core.storage.boto3.client')
    def test_initialization_success(self, mock_boto3_client, mock_s3_client):
        """Test successful S3StorageHandler initialization."""
        mock_boto3_client.return_value = mock_s3_client
        
        handler = S3StorageHandler(
            bucket_name="test-bucket",
            region="us-west-2",
            cloudfront_domain="https://cdn.example.com"
        )
        
        assert handler.bucket_name == "test-bucket"
        assert handler.region == "us-west-2"
        assert handler.cloudfront_domain == "https://cdn.example.com"
        mock_boto3_client.assert_called_once_with('s3', region_name='us-west-2')
        mock_s3_client.head_bucket.assert_called_once_with(Bucket='test-bucket')
    
    @patch('app.core.storage.boto3.client')
    def test_initialization_no_bucket_name(self, mock_boto3_client):
        """Test S3StorageHandler initialization without bucket name."""
        with pytest.raises(ValueError, match="S3 bucket name is required"):
            S3StorageHandler(bucket_name=None)
    
    @patch('app.core.storage.boto3.client')
    def test_initialization_no_credentials(self, mock_boto3_client):
        """Test S3StorageHandler initialization with no credentials."""
        mock_boto3_client.side_effect = NoCredentialsError()
        
        with pytest.raises(NoCredentialsError):
            S3StorageHandler(bucket_name="test-bucket")
    
    @patch('app.core.storage.boto3.client')
    def test_initialization_bucket_access_error(self, mock_boto3_client, mock_s3_client):
        """Test S3StorageHandler initialization with bucket access error."""
        mock_s3_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket'}}, 'HeadBucket'
        )
        mock_boto3_client.return_value = mock_s3_client
        
        with pytest.raises(ClientError):
            S3StorageHandler(bucket_name="nonexistent-bucket")
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_save_file_success(self, mock_boto3_client, mock_s3_client):
        """Test successful file saving to S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.save_file("videos/test.mp4", b"video content")
        
        assert result is True
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args[1]
        assert call_args['Bucket'] == 'test-bucket'
        assert call_args['Key'] == 'videos/test.mp4'
        assert call_args['Body'] == b'video content'
        assert call_args['ContentType'] == 'video/mp4'
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_save_file_failure(self, mock_boto3_client, mock_s3_client):
        """Test file saving failure to S3."""
        mock_s3_client.put_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied'}}, 'PutObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.save_file("videos/test.mp4", b"video content")
        
        assert result is False
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_success(self, mock_boto3_client, mock_s3_client):
        """Test successful file retrieval from S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.get_file("videos/test.mp4")
        
        assert result == b"test content"
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket', Key='videos/test.mp4'
        )
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_not_exists(self, mock_boto3_client, mock_s3_client):
        """Test getting non-existent file from S3."""
        mock_s3_client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey'}}, 'GetObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.get_file("nonexistent.mp4")
        
        assert result is None
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_delete_file_success(self, mock_boto3_client, mock_s3_client):
        """Test successful file deletion from S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.delete_file("videos/test.mp4")
        
        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket='test-bucket', Key='videos/test.mp4'
        )
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_delete_file_failure(self, mock_boto3_client, mock_s3_client):
        """Test file deletion failure from S3."""
        mock_s3_client.delete_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied'}}, 'DeleteObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.delete_file("videos/test.mp4")
        
        assert result is False
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_file_exists_true(self, mock_boto3_client, mock_s3_client):
        """Test file exists in S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.file_exists("videos/test.mp4")
        
        assert result is True
        mock_s3_client.head_object.assert_called_once_with(
            Bucket='test-bucket', Key='videos/test.mp4'
        )
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_file_exists_false(self, mock_boto3_client, mock_s3_client):
        """Test file doesn't exist in S3."""
        mock_s3_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.file_exists("nonexistent.mp4")
        
        assert result is False
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_url_with_cloudfront(self, mock_boto3_client, mock_s3_client):
        """Test file URL generation with CloudFront."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(
            bucket_name="test-bucket",
            cloudfront_domain="d123456.cloudfront.net"
        )
        
        url = await handler.get_file_url("videos/test.mp4")
        
        assert url == "https://d123456.cloudfront.net/videos/test.mp4"
        # Should not call generate_presigned_url when using CloudFront
        mock_s3_client.generate_presigned_url.assert_not_called()
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_url_signed(self, mock_boto3_client, mock_s3_client):
        """Test signed URL generation."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        url = await handler.get_file_url("videos/test.mp4", expiry=1800)
        
        assert url == "https://signed-url.com/test"
        mock_s3_client.generate_presigned_url.assert_called_once()
        call_args = mock_s3_client.generate_presigned_url.call_args
        assert call_args[0][0] == 'get_object'
        assert call_args[1]['ExpiresIn'] == 1800
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_url_not_exists(self, mock_boto3_client, mock_s3_client):
        """Test URL generation for non-existent file."""
        mock_s3_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        url = await handler.get_file_url("nonexistent.mp4")
        
        assert url is None
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_size_success(self, mock_boto3_client, mock_s3_client):
        """Test file size retrieval from S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        size = await handler.get_file_size("videos/test.mp4")
        
        assert size == 12
        mock_s3_client.head_object.assert_called_once_with(
            Bucket='test-bucket', Key='videos/test.mp4'
        )
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_get_file_size_not_exists(self, mock_boto3_client, mock_s3_client):
        """Test file size for non-existent file in S3."""
        mock_s3_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        size = await handler.get_file_size("nonexistent.mp4")
        
        assert size is None
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_list_files_success(self, mock_boto3_client, mock_s3_client):
        """Test file listing from S3."""
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        files = await handler.list_files("videos")
        
        assert files == ["videos/test1.mp4", "videos/test2.mp4"]
        mock_s3_client.list_objects_v2.assert_called_once_with(
            Bucket='test-bucket', Prefix='videos/'
        )
    
    @patch('app.core.storage.boto3.client')
    @pytest.mark.asyncio
    async def test_list_files_empty(self, mock_boto3_client, mock_s3_client):
        """Test file listing from empty S3 directory."""
        mock_s3_client.list_objects_v2.return_value = {}  # No Contents key
        mock_boto3_client.return_value = mock_s3_client
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        files = await handler.list_files("empty-dir")
        
        assert files == []
    
    def test_get_content_type(self):
        """Test content type determination based on file extension."""
        # We can't instantiate S3StorageHandler without mocking boto3,
        # but we can test the content type mapping logic
        with patch('app.core.storage.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_client.head_bucket.return_value = {}
            mock_boto3.return_value = mock_client
            
            handler = S3StorageHandler(bucket_name="test-bucket")
            
            # Test various file types
            assert handler._get_content_type("video.mp4") == "video/mp4"
            assert handler._get_content_type("video.mkv") == "video/x-matroska"
            assert handler._get_content_type("audio.mp3") == "audio/mpeg"
            assert handler._get_content_type("subtitle.srt") == "text/srt"
            assert handler._get_content_type("thumb.jpg") == "image/jpeg"
            assert handler._get_content_type("unknown.xyz") == "application/octet-stream"


class TestStorageFactory:
    """Test storage factory functions."""
    
    @patch('app.core.storage.settings')
    def test_get_storage_handler_local_environment(self, mock_settings):
        """Test get_storage_handler returns LocalStorageHandler for local environment."""
        mock_settings.environment = "localhost"
        mock_settings.download_base_path = "./downloads"
        mock_settings.host = "localhost"
        mock_settings.port = 8000
        
        with patch('app.core.storage.LocalStorageHandler') as mock_local:
            mock_local.return_value = Mock()
            
            handler = get_storage_handler()
            
            mock_local.assert_called_once_with("./downloads")
            assert handler == mock_local.return_value
    
    @patch('app.core.storage.settings')
    @patch('app.core.storage.S3StorageHandler')
    def test_get_storage_handler_aws_environment(self, mock_s3_handler, mock_settings):
        """Test get_storage_handler returns S3StorageHandler for AWS environment."""
        mock_settings.environment = "aws"
        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_region = "us-west-2"
        mock_settings.s3_cloudfront_domain = "https://cdn.example.com"
        
        mock_s3_handler.return_value = Mock()
        
        handler = get_storage_handler()
        
        mock_s3_handler.assert_called_once_with(
            bucket_name="my-bucket",
            region="us-west-2",
            cloudfront_domain="https://cdn.example.com"
        )
        assert handler == mock_s3_handler.return_value
    
    @patch('app.core.storage.settings')
    def test_get_storage_handler_aws_no_bucket_fallback(self, mock_settings):
        """Test get_storage_handler falls back to local when S3 bucket not configured."""
        mock_settings.environment = "aws"
        mock_settings.s3_bucket_name = None
        mock_settings.download_base_path = "./downloads"
        mock_settings.host = "localhost"
        mock_settings.port = 8000
        
        with patch('app.core.storage.LocalStorageHandler') as mock_local:
            mock_local.return_value = Mock()
            
            handler = get_storage_handler()
            
            mock_local.assert_called_once()
            assert handler == mock_local.return_value
    
    @patch('app.core.storage.settings')
    @patch('app.core.storage.S3StorageHandler')
    def test_get_storage_handler_exception_fallback(self, mock_s3_handler, mock_settings):
        """Test get_storage_handler falls back to local on exception."""
        mock_settings.environment = "aws"
        mock_settings.s3_bucket_name = "my-bucket"
        
        # S3StorageHandler raises an exception
        mock_s3_handler.side_effect = Exception("S3 initialization failed")
        
        with patch('app.core.storage.LocalStorageHandler') as mock_local:
            mock_local.return_value = Mock()
            
            handler = get_storage_handler()
            
            # Should fall back to LocalStorageHandler
            mock_local.assert_called_once()
            assert handler == mock_local.return_value
    
    def test_init_storage_creates_singleton(self):
        """Test init_storage creates and reuses storage singleton."""
        # Reset the global storage variable
        import app.core.storage
        app.core.storage.storage = None
        
        with patch('app.core.storage.get_storage_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_get_handler.return_value = mock_handler
            
            # First call should create storage
            handler1 = init_storage()
            assert handler1 == mock_handler
            mock_get_handler.assert_called_once()
            
            # Second call should reuse existing storage
            handler2 = init_storage()
            assert handler2 == mock_handler
            assert handler1 is handler2
            # get_storage_handler should not be called again
            assert mock_get_handler.call_count == 1
    
    @pytest.mark.asyncio
    async def test_health_check_storage_success(self):
        """Test successful storage health check."""
        mock_handler = Mock()
        mock_handler.save_file = AsyncMock(return_value=True)
        mock_handler.get_file = AsyncMock(return_value=b"Health check test content")
        mock_handler.delete_file = AsyncMock(return_value=True)
        
        with patch('app.core.storage.init_storage', return_value=mock_handler):
            result = await health_check_storage()
            
            assert result["status"] == "healthy"
            assert result["storage_type"] == "Mock"
            
            # Verify all operations were called
            mock_handler.save_file.assert_called_once()
            mock_handler.get_file.assert_called_once()
            mock_handler.delete_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_health_check_storage_save_failure(self):
        """Test health check with save failure."""
        mock_handler = Mock()
        mock_handler.save_file = AsyncMock(return_value=False)
        
        with patch('app.core.storage.init_storage', return_value=mock_handler):
            result = await health_check_storage()
            
            assert result["status"] == "unhealthy"
            assert result["error"] == "Failed to save test file"
    
    @pytest.mark.asyncio
    async def test_health_check_storage_content_mismatch(self):
        """Test health check with content mismatch."""
        mock_handler = Mock()
        mock_handler.save_file = AsyncMock(return_value=True)
        mock_handler.get_file = AsyncMock(return_value=b"Wrong content")
        
        with patch('app.core.storage.init_storage', return_value=mock_handler):
            result = await health_check_storage()
            
            assert result["status"] == "unhealthy"
            assert result["error"] == "Retrieved content doesn't match saved content"
    
    @pytest.mark.asyncio
    async def test_health_check_storage_delete_failure(self):
        """Test health check with delete failure."""
        mock_handler = Mock()
        mock_handler.save_file = AsyncMock(return_value=True)
        mock_handler.get_file = AsyncMock(return_value=b"Health check test content")
        mock_handler.delete_file = AsyncMock(return_value=False)
        
        with patch('app.core.storage.init_storage', return_value=mock_handler):
            result = await health_check_storage()
            
            assert result["status"] == "unhealthy"
            assert result["error"] == "Failed to delete test file"
    
    @pytest.mark.asyncio
    async def test_health_check_storage_exception(self):
        """Test health check with exception."""
        with patch('app.core.storage.init_storage', side_effect=Exception("Storage error")):
            result = await health_check_storage()
            
            assert result["status"] == "unhealthy"
            assert result["storage_type"] == "unknown"
            assert result["error"] == "Storage error"