"""
Unit tests for encryption and decryption functionality.

This module tests cryptographic operations including Fernet encryption,
key derivation, data integrity, and security edge cases.
"""

import pytest
import os
import secrets
from unittest.mock import patch, Mock
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

from app.core.cookie_manager import CookieManager


class TestEncryptionDecryption:
    """Test suite for encryption and decryption functionality."""
    
    @pytest.fixture
    def test_encryption_key(self):
        """Generate test encryption key."""
        return "test-key-1234567890123456789012345678"
    
    @pytest.fixture
    def sample_cookie_data(self):
        """Sample cookie data for encryption testing."""
        return """# Netscape HTTP Cookie File
# This contains sensitive authentication tokens
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tabc123def456
.google.com\tTRUE\t/\tFALSE\t1735689600\tSESSION_TOKEN\txyz789uvw012
.googleapis.com\tTRUE\t/\tFALSE\t1735689600\tAPI_KEY\tqwe345rty678
"""
    
    @pytest.fixture
    def cookie_manager(self, test_encryption_key, mock_cookie_settings):
        """Create cookie manager for encryption testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            return CookieManager(
                bucket_name="test-bucket",
                encryption_key=test_encryption_key
            )
    
    def test_key_derivation_consistency(self, cookie_manager, test_encryption_key):
        """Test that key derivation produces consistent results."""
        # Derive key multiple times
        key1 = cookie_manager._derive_key(test_encryption_key)
        key2 = cookie_manager._derive_key(test_encryption_key)
        key3 = cookie_manager._derive_key(test_encryption_key)
        
        # Keys should be identical for same input
        assert key1 == key2 == key3
        
        # Keys should be valid Fernet keys (32 bytes base64 encoded)
        assert len(base64.urlsafe_b64decode(key1)) == 32
        assert len(base64.urlsafe_b64decode(key2)) == 32
        assert len(base64.urlsafe_b64decode(key3)) == 32
    
    def test_key_derivation_with_different_inputs(self, cookie_manager):
        """Test key derivation with different input keys."""
        # Different input keys should produce different derived keys
        key1 = cookie_manager._derive_key("password1234567890123456789012345678")
        key2 = cookie_manager._derive_key("different123456789012345678901234567")
        key3 = cookie_manager._derive_key("another456789012345678901234567890")
        
        # All keys should be different
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3
        
        # All should be valid Fernet keys
        for key in [key1, key2, key3]:
            assert len(base64.urlsafe_b64decode(key)) == 32
            # Test that they can create valid Fernet instances
            cipher = Fernet(key)
            assert cipher is not None
    
    def test_encryption_decryption_roundtrip(self, cookie_manager, sample_cookie_data):
        """Test complete encryption-decryption roundtrip."""
        # Encrypt the data
        encrypted_data = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        
        # Verify encryption produces different data
        assert encrypted_data != sample_cookie_data.encode('utf-8')
        assert len(encrypted_data) > len(sample_cookie_data)
        
        # Decrypt the data
        decrypted_data = cookie_manager._decrypt_cookie_data(encrypted_data)
        
        # Verify decryption restores original data
        assert decrypted_data == sample_cookie_data
        assert isinstance(decrypted_data, str)
    
    def test_encryption_produces_different_outputs(self, cookie_manager, sample_cookie_data):
        """Test that encryption produces different outputs for same input."""
        # Encrypt same data multiple times
        encrypted1 = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        encrypted2 = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        encrypted3 = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        
        # Encrypted outputs should be different (due to random IV/nonce)
        assert encrypted1 != encrypted2
        assert encrypted2 != encrypted3
        assert encrypted1 != encrypted3
        
        # But all should decrypt to the same original data
        decrypted1 = cookie_manager._decrypt_cookie_data(encrypted1)
        decrypted2 = cookie_manager._decrypt_cookie_data(encrypted2)
        decrypted3 = cookie_manager._decrypt_cookie_data(encrypted3)
        
        assert decrypted1 == decrypted2 == decrypted3 == sample_cookie_data
    
    def test_encryption_with_empty_data(self, cookie_manager):
        """Test encryption and decryption with empty data."""
        # Test empty string
        empty_data = ""
        encrypted = cookie_manager._encrypt_cookie_data(empty_data)
        decrypted = cookie_manager._decrypt_cookie_data(encrypted)
        assert decrypted == empty_data
        
        # Test whitespace-only data
        whitespace_data = "   \n\t  "
        encrypted = cookie_manager._encrypt_cookie_data(whitespace_data)
        decrypted = cookie_manager._decrypt_cookie_data(encrypted)
        assert decrypted == whitespace_data
    
    def test_encryption_with_special_characters(self, cookie_manager):
        """Test encryption with special characters and unicode."""
        # Test data with special characters
        special_data = """# Cookies with special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?
.example.com\tTRUE\t/\tFALSE\t1735689600\tUNICODE\tvalue_with_ñ_and_emojis_🍪_and_symbols_©®™
.test.com\tTRUE\t/\tFALSE\t1735689600\tENTITIES\t&lt;&gt;&amp;&quot;&#39;
"""
        
        encrypted = cookie_manager._encrypt_cookie_data(special_data)
        decrypted = cookie_manager._decrypt_cookie_data(encrypted)
        assert decrypted == special_data
    
    def test_encryption_with_large_data(self, cookie_manager):
        """Test encryption with large data sets."""
        # Generate large cookie data (1MB+)
        large_data = "# Large cookie file\n"
        for i in range(10000):
            large_data += f".domain{i}.com\tTRUE\t/\tFALSE\t1735689600\tCOOKIE{i}\t{'x' * 100}\n"
        
        # Encrypt and decrypt large data
        encrypted = cookie_manager._encrypt_cookie_data(large_data)
        decrypted = cookie_manager._decrypt_cookie_data(encrypted)
        
        assert decrypted == large_data
        assert len(encrypted) > len(large_data.encode('utf-8'))  # Encryption overhead
    
    def test_decryption_with_invalid_data(self, cookie_manager):
        """Test decryption error handling with invalid data."""
        # Test with completely invalid data
        with pytest.raises(InvalidToken):
            cookie_manager._decrypt_cookie_data(b"invalid encrypted data")
        
        # Test with corrupted encrypted data
        valid_encrypted = cookie_manager._encrypt_cookie_data("test data")
        corrupted_data = valid_encrypted[:-10] + b"corrupted"
        
        with pytest.raises(InvalidToken):
            cookie_manager._decrypt_cookie_data(corrupted_data)
        
        # Test with empty bytes
        with pytest.raises((InvalidToken, ValueError)):
            cookie_manager._decrypt_cookie_data(b"")
    
    def test_decryption_with_wrong_key(self, sample_cookie_data):
        """Test decryption fails with wrong key."""
        # Create two cookie managers with different keys
        with patch('app.core.cookie_manager.boto3.client'):
            manager1 = CookieManager(
                bucket_name="test-bucket",
                encryption_key="key1-1234567890123456789012345678"
            )
            manager2 = CookieManager(
                bucket_name="test-bucket",
                encryption_key="key2-9876543210987654321098765432"
            )
        
        # Encrypt with first manager
        encrypted_data = manager1._encrypt_cookie_data(sample_cookie_data)
        
        # Try to decrypt with second manager (wrong key)
        with pytest.raises(InvalidToken):
            manager2._decrypt_cookie_data(encrypted_data)
        
        # Verify first manager can still decrypt correctly
        decrypted = manager1._decrypt_cookie_data(encrypted_data)
        assert decrypted == sample_cookie_data
    
    def test_key_security_properties(self, cookie_manager):
        """Test security properties of derived keys."""
        key = cookie_manager._derive_key("test-password-1234567890123456789012")
        
        # Key should be base64 encoded
        decoded_key = base64.urlsafe_b64decode(key)
        assert len(decoded_key) == 32  # 256 bits
        
        # Key should have good entropy (not all same bytes)
        unique_bytes = set(decoded_key)
        assert len(unique_bytes) > 10  # Should have reasonable diversity
        
        # Key should be deterministic for same input
        key2 = cookie_manager._derive_key("test-password-1234567890123456789012")
        assert key == key2
    
    def test_pbkdf2_parameters(self, cookie_manager):
        """Test PBKDF2 key derivation parameters."""
        # Access the internal salt and iterations (if exposed for testing)
        password = "test-password-1234567890123456789012"
        
        # Test that salt is consistent (hardcoded for reproducibility)
        key1 = cookie_manager._derive_key(password)
        key2 = cookie_manager._derive_key(password)
        assert key1 == key2
        
        # Test key derivation with different passwords produces different results
        different_key = cookie_manager._derive_key("different-password-567890123456789")
        assert key1 != different_key
    
    def test_encryption_performance_benchmarks(self, cookie_manager, sample_cookie_data):
        """Test encryption/decryption performance."""
        import time
        
        # Benchmark encryption
        encryption_times = []
        for _ in range(100):
            start = time.time()
            encrypted = cookie_manager._encrypt_cookie_data(sample_cookie_data)
            encryption_times.append(time.time() - start)
        
        # Benchmark decryption
        encrypted_sample = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        decryption_times = []
        for _ in range(100):
            start = time.time()
            decrypted = cookie_manager._decrypt_cookie_data(encrypted_sample)
            decryption_times.append(time.time() - start)
        
        # Performance assertions (generous limits)
        avg_encryption_time = sum(encryption_times) / len(encryption_times)
        avg_decryption_time = sum(decryption_times) / len(decryption_times)
        
        assert avg_encryption_time < 0.1  # Less than 100ms average
        assert avg_decryption_time < 0.1  # Less than 100ms average
        
        # Verify decryption correctness in benchmark
        assert decrypted == sample_cookie_data
    
    def test_encryption_memory_safety(self, cookie_manager, sample_cookie_data):
        """Test encryption operations don't leak sensitive data."""
        # Encrypt data
        encrypted = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        
        # Verify original data is not contained in encrypted output
        assert sample_cookie_data.encode('utf-8') not in encrypted
        assert b"VISITOR_INFO1_LIVE" not in encrypted
        assert b"SESSION_TOKEN" not in encrypted
        assert b"API_KEY" not in encrypted
        
        # Test multiple encryptions don't reveal patterns
        encryptions = []
        for _ in range(10):
            encryptions.append(cookie_manager._encrypt_cookie_data(sample_cookie_data))
        
        # No two encryptions should be identical
        for i in range(len(encryptions)):
            for j in range(i + 1, len(encryptions)):
                assert encryptions[i] != encryptions[j]
    
    def test_concurrent_encryption_operations(self, cookie_manager, sample_cookie_data):
        """Test concurrent encryption/decryption operations."""
        import threading
        import time
        
        results = {'successes': 0, 'failures': 0}
        results_lock = threading.Lock()
        
        def encrypt_decrypt_worker():
            """Worker function for concurrent operations."""
            try:
                # Perform encryption/decryption cycle
                encrypted = cookie_manager._encrypt_cookie_data(sample_cookie_data)
                decrypted = cookie_manager._decrypt_cookie_data(encrypted)
                
                # Verify correctness
                assert decrypted == sample_cookie_data
                
                with results_lock:
                    results['successes'] += 1
                    
            except Exception:
                with results_lock:
                    results['failures'] += 1
        
        # Create and start threads
        threads = []
        num_threads = 10
        
        for _ in range(num_threads):
            thread = threading.Thread(target=encrypt_decrypt_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify all operations succeeded
        assert results['successes'] == num_threads
        assert results['failures'] == 0
    
    def test_encryption_with_binary_data(self, cookie_manager):
        """Test encryption with binary data patterns."""
        # Test with various binary patterns
        binary_patterns = [
            b'\x00' * 100,  # Null bytes
            b'\xFF' * 100,  # Max bytes
            b'\x00\xFF' * 50,  # Alternating pattern
            bytes(range(256)),  # Full byte range
            os.urandom(1000),  # Random data
        ]
        
        for binary_data in binary_patterns:
            # Convert to string for encryption (cookie manager expects strings)
            data_str = base64.b64encode(binary_data).decode('utf-8')
            
            encrypted = cookie_manager._encrypt_cookie_data(data_str)
            decrypted = cookie_manager._decrypt_cookie_data(encrypted)
            
            assert decrypted == data_str
            
            # Verify round-trip with binary data
            recovered_binary = base64.b64decode(decrypted)
            assert recovered_binary == binary_data
    
    @pytest.mark.parametrize("key_length", [32, 48, 64, 128])
    def test_key_derivation_with_various_lengths(self, key_length):
        """Test key derivation with various input key lengths."""
        # Generate test key of specified length
        test_key = 'x' * key_length
        
        with patch('app.core.cookie_manager.boto3.client'):
            cookie_manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key=test_key
            )
        
        # Derive key and test encryption
        derived_key = cookie_manager._derive_key(test_key)
        assert len(base64.urlsafe_b64decode(derived_key)) == 32
        
        # Test that encryption works regardless of input key length
        test_data = "Test data for encryption"
        encrypted = cookie_manager._encrypt_cookie_data(test_data)
        decrypted = cookie_manager._decrypt_cookie_data(encrypted)
        assert decrypted == test_data
    
    def test_fernet_token_format_validation(self, cookie_manager, sample_cookie_data):
        """Test that encrypted tokens follow Fernet format specifications."""
        encrypted = cookie_manager._encrypt_cookie_data(sample_cookie_data)
        
        # Fernet tokens should be base64 URL-safe encoded
        try:
            decoded_token = base64.urlsafe_b64decode(encrypted)
        except Exception:
            pytest.fail("Encrypted token is not valid base64 URL-safe encoded")
        
        # Fernet token structure: version(1) + timestamp(8) + iv(16) + ciphertext(variable) + hmac(32)
        # Minimum length should be 57 bytes (1+8+16+0+32)
        assert len(decoded_token) >= 57
        
        # First byte should be version (0x80 for current Fernet)
        assert decoded_token[0] == 0x80
    
    def test_encryption_deterministic_for_testing(self, cookie_manager):
        """Test encryption behavior for testing scenarios."""
        # While encryption should normally be non-deterministic,
        # test that our manager produces valid encryptions consistently
        test_data = "Deterministic test data"
        
        encryptions = []
        for _ in range(5):
            encrypted = cookie_manager._encrypt_cookie_data(test_data)
            encryptions.append(encrypted)
            
            # Each should decrypt correctly
            decrypted = cookie_manager._decrypt_cookie_data(encrypted)
            assert decrypted == test_data
        
        # All encryptions should be valid but different
        for i in range(len(encryptions)):
            for j in range(i + 1, len(encryptions)):
                assert encryptions[i] != encryptions[j]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])