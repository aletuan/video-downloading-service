"""
Unit tests for error handling functionality.

This module tests error scenarios including network failures, S3 errors,
encryption errors, validation failures, and recovery mechanisms.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError, ConnectionError
from cryptography.fernet import InvalidToken
from pathlib import Path
import tempfile
import os

from app.core.cookie_manager import CookieManager


class TestErrorHandling:
    """Test suite for comprehensive error handling scenarios."""
    
    @pytest.fixture
    def cookie_manager(self, mock_cookie_settings):
        """Create cookie manager for error testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            return CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
    
    @pytest.fixture
    def sample_cookie_data(self):
        """Sample cookie data for testing."""
        return """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tabc123
.google.com\tTRUE\t/\tFALSE\t1735689600\tSESSION_TOKEN\tdef456
"""
    
    def test_s3_connection_errors(self, cookie_manager):
        """Test handling of S3 connection errors."""
        # Mock S3 client to raise connection error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ConnectionError("Connection failed")
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
            assert result is None
    
    def test_s3_access_denied_errors(self, cookie_manager):
        """Test handling of S3 access denied errors."""
        # Mock S3 client to raise access denied error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            operation_name='GetObject'
        )
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
            assert result is None
    
    def test_s3_no_such_key_errors(self, cookie_manager):
        """Test handling of S3 NoSuchKey errors."""
        # Mock S3 client to raise NoSuchKey error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchKey', 'Message': 'The specified key does not exist'}},
            operation_name='GetObject'
        )
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/nonexistent.txt')
            assert result is None
    
    def test_s3_no_such_bucket_errors(self, cookie_manager):
        """Test handling of S3 NoSuchBucket errors."""
        # Mock S3 client to raise NoSuchBucket error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'NoSuchBucket', 'Message': 'The specified bucket does not exist'}},
            operation_name='GetObject'
        )
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
            assert result is None
    
    def test_s3_throttling_errors(self, cookie_manager):
        """Test handling of S3 throttling errors."""
        # Mock S3 client to raise throttling error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'SlowDown', 'Message': 'Reduce your request rate'}},
            operation_name='GetObject'
        )
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
            assert result is None
    
    def test_s3_upload_errors(self, cookie_manager, sample_cookie_data):
        """Test handling of S3 upload errors."""
        # Mock S3 client to raise upload error
        mock_s3 = Mock()
        mock_s3.put_object.side_effect = ClientError(
            error_response={'Error': {'Code': 'InternalError', 'Message': 'We encountered an internal error'}},
            operation_name='PutObject'
        )
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            encrypted_data = cookie_manager._encrypt_cookie_data(sample_cookie_data)
            success = cookie_manager._upload_cookies_to_s3('cookies/test.txt', encrypted_data)
            assert success is False
    
    def test_encryption_key_errors(self):
        """Test handling of invalid encryption keys."""
        # Test with too short key
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name="test-bucket",
                    encryption_key="short"
                )
        
        # Test with None key
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name="test-bucket",
                    encryption_key=None
                )
        
        # Test with empty key
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name="test-bucket",
                    encryption_key=""
                )
    
    def test_decryption_invalid_token_errors(self, cookie_manager):
        """Test handling of decryption InvalidToken errors."""
        # Test with invalid encrypted data
        with pytest.raises(InvalidToken):
            cookie_manager._decrypt_cookie_data(b"invalid_token_data")
        
        # Test with corrupted data
        valid_data = "test data"
        encrypted = cookie_manager._encrypt_cookie_data(valid_data)
        corrupted = encrypted[:-5] + b"xxxxx"  # Corrupt the end
        
        with pytest.raises(InvalidToken):
            cookie_manager._decrypt_cookie_data(corrupted)
    
    def test_cookie_validation_errors(self, cookie_manager):
        """Test handling of cookie validation errors."""
        # Test invalid Netscape format
        invalid_netscape = "invalid\tline\twithout\tenough\tfields"
        result = cookie_manager._validate_cookies(invalid_netscape, "netscape")
        assert result['valid'] is False
        assert len(result['issues']) > 0
        
        # Test invalid JSON format
        invalid_json = "{'invalid': json syntax}"
        result = cookie_manager._validate_cookies(invalid_json, "json")
        assert result['valid'] is False
        assert len(result['issues']) > 0
        
        # Test unknown format
        unknown_data = "unknown format data"
        result = cookie_manager._validate_cookies(unknown_data, "unknown")
        assert result['valid'] is False
        assert len(result['issues']) > 0
    
    def test_cookie_expiration_edge_cases(self, cookie_manager):
        """Test cookie expiration validation edge cases."""
        # Test with invalid timestamp formats
        invalid_timestamps = [
            "invalid_timestamp",
            "-1",
            "999999999999999999999",  # Too large
            "not_a_number",
        ]
        
        for invalid_ts in invalid_timestamps:
            cookie_line = f".youtube.com\tTRUE\t/\tFALSE\t{invalid_ts}\tTEST\tvalue"
            result = cookie_manager._validate_cookies(cookie_line, "netscape")
            # Should not crash, may have warnings
            assert 'warnings' in result or 'issues' in result
    
    def test_temporary_file_creation_errors(self, cookie_manager, sample_cookie_data):
        """Test handling of temporary file creation errors."""
        # Mock tempfile to raise permission error
        with patch('tempfile.NamedTemporaryFile', side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError):
                cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        
        # Mock tempfile to raise OSError
        with patch('tempfile.NamedTemporaryFile', side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                cookie_manager._create_temporary_cookie_file(sample_cookie_data)
    
    def test_file_system_errors(self, cookie_manager, sample_cookie_data):
        """Test handling of file system errors."""
        # Create a temporary file that we can manipulate
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Make the file read-only to trigger write errors
            os.chmod(temp_path, 0o444)
            
            # Mock the temporary file creation to return our read-only file
            def mock_temp_file(*args, **kwargs):
                mock_file = Mock()
                mock_file.name = temp_path
                mock_file.write.side_effect = PermissionError("Permission denied")
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=None)
                return mock_file
            
            with patch('tempfile.NamedTemporaryFile', side_effect=mock_temp_file):
                with pytest.raises(PermissionError):
                    cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        
        finally:
            # Clean up
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)
    
    def test_network_timeout_errors(self, cookie_manager):
        """Test handling of network timeout errors."""
        # Mock S3 client to raise timeout error
        mock_s3 = Mock()
        mock_s3.get_object.side_effect = BotoCoreError("Read timeout")
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
            assert result is None
    
    def test_memory_errors(self, cookie_manager):
        """Test handling of memory errors with large data."""
        # Mock encryption to raise MemoryError
        with patch.object(cookie_manager, '_encrypt_cookie_data', side_effect=MemoryError("Out of memory")):
            with pytest.raises(MemoryError):
                cookie_manager._encrypt_cookie_data("test data")
    
    def test_concurrent_access_errors(self, cookie_manager, sample_cookie_data):
        """Test handling of concurrent access errors."""
        import threading
        import time
        
        errors = []
        
        def worker_with_errors():
            """Worker that may encounter errors during concurrent operations."""
            try:
                # Simulate various error conditions
                if threading.current_thread().name.endswith('0'):
                    # First thread: S3 error
                    mock_s3 = Mock()
                    mock_s3.get_object.side_effect = ClientError(
                        error_response={'Error': {'Code': 'ServiceUnavailable', 'Message': 'Service unavailable'}},
                        operation_name='GetObject'
                    )
                    with patch.object(cookie_manager, '_s3_client', mock_s3):
                        result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
                        if result is None:
                            errors.append("S3 error handled correctly")
                
                elif threading.current_thread().name.endswith('1'):
                    # Second thread: Encryption error
                    try:
                        cookie_manager._decrypt_cookie_data(b"invalid_data")
                    except InvalidToken:
                        errors.append("Encryption error handled correctly")
                
                else:
                    # Other threads: Normal operation
                    encrypted = cookie_manager._encrypt_cookie_data(sample_cookie_data)
                    decrypted = cookie_manager._decrypt_cookie_data(encrypted)
                    if decrypted == sample_cookie_data:
                        errors.append("Normal operation successful")
                        
            except Exception as e:
                errors.append(f"Unexpected error: {e}")
        
        # Create and start threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_with_errors, name=f"worker-{i}")
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify error handling
        assert len(errors) == 5  # All threads should complete
        assert any("S3 error handled correctly" in error for error in errors)
        assert any("Encryption error handled correctly" in error for error in errors)
        assert any("Normal operation successful" in error for error in errors)
    
    def test_configuration_errors(self):
        """Test handling of configuration errors."""
        # Test missing bucket name
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name=None,
                    encryption_key="test-key-1234567890123456789012345678"
                )
        
        # Test empty bucket name
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name="",
                    encryption_key="test-key-1234567890123456789012345678"
                )
        
        # Test invalid bucket name format
        with pytest.raises((ValueError, TypeError)):
            with patch('app.core.cookie_manager.boto3.client'):
                CookieManager(
                    bucket_name="Invalid..Bucket..Name",
                    encryption_key="test-key-1234567890123456789012345678"
                )
    
    def test_boto3_client_initialization_errors(self):
        """Test handling of boto3 client initialization errors."""
        # Mock boto3.client to raise credential error
        with patch('app.core.cookie_manager.boto3.client', side_effect=NoCredentialsError()):
            with pytest.raises(NoCredentialsError):
                CookieManager(
                    bucket_name="test-bucket",
                    encryption_key="test-key-1234567890123456789012345678"
                )
        
        # Mock boto3.client to raise other boto3 error
        with patch('app.core.cookie_manager.boto3.client', side_effect=BotoCoreError()):
            with pytest.raises(BotoCoreError):
                CookieManager(
                    bucket_name="test-bucket",
                    encryption_key="test-key-1234567890123456789012345678"
                )
    
    def test_malformed_cookie_data_handling(self, cookie_manager):
        """Test handling of various malformed cookie data."""
        malformed_data_sets = [
            # Binary data
            b'\x00\x01\x02\x03\x04\x05',
            # Extremely long lines
            "a" * 100000,
            # Mixed line endings
            "line1\r\nline2\nline3\r\n",
            # Non-UTF8 data (as string)
            "invalid\udcff\udcfe",
        ]
        
        for malformed_data in malformed_data_sets:
            try:
                if isinstance(malformed_data, bytes):
                    # Skip binary data for string-based operations
                    continue
                    
                result = cookie_manager._validate_cookies(malformed_data, "netscape")
                # Should not crash, may be invalid
                assert 'valid' in result
                
            except (UnicodeDecodeError, UnicodeError):
                # These errors are acceptable for malformed unicode data
                pass
            except Exception as e:
                pytest.fail(f"Unexpected exception for malformed data: {e}")
    
    def test_resource_cleanup_on_errors(self, cookie_manager, sample_cookie_data):
        """Test that resources are properly cleaned up when errors occur."""
        # Track file handles
        created_files = []
        
        def track_tempfile(*args, **kwargs):
            """Track created temporary files."""
            temp_file = tempfile.NamedTemporaryFile(*args, **kwargs)
            created_files.append(temp_file)
            return temp_file
        
        with patch('tempfile.NamedTemporaryFile', side_effect=track_tempfile):
            # Create temporary file and then simulate error
            try:
                temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
                
                # Simulate error during processing
                with patch.object(cookie_manager, '_validate_cookies', side_effect=Exception("Processing error")):
                    with pytest.raises(Exception):
                        # This should trigger cleanup
                        result = cookie_manager.get_active_cookies()
                
                # Verify file was cleaned up
                assert not os.path.exists(temp_path)
                
            except Exception:
                # Verify cleanup happened even with errors
                for temp_file in created_files:
                    if hasattr(temp_file, 'name'):
                        assert not os.path.exists(temp_file.name)
    
    def test_error_recovery_mechanisms(self, cookie_manager, sample_cookie_data):
        """Test error recovery and fallback mechanisms."""
        # Mock primary operation to fail, backup to succeed
        mock_s3 = Mock()
        
        # First call fails, second succeeds
        encrypted_data = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        mock_s3.get_object.side_effect = [
            ClientError(
                error_response={'Error': {'Code': 'ServiceUnavailable', 'Message': 'Service unavailable'}},
                operation_name='GetObject'
            ),
            {'Body': Mock(read=Mock(return_value=encrypted_data))}
        ]
        
        with patch.object(cookie_manager, '_s3_client', mock_s3):
            # First attempt should fail
            result1 = cookie_manager._download_cookies_from_s3('cookies/active.txt')
            assert result1 is None
            
            # Second attempt should succeed (simulating retry logic)
            result2 = cookie_manager._download_cookies_from_s3('cookies/backup.txt')
            assert result2 == encrypted_data
    
    @pytest.mark.parametrize("error_type,error_args", [
        (ConnectionError, ("Connection failed",)),
        (ClientError, ({'Error': {'Code': 'InternalError', 'Message': 'Internal error'}}, 'GetObject')),
        (BotoCoreError, ()),
        (InvalidToken, ()),
        (PermissionError, ("Permission denied",)),
        (OSError, ("Disk full",)),
    ])
    def test_parametrized_error_scenarios(self, cookie_manager, error_type, error_args):
        """Test various error scenarios with parametrized inputs."""
        # Mock appropriate method based on error type
        if error_type in [ConnectionError, ClientError, BotoCoreError]:
            # S3-related errors
            mock_s3 = Mock()
            mock_s3.get_object.side_effect = error_type(*error_args)
            
            with patch.object(cookie_manager, '_s3_client', mock_s3):
                result = cookie_manager._download_cookies_from_s3('cookies/test.txt')
                assert result is None
                
        elif error_type == InvalidToken:
            # Encryption-related errors
            with pytest.raises(InvalidToken):
                cookie_manager._decrypt_cookie_data(b"invalid_data")
                
        elif error_type in [PermissionError, OSError]:
            # File system errors
            with patch('tempfile.NamedTemporaryFile', side_effect=error_type(*error_args)):
                with pytest.raises(error_type):
                    cookie_manager._create_temporary_cookie_file("test data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])