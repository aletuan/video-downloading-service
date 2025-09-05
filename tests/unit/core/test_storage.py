import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.storage import (
    StorageHandler,
    LocalStorageHandler,
    S3StorageHandler,
    get_storage_handler,
    init_storage,
    health_check_storage
)


class TestLocalStorageHandler:
    """Test cases for LocalStorageHandler."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def local_storage(self, temp_dir):
        """Create a LocalStorageHandler instance with temp directory."""
        return LocalStorageHandler(base_path=temp_dir)

    def test_local_storage_init(self, temp_dir):
        """Test LocalStorageHandler initialization."""
        handler = LocalStorageHandler(base_path=temp_dir)
        assert handler.base_path == Path(temp_dir)
        assert handler.base_path.exists()

    @pytest.mark.asyncio
    async def test_save_and_get_file(self, local_storage):
        """Test saving and retrieving a file."""
        file_path = "test/example.txt"
        content = b"Hello, World!"
        
        # Save file
        result = await local_storage.save_file(file_path, content)
        assert result is True
        
        # Get file
        retrieved_content = await local_storage.get_file(file_path)
        assert retrieved_content == content

    @pytest.mark.asyncio
    async def test_file_exists(self, local_storage):
        """Test checking file existence."""
        file_path = "test/exists.txt"
        content = b"test content"
        
        # File doesn't exist initially
        assert await local_storage.file_exists(file_path) is False
        
        # Save file
        await local_storage.save_file(file_path, content)
        
        # File should exist now
        assert await local_storage.file_exists(file_path) is True

    @pytest.mark.asyncio
    async def test_delete_file(self, local_storage):
        """Test deleting a file."""
        file_path = "test/delete_me.txt"
        content = b"to be deleted"
        
        # Save file first
        await local_storage.save_file(file_path, content)
        assert await local_storage.file_exists(file_path) is True
        
        # Delete file
        result = await local_storage.delete_file(file_path)
        assert result is True
        assert await local_storage.file_exists(file_path) is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, local_storage):
        """Test deleting a file that doesn't exist."""
        result = await local_storage.delete_file("nonexistent.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_file_url(self, local_storage):
        """Test getting file URL."""
        file_path = "test/url_test.txt"
        content = b"url test content"
        
        # File doesn't exist
        url = await local_storage.get_file_url(file_path)
        assert url is None
        
        # Save file
        await local_storage.save_file(file_path, content)
        
        # Get URL
        url = await local_storage.get_file_url(file_path)
        assert url is not None
        assert "url_test.txt" in url

    @pytest.mark.asyncio
    async def test_get_file_size(self, local_storage):
        """Test getting file size."""
        file_path = "test/size_test.txt"
        content = b"size test content"
        
        # File doesn't exist
        size = await local_storage.get_file_size(file_path)
        assert size is None
        
        # Save file
        await local_storage.save_file(file_path, content)
        
        # Get size
        size = await local_storage.get_file_size(file_path)
        assert size == len(content)

    @pytest.mark.asyncio
    async def test_list_files(self, local_storage):
        """Test listing files."""
        # Initially empty
        files = await local_storage.list_files()
        assert files == []
        
        # Save some files
        await local_storage.save_file("dir1/file1.txt", b"content1")
        await local_storage.save_file("dir1/file2.txt", b"content2")
        await local_storage.save_file("dir2/file3.txt", b"content3")
        
        # List all files using recursive pattern
        files = await local_storage.list_files("", "**/*.txt")
        assert len(files) >= 3
        # Check if files exist (they might be in different order)
        file_names = [Path(f).name for f in files]
        assert "file1.txt" in file_names
        assert "file2.txt" in file_names
        assert "file3.txt" in file_names

    def test_get_full_path(self, local_storage):
        """Test _get_full_path method."""
        # Test with leading slash
        path1 = local_storage._get_full_path("/test/file.txt")
        expected1 = local_storage.base_path / "test/file.txt"
        assert path1 == expected1
        
        # Test without leading slash
        path2 = local_storage._get_full_path("test/file.txt")
        expected2 = local_storage.base_path / "test/file.txt"
        assert path2 == expected2


class TestS3StorageHandler:
    """Test cases for S3StorageHandler."""

    @pytest.fixture
    def mock_s3_client(self):
        """Create a mock S3 client."""
        with patch('boto3.client') as mock_client:
            mock_s3 = MagicMock()
            mock_client.return_value = mock_s3
            yield mock_s3

    def test_s3_storage_init_success(self, mock_s3_client):
        """Test successful S3StorageHandler initialization."""
        mock_s3_client.head_bucket.return_value = {}
        
        handler = S3StorageHandler(bucket_name="test-bucket", region="us-east-1")
        
        assert handler.bucket_name == "test-bucket"
        assert handler.region == "us-east-1"
        assert handler.s3_client == mock_s3_client
        mock_s3_client.head_bucket.assert_called_once_with(Bucket="test-bucket")

    @patch('app.core.storage.settings')
    def test_s3_storage_init_no_bucket(self, mock_settings):
        """Test S3StorageHandler initialization without bucket name."""
        mock_settings.s3_bucket_name = None
        mock_settings.aws_region = "us-east-1"
        with pytest.raises(ValueError, match="S3 bucket name is required"):
            S3StorageHandler()

    @patch('app.core.storage.settings')
    def test_s3_storage_init_no_credentials(self, mock_settings, mock_s3_client):
        """Test S3StorageHandler initialization with no credentials."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.side_effect = NoCredentialsError()
        
        with pytest.raises(NoCredentialsError):
            S3StorageHandler(bucket_name="test-bucket")

    @patch('app.core.storage.settings')
    def test_s3_storage_init_bucket_error(self, mock_settings, mock_s3_client):
        """Test S3StorageHandler initialization with bucket access error."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket'}}, 'head_bucket'
        )
        
        with pytest.raises(ClientError):
            S3StorageHandler(bucket_name="test-bucket")

    @pytest.mark.asyncio
    @patch('app.core.storage.settings')
    async def test_s3_save_file(self, mock_settings, mock_s3_client):
        """Test saving file to S3."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.put_object.return_value = {}
        
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        result = await handler.save_file("test/file.txt", b"content")
        
        assert result is True
        mock_s3_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.core.storage.settings')
    async def test_s3_get_file(self, mock_settings, mock_s3_client):
        """Test getting file from S3."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.return_value = {}
        mock_response = {'Body': MagicMock()}
        mock_response['Body'].read.return_value = b"test content"
        mock_s3_client.get_object.return_value = mock_response
        
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        content = await handler.get_file("test/file.txt")
        
        assert content == b"test content"
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.txt"
        )

    @pytest.mark.asyncio
    @patch('app.core.storage.settings')
    async def test_s3_file_exists(self, mock_settings, mock_s3_client):
        """Test checking file existence in S3."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.head_object.return_value = {}
        
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        exists = await handler.file_exists("test/file.txt")
        
        assert exists is True
        mock_s3_client.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.txt"
        )

    @patch('app.core.storage.settings')
    def test_get_content_type(self, mock_settings, mock_s3_client):
        """Test _get_content_type method."""
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        mock_s3_client.head_bucket.return_value = {}
        handler = S3StorageHandler(bucket_name="test-bucket")
        
        assert handler._get_content_type("video.mp4") == "video/mp4"
        assert handler._get_content_type("audio.mp3") == "audio/mpeg"
        assert handler._get_content_type("subtitle.srt") == "text/srt"
        assert handler._get_content_type("unknown.xyz") == "application/octet-stream"


class TestStorageFactory:
    """Test cases for storage factory functions."""

    @patch('app.core.storage.settings')
    def test_get_storage_handler_localhost(self, mock_settings):
        """Test get_storage_handler for localhost environment."""
        mock_settings.environment = "localhost"
        mock_settings.download_base_path = "/tmp/downloads"
        
        handler = get_storage_handler()
        
        assert isinstance(handler, LocalStorageHandler)

    @patch('app.core.storage.settings')
    @patch('boto3.client')
    def test_get_storage_handler_aws(self, mock_boto3_client, mock_settings):
        """Test get_storage_handler for AWS environment."""
        mock_settings.environment = "aws"
        mock_settings.s3_bucket_name = "test-bucket"
        mock_settings.aws_region = "us-east-1"
        
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.head_bucket.return_value = {}
        
        handler = get_storage_handler()
        
        assert isinstance(handler, S3StorageHandler)
        assert handler.bucket_name == "test-bucket"

    @patch('app.core.storage.settings')
    def test_get_storage_handler_fallback(self, mock_settings):
        """Test get_storage_handler fallback to local storage."""
        mock_settings.environment = "aws"
        mock_settings.s3_bucket_name = None
        mock_settings.download_base_path = "/tmp/downloads"
        
        handler = get_storage_handler()
        
        assert isinstance(handler, LocalStorageHandler)

    @patch('app.core.storage.get_storage_handler')
    def test_init_storage(self, mock_get_handler):
        """Test init_storage function."""
        mock_handler = MagicMock()
        mock_get_handler.return_value = mock_handler
        
        # First call should create new handler
        result1 = init_storage()
        assert result1 == mock_handler
        mock_get_handler.assert_called_once()
        
        # Second call should return cached handler
        mock_get_handler.reset_mock()
        result2 = init_storage()
        assert result2 == mock_handler
        mock_get_handler.assert_not_called()


@pytest.mark.asyncio
class TestStorageHealthCheck:
    """Test cases for storage health check."""

    @patch('app.core.storage.init_storage')
    async def test_health_check_storage_success(self, mock_init):
        """Test successful storage health check."""
        mock_handler = AsyncMock()
        mock_handler.save_file.return_value = True
        mock_handler.get_file.return_value = b"Health check test content"
        mock_handler.delete_file.return_value = True
        mock_init.return_value = mock_handler
        
        result = await health_check_storage()
        
        assert result["status"] == "healthy"
        assert "storage_type" in result

    @patch('app.core.storage.init_storage')
    async def test_health_check_storage_save_fail(self, mock_init):
        """Test storage health check when save fails."""
        mock_handler = AsyncMock()
        mock_handler.save_file.return_value = False
        mock_init.return_value = mock_handler
        
        result = await health_check_storage()
        
        assert result["status"] == "unhealthy"
        assert "Failed to save test file" in result["error"]

    @patch('app.core.storage.init_storage')
    async def test_health_check_storage_exception(self, mock_init):
        """Test storage health check when exception occurs."""
        mock_init.side_effect = Exception("Storage initialization failed")
        
        result = await health_check_storage()
        
        assert result["status"] == "unhealthy"
        assert result["storage_type"] == "unknown"
        assert "Storage initialization failed" in result["error"]