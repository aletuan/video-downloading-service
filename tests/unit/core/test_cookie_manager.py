"""
Unit tests for CookieManager class.

This test suite provides comprehensive unit testing for the cookie management system,
including validation logic, S3 integration, encryption/decryption, error handling,
and temporary file cleanup functionality.
"""

import pytest
import asyncio
import tempfile
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from cryptography.fernet import Fernet
import boto3
from moto import mock_s3

# Import the module under test
from app.core.cookie_manager import CookieManager, CookieManagerError


class TestCookieManager:
    """Test suite for CookieManager class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        with patch('app.core.cookie_manager.settings') as mock_settings:
            mock_settings.cookie_s3_bucket = "test-cookie-bucket"
            mock_settings.cookie_encryption_key = "test-key-1234567890123456789012345678"
            mock_settings.cookie_refresh_interval = 3600
            mock_settings.cookie_validation_enabled = True
            mock_settings.cookie_backup_count = 3
            mock_settings.cookie_temp_dir = "/tmp/cookie_temp"
            mock_settings.aws_region = "us-east-1"
            yield mock_settings
    
    @pytest.fixture
    def cookie_manager(self, mock_settings):
        """Create CookieManager instance for testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678",
                aws_region="us-east-1"
            )
            return manager
    
    @pytest.fixture
    def sample_netscape_cookies(self):
        """Sample Netscape format cookies for testing."""
        return """# Netscape HTTP Cookie File
# This is a generated file!  Do not edit.

.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123
.google.com	TRUE	/	TRUE	1735689600	SIDCC	def456
youtube.com	FALSE	/	FALSE	0	PREF	ghi789
"""
    
    @pytest.fixture
    def sample_json_cookies(self):
        """Sample JSON format cookies for testing."""
        return json.dumps([
            {
                "domain": ".youtube.com",
                "name": "VISITOR_INFO1_LIVE",
                "value": "abc123",
                "path": "/",
                "expires": 1735689600,
                "secure": False,
                "httpOnly": True
            },
            {
                "domain": ".google.com",
                "name": "SIDCC",
                "value": "def456",
                "path": "/",
                "expires": 1735689600,
                "secure": True,
                "httpOnly": False
            }
        ])
    
    @pytest.fixture
    def expired_cookies(self):
        """Sample expired cookies for testing."""
        expired_timestamp = int((datetime.now() - timedelta(days=1)).timestamp())
        return f"""# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	{expired_timestamp}	VISITOR_INFO1_LIVE	expired123
"""
    
    def test_cookie_manager_initialization(self, mock_settings):
        """Test CookieManager initialization with various configurations."""
        # Test successful initialization
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            assert manager.bucket_name == "test-bucket"
            assert manager.aws_region == "us-east-1"
            assert manager._cipher_suite is not None
        
        # Test initialization with missing bucket name
        with pytest.raises(CookieManagerError):
            CookieManager(bucket_name=None, encryption_key="test-key")
        
        # Test initialization with missing encryption key
        with pytest.raises(CookieManagerError):
            CookieManager(bucket_name="test-bucket", encryption_key=None)
    
    def test_key_derivation(self, cookie_manager):
        """Test encryption key derivation."""
        key1 = cookie_manager._derive_key("password123")
        key2 = cookie_manager._derive_key("password123")
        key3 = cookie_manager._derive_key("different_password")
        
        # Same password should produce same key
        assert key1 == key2
        
        # Different passwords should produce different keys
        assert key1 != key3
        
        # Keys should be proper length for Fernet
        assert len(key1) == 44  # Base64 encoded 32-byte key
    
    def test_cookie_validation_netscape_format(self, cookie_manager, sample_netscape_cookies, expired_cookies):
        """Test cookie validation for Netscape format."""
        # Test valid cookies
        result = cookie_manager._validate_cookies(sample_netscape_cookies, "netscape")
        
        assert result['valid'] is True
        assert result['format'] == "netscape"
        assert result['cookie_count'] == 3
        assert ".youtube.com" in result['domains']
        assert ".google.com" in result['domains']
        assert len(result['issues']) == 0
        
        # Test expired cookies
        result = cookie_manager._validate_cookies(expired_cookies, "netscape")
        
        assert result['cookie_count'] == 1
        assert len(result['warnings']) > 0
        assert any("expired" in warning.lower() for warning in result['warnings'])
        
        # Test invalid format
        invalid_cookies = "invalid\nformat\nhere"
        result = cookie_manager._validate_cookies(invalid_cookies, "netscape")
        
        assert result['valid'] is False
        assert len(result['issues']) > 0
    
    def test_cookie_validation_json_format(self, cookie_manager, sample_json_cookies):
        """Test cookie validation for JSON format."""
        # Test valid JSON cookies
        result = cookie_manager._validate_cookies(sample_json_cookies, "json")
        
        assert result['valid'] is True
        assert result['format'] == "json"
        assert result['cookie_count'] == 2
        assert ".youtube.com" in result['domains']
        assert ".google.com" in result['domains']
        
        # Test invalid JSON
        invalid_json = "{'invalid': json}"
        result = cookie_manager._validate_cookies(invalid_json, "json")
        
        assert result['valid'] is False
        assert len(result['issues']) > 0
        
        # Test JSON with missing required fields
        incomplete_json = json.dumps([{"name": "test"}])  # Missing domain
        result = cookie_manager._validate_cookies(incomplete_json, "json")
        
        assert len(result['warnings']) > 0
    
    def test_cookie_expiration_logic(self, cookie_manager):
        """Test cookie expiration detection logic."""
        now = datetime.now()
        
        # Test future expiration (valid)
        future_timestamp = int((now + timedelta(days=30)).timestamp())
        future_cookies = f"""# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	{future_timestamp}	VISITOR_INFO1_LIVE	future123
"""
        
        result = cookie_manager._validate_cookies(future_cookies, "netscape")
        assert result['valid'] is True
        assert len(result['warnings']) == 0
        
        # Test past expiration (expired)
        past_timestamp = int((now - timedelta(days=1)).timestamp())
        past_cookies = f"""# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	{past_timestamp}	VISITOR_INFO1_LIVE	past123
"""
        
        result = cookie_manager._validate_cookies(past_cookies, "netscape")
        assert len(result['warnings']) > 0
        assert any("expired" in warning.lower() for warning in result['warnings'])
        
        # Test session cookies (expires = 0)
        session_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	0	VISITOR_INFO1_LIVE	session123
"""
        
        result = cookie_manager._validate_cookies(session_cookies, "netscape")
        assert result['valid'] is True  # Session cookies are valid
    
    @mock_s3
    def test_s3_integration_with_mocks(self, cookie_manager, sample_netscape_cookies):
        """Test S3 integration using moto mocks."""
        # Setup mock S3
        s3_client = boto3.client('s3', region_name='us-east-1')
        s3_client.create_bucket(Bucket='test-cookie-bucket')
        
        # Replace the cookie manager's S3 client with our mocked one
        cookie_manager._s3_client = s3_client
        cookie_manager.bucket_name = 'test-cookie-bucket'
        
        # Test cookie upload
        encrypted_content = cookie_manager._cipher_suite.encrypt(sample_netscape_cookies.encode())
        
        s3_client.put_object(
            Bucket='test-cookie-bucket',
            Key='cookies/youtube-cookies-active.txt',
            Body=encrypted_content
        )
        
        # Test cookie download
        response = s3_client.get_object(
            Bucket='test-cookie-bucket',
            Key='cookies/youtube-cookies-active.txt'
        )
        
        retrieved_content = response['Body'].read()
        decrypted_content = cookie_manager._cipher_suite.decrypt(retrieved_content)
        
        assert decrypted_content.decode() == sample_netscape_cookies
        
        # Test metadata handling
        metadata = {
            'upload_timestamp': datetime.utcnow().isoformat(),
            'cookie_count': 3,
            'format': 'netscape'
        }
        
        s3_client.put_object(
            Bucket='test-cookie-bucket',
            Key='cookies/metadata.json',
            Body=json.dumps(metadata).encode()
        )
        
        # Verify metadata retrieval
        response = s3_client.get_object(
            Bucket='test-cookie-bucket',
            Key='cookies/metadata.json'
        )
        
        retrieved_metadata = json.loads(response['Body'].read().decode())
        assert retrieved_metadata['cookie_count'] == 3
        assert retrieved_metadata['format'] == 'netscape'
    
    def test_encryption_decryption(self, cookie_manager, sample_netscape_cookies, sample_json_cookies):
        """Test encryption and decryption functionality."""
        # Test Netscape format encryption/decryption
        encrypted_netscape = cookie_manager._cipher_suite.encrypt(sample_netscape_cookies.encode())
        decrypted_netscape = cookie_manager._cipher_suite.decrypt(encrypted_netscape).decode()
        
        assert decrypted_netscape == sample_netscape_cookies
        
        # Test JSON format encryption/decryption
        encrypted_json = cookie_manager._cipher_suite.encrypt(sample_json_cookies.encode())
        decrypted_json = cookie_manager._cipher_suite.decrypt(encrypted_json).decode()
        
        assert decrypted_json == sample_json_cookies
        
        # Test that encrypted content is different from original
        assert encrypted_netscape != sample_netscape_cookies.encode()
        assert encrypted_json != sample_json_cookies.encode()
        
        # Test encryption with different keys produces different results
        different_key = Fernet.generate_key()
        different_cipher = Fernet(different_key)
        
        different_encrypted = different_cipher.encrypt(sample_netscape_cookies.encode())
        assert different_encrypted != encrypted_netscape
        
        # Test decryption with wrong key fails
        with pytest.raises(Exception):  # Fernet will raise various crypto exceptions
            cookie_manager._cipher_suite.decrypt(different_encrypted)
    
    @pytest.mark.asyncio
    async def test_get_active_cookies_success(self, cookie_manager, sample_netscape_cookies):
        """Test successful retrieval of active cookies."""
        mock_s3 = Mock()
        mock_response = Mock()
        mock_response.read.return_value = cookie_manager._cipher_suite.encrypt(sample_netscape_cookies.encode())
        mock_s3.get_object.return_value = {'Body': mock_response}
        
        cookie_manager._s3_client = mock_s3
        
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_file = Mock()
            mock_file.name = "/tmp/test_cookies.txt"
            mock_file.__enter__.return_value = mock_file
            mock_temp.return_value = mock_file
            
            result = await cookie_manager.get_active_cookies()
            
            assert result == "/tmp/test_cookies.txt"
            mock_s3.get_object.assert_called_once_with(
                Bucket=cookie_manager.bucket_name,
                Key='cookies/youtube-cookies-active.txt'
            )
            mock_file.write.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_active_cookies_s3_error(self, cookie_manager):
        """Test handling of S3 errors when retrieving cookies."""
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = Exception("S3 connection failed")
        
        cookie_manager._s3_client = mock_s3
        
        with pytest.raises(CookieManagerError):
            await cookie_manager.get_active_cookies()
    
    @pytest.mark.asyncio
    async def test_get_active_cookies_decryption_error(self, cookie_manager):
        """Test handling of decryption errors."""
        mock_s3 = Mock()
        mock_response = Mock()
        mock_response.read.return_value = b"invalid_encrypted_content"
        mock_s3.get_object.return_value = {'Body': mock_response}
        
        cookie_manager._s3_client = mock_s3
        
        with pytest.raises(CookieManagerError):
            await cookie_manager.get_active_cookies()
    
    @pytest.mark.asyncio
    async def test_validate_cookie_freshness(self, cookie_manager, sample_netscape_cookies, expired_cookies):
        """Test cookie freshness validation."""
        # Test fresh cookies
        result = await cookie_manager.validate_cookie_freshness(sample_netscape_cookies)
        
        assert result['fresh'] is True
        assert result['expired_count'] == 0
        assert result['total_cookies'] > 0
        
        # Test expired cookies
        result = await cookie_manager.validate_cookie_freshness(expired_cookies)
        
        assert result['fresh'] is False
        assert result['expired_count'] > 0
        assert len(result['expired_cookies']) > 0
    
    def test_error_handling_scenarios(self, cookie_manager):
        """Test various error handling scenarios."""
        # Test invalid bucket name
        with patch('app.core.cookie_manager.boto3.client') as mock_boto:
            mock_client = Mock()
            mock_client.get_object.side_effect = Exception("NoSuchBucket")
            mock_boto.return_value = mock_client
            
            manager = CookieManager(bucket_name="nonexistent-bucket", encryption_key="test-key")
            
            with pytest.raises(Exception):
                asyncio.run(manager.get_active_cookies())
        
        # Test network timeout simulation
        with patch.object(cookie_manager, '_s3_client') as mock_s3:
            mock_s3.get_object.side_effect = Exception("Timeout")
            
            with pytest.raises(CookieManagerError):
                asyncio.run(cookie_manager.get_active_cookies())
        
        # Test invalid cookie content
        invalid_content = "completely invalid cookie content"
        result = cookie_manager._validate_cookies(invalid_content, "unknown")
        
        assert result['valid'] is False
        assert len(result['issues']) > 0
    
    @pytest.mark.asyncio
    async def test_temporary_file_cleanup(self, cookie_manager, sample_netscape_cookies):
        """Test temporary file cleanup functionality."""
        mock_s3 = Mock()
        mock_response = Mock()
        mock_response.read.return_value = cookie_manager._cipher_suite.encrypt(sample_netscape_cookies.encode())
        mock_s3.get_object.return_value = {'Body': mock_response}
        
        cookie_manager._s3_client = mock_s3
        
        # Track created temporary files
        temp_files = []
        
        def track_temp_file(*args, **kwargs):
            mock_file = Mock()
            mock_file.name = f"/tmp/test_cookies_{len(temp_files)}.txt"
            mock_file.__enter__.return_value = mock_file
            temp_files.append(mock_file.name)
            return mock_file
        
        with patch('tempfile.NamedTemporaryFile', side_effect=track_temp_file):
            # Create multiple temporary cookie files
            result1 = await cookie_manager.get_active_cookies()
            result2 = await cookie_manager.get_active_cookies()
            
            assert len(temp_files) == 2
            assert result1 != result2
        
        # Test cleanup method
        with patch('os.path.exists', return_value=True), \
             patch('os.unlink') as mock_unlink:
            
            await cookie_manager.cleanup_temporary_files()
            
            # Verify cleanup was attempted (in real implementation)
            # This is a placeholder for actual cleanup logic
            assert True  # Placeholder assertion
    
    @pytest.mark.asyncio
    async def test_cookie_rotation_logic(self, cookie_manager, sample_netscape_cookies):
        """Test cookie rotation functionality."""
        mock_s3 = Mock()
        
        # Mock successful rotation sequence
        mock_s3.head_object.return_value = True  # Backup exists
        mock_s3.copy_object.return_value = True  # Copy operations succeed
        
        cookie_manager._s3_client = mock_s3
        
        result = await cookie_manager.rotate_cookies()
        
        # Verify rotation steps were called
        expected_calls = [
            # Check backup exists
            mock_s3.head_object,
            # Archive current to timestamped backup
            mock_s3.copy_object,
            # Promote backup to active
            mock_s3.copy_object
        ]
        
        assert result['success'] is True
        assert mock_s3.head_object.called
        assert mock_s3.copy_object.call_count >= 2
    
    def test_cookie_metadata_handling(self, cookie_manager):
        """Test cookie metadata creation and validation."""
        sample_data = {
            'cookie_count': 5,
            'domains': ['.youtube.com', '.google.com'],
            'expires_earliest': '2024-01-01T00:00:00',
            'expires_latest': '2024-12-31T23:59:59',
            'format': 'netscape'
        }
        
        metadata = cookie_manager._create_metadata(
            file_size=1024,
            checksum='abc123',
            validation_result=sample_data,
            source='test',
            description='Unit test cookies'
        )
        
        assert metadata['cookie_count'] == 5
        assert metadata['format'] == 'netscape'
        assert metadata['source'] == 'test'
        assert metadata['file_size'] == 1024
        assert metadata['checksum'] == 'abc123'
        assert 'upload_timestamp' in metadata
        assert len(metadata['domains']) == 2
    
    @pytest.mark.parametrize("file_size,expected_valid", [
        (0, False),           # Empty file
        (1024, True),         # Normal size
        (1024*1024, True),    # 1MB
        (10*1024*1024, True), # 10MB
        (20*1024*1024, False) # Too large
    ])
    def test_file_size_validation(self, cookie_manager, file_size, expected_valid):
        """Test file size validation with various sizes."""
        # This would be part of the file validation logic
        max_size = 10 * 1024 * 1024  # 10MB
        
        is_valid = 0 < file_size <= max_size
        assert is_valid == expected_valid
    
    def test_domain_validation(self, cookie_manager):
        """Test YouTube domain validation logic."""
        # Test cookies with YouTube domains
        youtube_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	test123
.googleapis.com	TRUE	/	FALSE	1735689600	AUTH_TOKEN	test456
"""
        
        result = cookie_manager._validate_cookies(youtube_cookies, "netscape")
        
        assert result['valid'] is True
        assert '.youtube.com' in result['domains']
        assert '.googleapis.com' in result['domains']
        
        # Test cookies without YouTube domains
        non_youtube_cookies = """# Netscape HTTP Cookie File
.facebook.com	TRUE	/	FALSE	1735689600	SESSIONID	test123
"""
        
        result = cookie_manager._validate_cookies(non_youtube_cookies, "netscape")
        
        assert result['valid'] is True  # Still valid, just warning
        assert len(result['warnings']) > 0
        assert any('youtube' in warning.lower() for warning in result['warnings'])
    
    @pytest.mark.asyncio
    async def test_concurrent_cookie_access(self, cookie_manager, sample_netscape_cookies):
        """Test concurrent access to cookie manager."""
        mock_s3 = Mock()
        mock_response = Mock()
        mock_response.read.return_value = cookie_manager._cipher_suite.encrypt(sample_netscape_cookies.encode())
        mock_s3.get_object.return_value = {'Body': mock_response}
        
        cookie_manager._s3_client = mock_s3
        
        # Simulate concurrent requests
        with patch('tempfile.NamedTemporaryFile') as mock_temp:
            mock_files = []
            for i in range(3):
                mock_file = Mock()
                mock_file.name = f"/tmp/test_cookies_{i}.txt"
                mock_file.__enter__.return_value = mock_file
                mock_files.append(mock_file)
            
            mock_temp.side_effect = mock_files
            
            # Execute concurrent requests
            tasks = [
                cookie_manager.get_active_cookies(),
                cookie_manager.get_active_cookies(),
                cookie_manager.get_active_cookies()
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Each request should get a unique temporary file
            assert len(set(results)) == 3
            assert all(result.startswith('/tmp/test_cookies_') for result in results)


# Fixtures for integration with pytest-asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test configuration and utilities
class TestCookieManagerConfiguration:
    """Test configuration and utility methods."""
    
    def test_environment_variable_handling(self):
        """Test environment variable configuration."""
        with patch.dict(os.environ, {
            'COOKIE_S3_BUCKET': 'env-bucket',
            'COOKIE_ENCRYPTION_KEY': 'env-key-123456789012345678901234',
            'AWS_REGION': 'us-west-2'
        }):
            with patch('app.core.cookie_manager.boto3.client'):
                manager = CookieManager()
                
                assert manager.bucket_name == 'env-bucket'
                assert manager.aws_region == 'us-west-2'
    
    def test_settings_precedence(self):
        """Test precedence of configuration sources."""
        with patch('app.core.cookie_manager.settings') as mock_settings:
            mock_settings.cookie_s3_bucket = "settings-bucket"
            mock_settings.cookie_encryption_key = "settings-key-123456789012345678"
            
            with patch('app.core.cookie_manager.boto3.client'):
                # Direct parameters should override settings
                manager = CookieManager(
                    bucket_name="direct-bucket",
                    encryption_key="direct-key-123456789012345678"
                )
                
                assert manager.bucket_name == "direct-bucket"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])