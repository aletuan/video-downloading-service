"""
Secure Cookie Manager for YouTube Downloads

This module provides secure cookie management functionality for bypassing
YouTube's anti-bot protection measures. It handles cookie storage, validation,
rotation, and secure temporary file creation for yt-dlp integration.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict, deque
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import boto3
import aiofiles
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings

logger = logging.getLogger(__name__)


class CookieValidationError(Exception):
    """Exception raised when cookie validation fails."""
    pass


class CookieExpiredError(Exception):
    """Exception raised when cookies have expired."""
    pass


class CookieDownloadError(Exception):
    """Exception raised when cookie download from S3 fails."""
    pass


class CookieRateLimitError(Exception):
    """Exception raised when cookie access rate limit is exceeded."""
    pass


class CookieIntegrityError(Exception):
    """Exception raised when cookie integrity validation fails."""
    pass


class CookieManager:
    """
    Secure cookie manager for YouTube download authentication.
    
    Provides secure cookie storage, validation, rotation, and temporary file
    creation for yt-dlp integration while maintaining security best practices.
    """
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        encryption_key: Optional[str] = None,
        aws_region: Optional[str] = None
    ):
        """
        Initialize the secure cookie manager.
        
        Args:
            bucket_name: S3 bucket name for cookie storage
            encryption_key: Key for in-memory cookie encryption
            aws_region: AWS region for S3 operations
        """
        self.bucket_name = bucket_name or settings.cookie_s3_bucket
        self.aws_region = aws_region or settings.aws_region
        self.encryption_key = encryption_key or settings.cookie_encryption_key
        
        # Initialize encryption
        self._cipher_suite = self._initialize_encryption()
        
        # Initialize S3 client
        self._s3_client = self._initialize_s3_client()
        
        # Cookie storage paths
        self.active_cookie_key = "cookies/youtube-cookies-active.txt"
        self.backup_cookie_key = "cookies/youtube-cookies-backup.txt"
        self.metadata_key = "cookies/metadata.json"
        
        # Temporary file management
        self.temp_dir = Path(settings.cookie_temp_dir or tempfile.gettempdir()) / "youtube_cookies"
        self.temp_dir.mkdir(exist_ok=True, mode=0o700)  # Secure permissions
        
        # In-memory cookie cache (encrypted)
        self._encrypted_cache: Dict[str, bytes] = {}
        self._cache_timestamps: Dict[str, float] = {}
        
        # Configuration
        self.cache_ttl = settings.cookie_refresh_interval * 60  # Convert minutes to seconds
        self.validation_enabled = settings.cookie_validation_enabled
        self.backup_count = settings.cookie_backup_count
        
        # Rate limiting for cookie access
        self.rate_limit_window = 60  # 1 minute window
        self.rate_limit_requests = 10  # Max 10 requests per minute per IP/session
        self._rate_limit_tracker: Dict[str, deque] = defaultdict(deque)
        
        # Cookie integrity tracking
        self._cookie_hashes: Dict[str, str] = {}  # Track cookie file hashes
        self._integrity_checks_enabled = True
        
        logger.info(
            f"CookieManager initialized: bucket={self.bucket_name}, "
            f"region={self.aws_region}, encryption_enabled=True"
        )
    
    def _initialize_encryption(self) -> Fernet:
        """Initialize encryption for in-memory cookie storage."""
        if not self.encryption_key:
            raise ValueError("Cookie encryption key is required")
        
        # Derive encryption key from provided key using PBKDF2
        password = self.encryption_key.encode('utf-8')
        salt = b'youtube_cookie_salt'  # In production, use a random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return Fernet(key)
    
    def _initialize_s3_client(self):
        """Initialize S3 client with proper configuration."""
        try:
            return boto3.client('s3', region_name=self.aws_region)
        except NoCredentialsError as e:
            logger.error(f"AWS credentials not configured: {e}")
            raise CookieDownloadError(f"AWS credentials not configured: {e}")
    
    async def get_active_cookies(self, identifier: str = "global") -> str:
        """
        Get active cookies as temporary file path for yt-dlp.
        
        Args:
            identifier: Unique identifier for rate limiting (IP, session, etc.)
        
        Returns:
            str: Path to temporary cookie file
            
        Raises:
            CookieDownloadError: If cookie download fails
            CookieValidationError: If cookies are invalid
            CookieExpiredError: If cookies have expired
            CookieRateLimitError: If rate limit is exceeded
            CookieIntegrityError: If cookie integrity validation fails
        """
        try:
            # Check rate limit first
            self._check_rate_limit(identifier)
            
            # Check cache first
            if self._is_cache_valid('active'):
                logger.debug("Using cached active cookies")
                cookies_content = self._decrypt_from_cache('active')
            else:
                # Download from S3
                logger.info("Downloading active cookies from S3")
                cookies_content = await self._download_cookie_file(self.active_cookie_key)
                
                # Validate cookie integrity
                self._validate_cookie_integrity(cookies_content, 'active')
                
                # Validate cookies if enabled
                if self.validation_enabled:
                    await self._validate_cookies(cookies_content)
                
                # Cache encrypted cookies
                self._encrypt_to_cache('active', cookies_content)
            
            # Create secure temporary file
            temp_file_path = await self._create_secure_temp_file(cookies_content, 'active')
            
            logger.info(f"Active cookies prepared: {temp_file_path}")
            return temp_file_path
            
        except (CookieRateLimitError, CookieIntegrityError):
            # Don't retry for rate limit or integrity errors
            raise
        except Exception as e:
            logger.error(f"Failed to get active cookies: {e}")
            # Try backup cookies as fallback
            try:
                return await self.get_backup_cookies(identifier)
            except Exception as backup_error:
                logger.error(f"Backup cookies also failed: {backup_error}")
                raise CookieDownloadError(f"Both active and backup cookies failed: {e}")
    
    async def get_backup_cookies(self, identifier: str = "global") -> str:
        """
        Get backup cookies as temporary file path for yt-dlp.
        
        Args:
            identifier: Unique identifier for rate limiting (IP, session, etc.)
        
        Returns:
            str: Path to temporary cookie file
            
        Raises:
            CookieDownloadError: If backup cookie download fails
            CookieRateLimitError: If rate limit is exceeded
            CookieIntegrityError: If cookie integrity validation fails
        """
        try:
            # Check rate limit (using a separate limit for backup cookies)
            self._check_rate_limit(f"{identifier}_backup")
            
            # Check cache first
            if self._is_cache_valid('backup'):
                logger.debug("Using cached backup cookies")
                cookies_content = self._decrypt_from_cache('backup')
            else:
                # Download from S3
                logger.info("Downloading backup cookies from S3")
                cookies_content = await self._download_cookie_file(self.backup_cookie_key)
                
                # Validate cookie integrity
                self._validate_cookie_integrity(cookies_content, 'backup')
                
                # Cache encrypted cookies
                self._encrypt_to_cache('backup', cookies_content)
            
            # Create secure temporary file
            temp_file_path = await self._create_secure_temp_file(cookies_content, 'backup')
            
            logger.info(f"Backup cookies prepared: {temp_file_path}")
            return temp_file_path
            
        except Exception as e:
            logger.error(f"Failed to get backup cookies: {e}")
            raise CookieDownloadError(f"Backup cookie download failed: {e}")
    
    async def _download_cookie_file(self, s3_key: str) -> str:
        """
        Download cookie file from S3.
        
        Args:
            s3_key: S3 object key for cookie file
            
        Returns:
            str: Cookie file content
            
        Raises:
            CookieDownloadError: If download fails
        """
        try:
            loop = asyncio.get_event_loop()
            
            # Download file from S3 in thread pool
            def _download():
                response = self._s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                return response['Body'].read().decode('utf-8')
            
            cookies_content = await loop.run_in_executor(None, _download)
            
            # Log download success (without sensitive data)
            logger.info(f"Successfully downloaded cookie file: {s3_key}")
            
            return cookies_content
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                raise CookieDownloadError(f"Cookie file not found: {s3_key}")
            elif error_code == 'AccessDenied':
                raise CookieDownloadError(f"Access denied to cookie file: {s3_key}")
            else:
                raise CookieDownloadError(f"S3 error downloading {s3_key}: {error_code}")
        except Exception as e:
            raise CookieDownloadError(f"Failed to download cookie file {s3_key}: {e}")
    
    async def _validate_cookies(self, cookies_content: str) -> bool:
        """
        Validate cookie content and freshness.
        
        Args:
            cookies_content: Raw cookie file content
            
        Returns:
            bool: True if cookies are valid
            
        Raises:
            CookieValidationError: If cookies are invalid
            CookieExpiredError: If cookies have expired
        """
        try:
            # Parse cookies and check format
            cookie_lines = [line.strip() for line in cookies_content.split('\n') 
                          if line.strip() and not line.strip().startswith('#')]
            
            if not cookie_lines:
                raise CookieValidationError("Cookie file is empty or contains no valid cookies")
            
            # Check cookie format and expiration
            current_time = int(time.time())
            valid_cookies = 0
            expired_cookies = 0
            
            for line in cookie_lines:
                parts = line.split('\t')
                if len(parts) >= 5:
                    try:
                        expiration = int(parts[4])
                        if expiration == 0:  # Session cookie
                            valid_cookies += 1
                        elif expiration > current_time:
                            valid_cookies += 1
                        else:
                            expired_cookies += 1
                    except (ValueError, IndexError):
                        logger.warning(f"Invalid cookie line format: {line[:50]}...")
            
            if valid_cookies == 0:
                raise CookieExpiredError("All cookies have expired")
            
            if expired_cookies > valid_cookies:
                logger.warning(f"Most cookies expired: {expired_cookies} expired, {valid_cookies} valid")
            
            logger.info(f"Cookie validation successful: {valid_cookies} valid, {expired_cookies} expired")
            return True
            
        except (CookieValidationError, CookieExpiredError):
            raise
        except Exception as e:
            raise CookieValidationError(f"Cookie validation failed: {e}")
    
    async def validate_cookie_freshness(self) -> Dict[str, Any]:
        """
        Check cookie freshness and return status information.
        
        Returns:
            dict: Cookie freshness status and metadata
        """
        try:
            # Download metadata
            metadata = await self._download_metadata()
            
            current_time = datetime.now(timezone.utc)
            
            # Check active cookies
            active_status = self._check_cookie_freshness(
                metadata.get('active_cookies', {}), 
                current_time
            )
            
            # Check backup cookies
            backup_status = self._check_cookie_freshness(
                metadata.get('backup_cookies', {}), 
                current_time
            )
            
            return {
                'timestamp': current_time.isoformat(),
                'active_cookies': active_status,
                'backup_cookies': backup_status,
                'rotation_due': self._is_rotation_due(metadata, current_time),
                'warnings': self._get_freshness_warnings(active_status, backup_status)
            }
            
        except Exception as e:
            logger.error(f"Cookie freshness validation failed: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'status': 'validation_failed'
            }
    
    def _check_cookie_freshness(self, cookie_info: Dict[str, Any], current_time: datetime) -> Dict[str, Any]:
        """Check freshness status for a specific cookie set."""
        if not cookie_info:
            return {'status': 'missing', 'fresh': False}
        
        expires_at_str = cookie_info.get('expires_at')
        if not expires_at_str:
            return {'status': 'no_expiry', 'fresh': True}
        
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            days_until_expiry = (expires_at - current_time).days
            
            if days_until_expiry < 0:
                return {'status': 'expired', 'fresh': False, 'days_overdue': abs(days_until_expiry)}
            elif days_until_expiry <= 7:
                return {'status': 'expiring_soon', 'fresh': True, 'days_remaining': days_until_expiry}
            else:
                return {'status': 'fresh', 'fresh': True, 'days_remaining': days_until_expiry}
                
        except Exception as e:
            logger.error(f"Error parsing expiry date {expires_at_str}: {e}")
            return {'status': 'parse_error', 'fresh': False, 'error': str(e)}
    
    def _is_rotation_due(self, metadata: Dict[str, Any], current_time: datetime) -> bool:
        """Check if cookie rotation is due."""
        rotation_schedule = metadata.get('rotation_schedule', {})
        next_rotation_str = rotation_schedule.get('next_rotation_due')
        
        if not next_rotation_str:
            return False
        
        try:
            next_rotation = datetime.fromisoformat(next_rotation_str.replace('Z', '+00:00'))
            return current_time >= next_rotation
        except Exception:
            return False
    
    def _get_freshness_warnings(self, active_status: Dict[str, Any], backup_status: Dict[str, Any]) -> List[str]:
        """Generate warnings based on cookie freshness status."""
        warnings = []
        
        if not active_status.get('fresh'):
            warnings.append(f"Active cookies are not fresh: {active_status.get('status')}")
        
        if not backup_status.get('fresh'):
            warnings.append(f"Backup cookies are not fresh: {backup_status.get('status')}")
        
        if active_status.get('status') == 'expiring_soon':
            days = active_status.get('days_remaining', 0)
            warnings.append(f"Active cookies expire in {days} days")
        
        if backup_status.get('status') == 'expiring_soon':
            days = backup_status.get('days_remaining', 0)
            warnings.append(f"Backup cookies expire in {days} days")
        
        return warnings
    
    async def _download_metadata(self) -> Dict[str, Any]:
        """Download and parse cookie metadata from S3."""
        try:
            metadata_content = await self._download_cookie_file(self.metadata_key)
            return json.loads(metadata_content)
        except Exception as e:
            logger.error(f"Failed to download metadata: {e}")
            return {}
    
    async def _create_secure_temp_file(self, cookies_content: str, cookie_type: str) -> str:
        """
        Create secure temporary file for cookie content.
        
        Args:
            cookies_content: Raw cookie content
            cookie_type: Type of cookies (active/backup)
            
        Returns:
            str: Path to secure temporary file
        """
        # Create unique filename with timestamp
        timestamp = int(time.time())
        filename = f"youtube_cookies_{cookie_type}_{timestamp}.txt"
        temp_file_path = self.temp_dir / filename
        
        try:
            # Write cookies to temporary file with secure permissions
            async with aiofiles.open(temp_file_path, 'w', encoding='utf-8') as f:
                await f.write(cookies_content)
            
            # Set secure file permissions (owner read/write only)
            os.chmod(temp_file_path, 0o600)
            
            logger.debug(f"Created secure temporary cookie file: {temp_file_path}")
            return str(temp_file_path)
            
        except Exception as e:
            logger.error(f"Failed to create temporary cookie file: {e}")
            # Clean up on failure
            if temp_file_path.exists():
                temp_file_path.unlink()
            raise
    
    async def cleanup_temporary_files(self, max_age_hours: int = 1) -> int:
        """
        Clean up old temporary cookie files.
        
        Args:
            max_age_hours: Maximum age of temporary files to keep
            
        Returns:
            int: Number of files cleaned up
        """
        cleaned_count = 0
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        try:
            for temp_file in self.temp_dir.glob("youtube_cookies_*.txt"):
                try:
                    if temp_file.stat().st_mtime < cutoff_time:
                        # Securely delete file
                        self._secure_delete_file(temp_file)
                        cleaned_count += 1
                        logger.debug(f"Cleaned up old temporary file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} old temporary cookie files")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during temporary file cleanup: {e}")
            return cleaned_count
    
    def _secure_delete_file(self, file_path: Path) -> None:
        """Securely delete a file by overwriting and then removing."""
        try:
            if file_path.exists():
                # Overwrite file with random data
                file_size = file_path.stat().st_size
                with open(file_path, 'r+b') as f:
                    f.write(os.urandom(file_size))
                    f.flush()
                    os.fsync(f.fileno())
                
                # Remove the file
                file_path.unlink()
        except Exception as e:
            logger.warning(f"Secure file deletion failed for {file_path}: {e}")
            # Fallback to regular deletion
            try:
                file_path.unlink()
            except Exception:
                pass
    
    def _encrypt_to_cache(self, cache_key: str, content: str) -> None:
        """Encrypt and store content in memory cache."""
        encrypted_content = self._cipher_suite.encrypt(content.encode('utf-8'))
        self._encrypted_cache[cache_key] = encrypted_content
        self._cache_timestamps[cache_key] = time.time()
    
    def _decrypt_from_cache(self, cache_key: str) -> str:
        """Decrypt and return content from memory cache."""
        encrypted_content = self._encrypted_cache.get(cache_key)
        if encrypted_content:
            return self._cipher_suite.decrypt(encrypted_content).decode('utf-8')
        raise KeyError(f"Cache key not found: {cache_key}")
    
    def _check_rate_limit(self, identifier: str = "global") -> bool:
        """
        Check if rate limit has been exceeded for cookie access.
        
        Args:
            identifier: Unique identifier for rate limiting (IP, session, etc.)
            
        Returns:
            bool: True if within rate limit, False if exceeded
            
        Raises:
            CookieRateLimitError: If rate limit is exceeded
        """
        current_time = time.time()
        window_start = current_time - self.rate_limit_window
        
        # Clean old entries outside the time window
        request_times = self._rate_limit_tracker[identifier]
        while request_times and request_times[0] < window_start:
            request_times.popleft()
        
        # Check if we're within rate limit
        if len(request_times) >= self.rate_limit_requests:
            logger.warning(
                f"Rate limit exceeded for {identifier}: "
                f"{len(request_times)} requests in {self.rate_limit_window}s window"
            )
            raise CookieRateLimitError(
                f"Rate limit exceeded: {len(request_times)}/{self.rate_limit_requests} "
                f"requests per {self.rate_limit_window}s"
            )
        
        # Add current request
        request_times.append(current_time)
        return True
    
    def _validate_cookie_integrity(self, cookies_content: str, cookie_type: str) -> bool:
        """
        Validate cookie file integrity using hash verification.
        
        Args:
            cookies_content: Cookie file content to validate
            cookie_type: Type of cookie file (active/backup)
            
        Returns:
            bool: True if integrity is valid
            
        Raises:
            CookieIntegrityError: If integrity validation fails
        """
        if not self._integrity_checks_enabled:
            return True
        
        try:
            # Calculate current hash
            current_hash = hashlib.sha256(cookies_content.encode('utf-8')).hexdigest()
            stored_hash = self._cookie_hashes.get(cookie_type)
            
            if stored_hash is None:
                # First time seeing this cookie type, store the hash
                self._cookie_hashes[cookie_type] = current_hash
                logger.info(f"Stored initial integrity hash for {cookie_type} cookies")
                return True
            
            if current_hash != stored_hash:
                logger.error(
                    f"Cookie integrity validation failed for {cookie_type}: "
                    f"hash mismatch (expected: {stored_hash[:16]}..., "
                    f"got: {current_hash[:16]}...)"
                )
                raise CookieIntegrityError(
                    f"Cookie file integrity validation failed for {cookie_type} cookies"
                )
            
            logger.debug(f"Cookie integrity validated for {cookie_type} cookies")
            return True
            
        except CookieIntegrityError:
            raise
        except Exception as e:
            logger.error(f"Error during cookie integrity validation: {e}")
            # In case of validation errors, we may want to proceed with caution
            # but log the issue for investigation
            return True
    
    def update_cookie_integrity_hash(self, cookie_type: str, cookies_content: str) -> None:
        """
        Update the stored integrity hash for a cookie type.
        
        This should be called when cookies are intentionally updated/rotated.
        
        Args:
            cookie_type: Type of cookie file (active/backup)
            cookies_content: New cookie file content
        """
        new_hash = hashlib.sha256(cookies_content.encode('utf-8')).hexdigest()
        self._cookie_hashes[cookie_type] = new_hash
        logger.info(f"Updated integrity hash for {cookie_type} cookies")
    
    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status for monitoring.
        
        Returns:
            Dict[str, Any]: Rate limit status information
        """
        current_time = time.time()
        window_start = current_time - self.rate_limit_window
        
        status = {
            'rate_limit_window_seconds': self.rate_limit_window,
            'max_requests_per_window': self.rate_limit_requests,
            'active_identifiers': len(self._rate_limit_tracker),
            'identifiers': {}
        }
        
        for identifier, request_times in self._rate_limit_tracker.items():
            # Clean old entries
            while request_times and request_times[0] < window_start:
                request_times.popleft()
            
            status['identifiers'][identifier] = {
                'requests_in_window': len(request_times),
                'remaining_requests': max(0, self.rate_limit_requests - len(request_times)),
                'window_resets_in': max(0, int(request_times[0] + self.rate_limit_window - current_time)) if request_times else 0
            }
        
        return status
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached content is still valid."""
        if cache_key not in self._encrypted_cache:
            return False
        
        timestamp = self._cache_timestamps.get(cache_key, 0)
        return (time.time() - timestamp) < self.cache_ttl
    
    def clear_cache(self) -> None:
        """Clear all cached cookie data."""
        self._encrypted_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cookie cache cleared")
    
    async def get_cookie_metadata(self) -> Dict[str, Any]:
        """
        Get cookie metadata and status information.
        
        Returns:
            dict: Cookie metadata and status
        """
        try:
            metadata = await self._download_metadata()
            
            # Add runtime information
            runtime_info = {
                'cache_status': {
                    'active_cached': 'active' in self._encrypted_cache,
                    'backup_cached': 'backup' in self._encrypted_cache,
                    'cache_ttl_seconds': self.cache_ttl
                },
                'temp_directory': str(self.temp_dir),
                'temp_file_count': len(list(self.temp_dir.glob("youtube_cookies_*.txt")))
            }
            
            # Combine metadata with runtime info
            return {
                **metadata,
                'runtime_info': runtime_info,
                'manager_status': 'operational'
            }
            
        except Exception as e:
            logger.error(f"Failed to get cookie metadata: {e}")
            return {
                'error': str(e),
                'manager_status': 'error',
                'runtime_info': {
                    'temp_directory': str(self.temp_dir),
                    'temp_file_count': len(list(self.temp_dir.glob("youtube_cookies_*.txt"))) if self.temp_dir.exists() else 0
                }
            }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        # Clear sensitive data from memory
        self.clear_cache()
        
        # Schedule cleanup of temporary files
        try:
            asyncio.create_task(self.cleanup_temporary_files())
        except Exception as e:
            logger.warning(f"Failed to schedule temporary file cleanup: {e}")


# Global cookie manager instance
_cookie_manager_instance: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    """
    Get or create global cookie manager instance.
    
    Returns:
        CookieManager: Global cookie manager instance
    """
    global _cookie_manager_instance
    
    if _cookie_manager_instance is None:
        _cookie_manager_instance = CookieManager()
    
    return _cookie_manager_instance


def reset_cookie_manager() -> None:
    """Reset global cookie manager instance (useful for testing)."""
    global _cookie_manager_instance
    
    if _cookie_manager_instance:
        _cookie_manager_instance.clear_cache()
    
    _cookie_manager_instance = None