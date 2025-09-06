from abc import ABC, abstractmethod
from typing import Optional, Union, Dict, Any
import os
import asyncio
from pathlib import Path
import logging
import shutil
from urllib.parse import urljoin
import aiofiles

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageHandler(ABC):
    """
    Abstract base class for file storage handlers.
    
    Provides a unified interface for different storage backends
    (local filesystem, AWS S3, etc.).
    """

    @abstractmethod
    async def save_file(self, file_path: str, content: bytes) -> bool:
        """
        Save file content to storage.
        
        Args:
            file_path: Path where the file should be saved
            content: File content as bytes
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def get_file(self, file_path: str) -> Optional[bytes]:
        """
        Retrieve file content from storage.
        
        Args:
            file_path: Path to the file
            
        Returns:
            bytes: File content, None if file doesn't exist
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            file_path: Path to the file to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            file_path: Path to the file
            
        Returns:
            bool: True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_file_url(self, file_path: str, expiry: int = 3600) -> Optional[str]:
        """
        Get a URL to access the file.
        
        Args:
            file_path: Path to the file
            expiry: URL expiry time in seconds (for signed URLs)
            
        Returns:
            str: Accessible URL, None if file doesn't exist
        """
        pass

    @abstractmethod
    async def get_file_size(self, file_path: str) -> Optional[int]:
        """
        Get the size of a file in bytes.
        
        Args:
            file_path: Path to the file
            
        Returns:
            int: File size in bytes, None if file doesn't exist
        """
        pass

    @abstractmethod
    async def list_files(self, directory: str = "", pattern: str = "*") -> list[str]:
        """
        List files in a directory.
        
        Args:
            directory: Directory path to list
            pattern: File pattern to match
            
        Returns:
            list[str]: List of file paths
        """
        pass


class LocalStorageHandler(StorageHandler):
    """
    Local filesystem storage handler.
    
    Stores files on the local filesystem, suitable for development
    and single-server deployments.
    """

    def __init__(self, base_path: str = None):
        """
        Initialize local storage handler.
        
        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path or settings.download_base_path)
        self.base_url = f"http://{settings.host}:{settings.port}/files"
        
        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"LocalStorageHandler initialized with base_path: {self.base_path}")

    def _get_full_path(self, file_path: str) -> Path:
        """Get the full filesystem path for a relative file path."""
        # Remove leading slash if present
        file_path = file_path.lstrip("/")
        return self.base_path / file_path

    async def save_file(self, file_path: str, content: bytes) -> bool:
        """Save file content to local filesystem."""
        try:
            full_path = self._get_full_path(file_path)
            
            # Create parent directories if they don't exist
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file asynchronously
            async with aiofiles.open(full_path, 'wb') as f:
                await f.write(content)
            
            logger.debug(f"File saved: {full_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save file {file_path}: {e}")
            return False

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content from local filesystem."""
        try:
            full_path = self._get_full_path(file_path)
            
            if not full_path.exists():
                return None
            
            async with aiofiles.open(full_path, 'rb') as f:
                content = await f.read()
            
            logger.debug(f"File retrieved: {full_path}")
            return content
            
        except Exception as e:
            logger.error(f"Failed to get file {file_path}: {e}")
            return None

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from local filesystem."""
        try:
            full_path = self._get_full_path(file_path)
            
            if full_path.exists():
                full_path.unlink()
                logger.debug(f"File deleted: {full_path}")
                return True
            else:
                logger.warning(f"File not found for deletion: {full_path}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists on local filesystem."""
        try:
            full_path = self._get_full_path(file_path)
            return full_path.exists()
        except Exception as e:
            logger.error(f"Failed to check file existence {file_path}: {e}")
            return False

    async def get_file_url(self, file_path: str, expiry: int = 3600) -> Optional[str]:
        """Get a URL to access the file via HTTP."""
        try:
            if not await self.file_exists(file_path):
                return None
            
            # Remove leading slash and construct URL
            clean_path = file_path.lstrip("/")
            return f"{self.base_url}/{clean_path}"
            
        except Exception as e:
            logger.error(f"Failed to generate file URL {file_path}: {e}")
            return None

    async def get_file_size(self, file_path: str) -> Optional[int]:
        """Get the size of a file in bytes."""
        try:
            full_path = self._get_full_path(file_path)
            
            if not full_path.exists():
                return None
            
            return full_path.stat().st_size
            
        except Exception as e:
            logger.error(f"Failed to get file size {file_path}: {e}")
            return None

    async def list_files(self, directory: str = "", pattern: str = "*") -> list[str]:
        """List files in a directory."""
        try:
            full_dir = self._get_full_path(directory)
            
            if not full_dir.exists():
                return []
            
            # Use pathlib glob pattern matching
            files = []
            for file_path in full_dir.glob(pattern):
                if file_path.is_file():
                    # Return relative path from base_path
                    relative_path = file_path.relative_to(self.base_path)
                    files.append(str(relative_path))
            
            return sorted(files)
            
        except Exception as e:
            logger.error(f"Failed to list files in {directory}: {e}")
            return []


class S3StorageHandler(StorageHandler):
    """
    AWS S3 storage handler.
    
    Stores files in AWS S3, suitable for production deployments
    with scalability and CDN integration.
    """

    def __init__(self, bucket_name: str = None, region: str = None, cloudfront_domain: str = None):
        """
        Initialize S3 storage handler.
        
        Args:
            bucket_name: S3 bucket name
            region: AWS region
            cloudfront_domain: CloudFront distribution domain for CDN URLs
        """
        self.bucket_name = bucket_name or settings.s3_bucket_name
        self.region = region or settings.aws_region
        self.cloudfront_domain = cloudfront_domain or getattr(settings, 's3_cloudfront_domain', None)
        
        if not self.bucket_name:
            raise ValueError("S3 bucket name is required")
        
        try:
            # Initialize S3 client
            self.s3_client = boto3.client('s3', region_name=self.region)
            
            # Verify bucket exists and is accessible
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            
            logger.info(f"S3StorageHandler initialized with bucket: {self.bucket_name}")
            
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise
        except ClientError as e:
            logger.error(f"Failed to access S3 bucket {self.bucket_name}: {e}")
            raise

    async def save_file(self, file_path: str, content: bytes) -> bool:
        """Save file content to S3."""
        try:
            # Remove leading slash
            key = file_path.lstrip("/")
            
            # Upload to S3 asynchronously
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=content,
                    ContentType=self._get_content_type(file_path)
                )
            )
            
            logger.debug(f"File uploaded to S3: s3://{self.bucket_name}/{key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save file to S3 {file_path}: {e}")
            return False

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content from S3."""
        try:
            key = file_path.lstrip("/")
            
            # Download from S3 asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            )
            
            content = response['Body'].read()
            logger.debug(f"File downloaded from S3: s3://{self.bucket_name}/{key}")
            return content
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            logger.error(f"Failed to get file from S3 {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get file from S3 {file_path}: {e}")
            return None

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from S3."""
        try:
            key = file_path.lstrip("/")
            
            # Delete from S3 asynchronously
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            )
            
            logger.debug(f"File deleted from S3: s3://{self.bucket_name}/{key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file from S3 {file_path}: {e}")
            return False

    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in S3."""
        try:
            key = file_path.lstrip("/")
            
            # Check object existence asynchronously
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            )
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"Failed to check file existence in S3 {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to check file existence in S3 {file_path}: {e}")
            return False

    async def get_file_url(self, file_path: str, expiry: int = 3600) -> Optional[str]:
        """Get a URL to access the file (signed URL or CloudFront URL)."""
        try:
            if not await self.file_exists(file_path):
                return None
            
            key = file_path.lstrip("/")
            
            # Use CloudFront URL if available
            if self.cloudfront_domain:
                return f"https://{self.cloudfront_domain}/{key}"
            
            # Generate signed URL
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                None,
                lambda: self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': key},
                    ExpiresIn=expiry
                )
            )
            
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate file URL for S3 {file_path}: {e}")
            return None

    async def get_file_size(self, file_path: str) -> Optional[int]:
        """Get the size of a file in S3."""
        try:
            key = file_path.lstrip("/")
            
            # Get object metadata asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            )
            
            return response['ContentLength']
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            logger.error(f"Failed to get file size from S3 {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to get file size from S3 {file_path}: {e}")
            return None

    async def list_files(self, directory: str = "", pattern: str = "*") -> list[str]:
        """List files in an S3 directory."""
        try:
            prefix = directory.lstrip("/")
            if prefix and not prefix.endswith("/"):
                prefix += "/"
            
            # List objects asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    # Simple pattern matching (could be enhanced)
                    if pattern == "*" or pattern in key:
                        files.append(key)
            
            return sorted(files)
            
        except Exception as e:
            logger.error(f"Failed to list files in S3 {directory}: {e}")
            return []

    def _get_content_type(self, file_path: str) -> str:
        """Determine content type based on file extension."""
        extension = Path(file_path).suffix.lower()
        content_types = {
            '.mp4': 'video/mp4',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.wav': 'audio/wav',
            '.srt': 'text/srt',
            '.vtt': 'text/vtt',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
        }
        return content_types.get(extension, 'application/octet-stream')


def get_storage_handler() -> StorageHandler:
    """
    Factory function to get the appropriate storage handler based on environment.
    
    Returns:
        StorageHandler: Configured storage handler instance
    """
    try:
        if settings.environment in ["aws", "dev", "staging", "production"]:
            # AWS/Production environment - use S3
            if not hasattr(settings, 's3_bucket_name') or not settings.s3_bucket_name:
                logger.warning("S3 bucket not configured, falling back to local storage")
                return LocalStorageHandler()
            
            return S3StorageHandler(
                bucket_name=settings.s3_bucket_name,
                region=getattr(settings, 'aws_region', 'us-east-1'),
                cloudfront_domain=getattr(settings, 's3_cloudfront_domain', None)
            )
        else:
            # Local/Development environment - use local filesystem
            return LocalStorageHandler(settings.download_base_path)
            
    except Exception as e:
        logger.error(f"Failed to initialize storage handler: {e}")
        # Fall back to local storage
        logger.info("Falling back to local storage handler")
        return LocalStorageHandler()


# Global storage handler instance
storage: Optional[StorageHandler] = None


def init_storage() -> StorageHandler:
    """Initialize and return the global storage handler."""
    global storage
    if storage is None:
        storage = get_storage_handler()
    return storage


async def health_check_storage() -> Dict[str, Any]:
    """
    Perform a health check on the storage system.
    
    Returns:
        dict: Health check results
    """
    try:
        storage_handler = init_storage()
        
        # Test basic operations
        test_file = "health_check_test.txt"
        test_content = b"Health check test content"
        
        # Test save
        save_success = await storage_handler.save_file(test_file, test_content)
        if not save_success:
            return {
                "status": "unhealthy",
                "storage_type": type(storage_handler).__name__,
                "error": "Failed to save test file"
            }
        
        # Test retrieve
        retrieved_content = await storage_handler.get_file(test_file)
        if retrieved_content != test_content:
            return {
                "status": "unhealthy", 
                "storage_type": type(storage_handler).__name__,
                "error": "Retrieved content doesn't match saved content"
            }
        
        # Test delete
        delete_success = await storage_handler.delete_file(test_file)
        if not delete_success:
            return {
                "status": "unhealthy",
                "storage_type": type(storage_handler).__name__, 
                "error": "Failed to delete test file"
            }
        
        return {
            "status": "healthy",
            "storage_type": type(storage_handler).__name__,
            "base_path": getattr(storage_handler, 'base_path', None),
            "bucket_name": getattr(storage_handler, 'bucket_name', None),
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "storage_type": "unknown",
            "error": str(e)
        }