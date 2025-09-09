"""
Unit tests for cookie validation logic.

This module tests cookie validation functionality including format detection,
expiration checking, domain validation, and various edge cases.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, Mock

from app.core.cookie_manager import CookieManager


class TestCookieValidation:
    """Test suite for cookie validation functionality."""
    
    @pytest.fixture
    def validator(self, mock_cookie_settings):
        """Create cookie manager for validation testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            return CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
    
    def test_netscape_format_detection(self, validator):
        """Test detection of Netscape HTTP Cookie File format."""
        # Valid Netscape format
        netscape_content = """# Netscape HTTP Cookie File
# This is a generated file!  Do not edit.

.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123
"""
        format_type = validator._detect_cookie_format(netscape_content)
        assert format_type == "netscape"
        
        # Netscape without header comment
        netscape_no_header = ".youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123"
        format_type = validator._detect_cookie_format(netscape_no_header)
        assert format_type == "netscape"
    
    def test_json_format_detection(self, validator):
        """Test detection of JSON cookie format."""
        # Valid JSON array
        json_content = json.dumps([
            {"domain": ".youtube.com", "name": "test", "value": "123"}
        ])
        format_type = validator._detect_cookie_format(json_content)
        assert format_type == "json"
        
        # Valid JSON object
        json_object = json.dumps({"domain": ".youtube.com", "name": "test", "value": "123"})
        format_type = validator._detect_cookie_format(json_object)
        assert format_type == "json"
    
    def test_unknown_format_detection(self, validator):
        """Test detection of unknown/invalid formats."""
        # Plain text
        unknown_content = "This is just plain text"
        format_type = validator._detect_cookie_format(unknown_content)
        assert format_type == "unknown"
        
        # Empty content
        format_type = validator._detect_cookie_format("")
        assert format_type == "unknown"
        
        # Invalid JSON
        invalid_json = "{'invalid': json syntax}"
        format_type = validator._detect_cookie_format(invalid_json)
        assert format_type == "unknown"
    
    def test_netscape_validation_comprehensive(self, validator):
        """Test comprehensive Netscape format validation."""
        # Valid cookies with various scenarios
        valid_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1735689600	VISITOR_INFO1_LIVE	abc123
.google.com	TRUE	/watch	TRUE	1735689600	AUTH_TOKEN	def456
youtube.com	FALSE	/	FALSE	0	SESSION_ID	ghi789
.googleapis.com	TRUE	/api	FALSE	1735689600	API_KEY	jkl012
"""
        
        result = validator._validate_cookies(valid_cookies, "netscape")
        
        assert result['valid'] is True
        assert result['cookie_count'] == 4
        assert result['format'] == "netscape"
        assert set(result['domains']) == {'.youtube.com', '.google.com', 'youtube.com', '.googleapis.com'}
        assert len(result['issues']) == 0
    
    def test_netscape_validation_malformed_lines(self, validator):
        """Test validation of malformed Netscape lines."""
        # Missing fields
        malformed_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	VISITOR_INFO1_LIVE	abc123
.google.com	TRUE	/	TRUE	1735689600	AUTH_TOKEN	def456	extra_field
normal.com	FALSE	/	FALSE	1735689600	NORMAL	value
"""
        
        result = validator._validate_cookies(malformed_cookies, "netscape")
        
        # Should have warnings for malformed lines but still process valid ones
        assert result['cookie_count'] == 1  # Only the valid line
        assert len(result['warnings']) >= 2  # Warnings for malformed lines
    
    def test_json_validation_comprehensive(self, validator):
        """Test comprehensive JSON format validation."""
        # Valid JSON cookies
        cookies_data = [
            {
                "domain": ".youtube.com",
                "name": "VISITOR_INFO1_LIVE",
                "value": "abc123",
                "path": "/",
                "expires": int((datetime.now() + timedelta(days=30)).timestamp()),
                "secure": False,
                "httpOnly": True
            },
            {
                "domain": ".google.com",
                "name": "AUTH_TOKEN",
                "value": "def456",
                "path": "/auth",
                "expires": int((datetime.now() + timedelta(days=7)).timestamp()),
                "secure": True,
                "httpOnly": False
            }
        ]
        
        json_cookies = json.dumps(cookies_data)
        result = validator._validate_cookies(json_cookies, "json")
        
        assert result['valid'] is True
        assert result['cookie_count'] == 2
        assert result['format'] == "json"
        assert '.youtube.com' in result['domains']
        assert '.google.com' in result['domains']
    
    def test_json_validation_missing_fields(self, validator):
        """Test JSON validation with missing required fields."""
        # Missing domain field
        incomplete_cookies = [
            {"name": "test", "value": "123"},  # Missing domain
            {"domain": ".youtube.com", "value": "456"},  # Missing name
            {"domain": ".google.com", "name": "complete", "value": "789"}  # Complete
        ]
        
        json_cookies = json.dumps(incomplete_cookies)
        result = validator._validate_cookies(json_cookies, "json")
        
        assert result['cookie_count'] == 3
        assert len(result['warnings']) >= 2  # Warnings for missing fields
        assert '.google.com' in result['domains']  # Complete cookie processed
    
    def test_expiration_validation_various_formats(self, validator):
        """Test expiration validation with various timestamp formats."""
        now = datetime.now()
        
        # Future timestamps
        future_unix = int((now + timedelta(days=30)).timestamp())
        future_iso = (now + timedelta(days=30)).isoformat()
        
        # Past timestamps
        past_unix = int((now - timedelta(days=1)).timestamp())
        past_iso = (now - timedelta(days=1)).isoformat()
        
        # Test with Netscape format (Unix timestamps)
        future_cookies = f"""# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	{future_unix}	FUTURE	value
.youtube.com	TRUE	/	FALSE	{past_unix}	PAST	value
"""
        
        result = validator._validate_cookies(future_cookies, "netscape")
        
        assert result['cookie_count'] == 2
        assert len([w for w in result['warnings'] if 'expired' in w.lower()]) == 1
        
        # Test with JSON format (various formats)
        json_cookies = json.dumps([
            {"domain": ".youtube.com", "name": "future_unix", "expires": future_unix},
            {"domain": ".youtube.com", "name": "past_unix", "expires": past_unix},
            {"domain": ".youtube.com", "name": "future_iso", "expires": future_iso},
            {"domain": ".youtube.com", "name": "past_iso", "expires": past_iso}
        ])
        
        result = validator._validate_cookies(json_cookies, "json")
        
        assert result['cookie_count'] == 4
        assert len([w for w in result['warnings'] if 'expired' in w.lower()]) >= 2
    
    def test_session_cookie_handling(self, validator):
        """Test handling of session cookies (no expiration)."""
        # Session cookies have expires = 0 in Netscape format
        session_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	0	SESSION_TOKEN	abc123
.google.com	TRUE	/	FALSE	0	TEMP_ID	def456
"""
        
        result = validator._validate_cookies(session_cookies, "netscape")
        
        assert result['valid'] is True
        assert result['cookie_count'] == 2
        # Session cookies should not be marked as expired
        assert len([w for w in result['warnings'] if 'expired' in w.lower()]) == 0
    
    def test_domain_validation_youtube_presence(self, validator):
        """Test validation of YouTube/Google domain presence."""
        # Cookies with YouTube domains
        youtube_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1735689600	YT_TOKEN	abc123
.google.com	TRUE	/	FALSE	1735689600	GOOGLE_TOKEN	def456
"""
        
        result = validator._validate_cookies(youtube_cookies, "netscape")
        
        assert result['valid'] is True
        # Should not have YouTube domain warnings
        youtube_warnings = [w for w in result['warnings'] if 'youtube' in w.lower()]
        assert len(youtube_warnings) == 0
        
        # Cookies without YouTube domains
        non_youtube_cookies = """# Netscape HTTP Cookie File
.facebook.com	TRUE	/	FALSE	1735689600	FB_TOKEN	abc123
.twitter.com	TRUE	/	FALSE	1735689600	TW_TOKEN	def456
"""
        
        result = validator._validate_cookies(non_youtube_cookies, "netscape")
        
        assert result['valid'] is True  # Still valid
        # Should have YouTube domain warning
        youtube_warnings = [w for w in result['warnings'] if 'youtube' in w.lower() or 'google' in w.lower()]
        assert len(youtube_warnings) > 0
    
    def test_cookie_count_accuracy(self, validator):
        """Test accuracy of cookie counting."""
        # Mixed content with comments and empty lines
        mixed_content = """# Netscape HTTP Cookie File
# This is a comment

.youtube.com	TRUE	/	FALSE	1735689600	COOKIE1	value1

# Another comment
.google.com	TRUE	/	FALSE	1735689600	COOKIE2	value2

# Empty line above and below

.googleapis.com	TRUE	/	FALSE	1735689600	COOKIE3	value3
"""
        
        result = validator._validate_cookies(mixed_content, "netscape")
        
        assert result['cookie_count'] == 3  # Should count only actual cookie lines
        assert len(result['domains']) == 3
    
    def test_large_cookie_file_handling(self, validator):
        """Test handling of large cookie files."""
        # Generate large cookie content
        large_cookies = "# Netscape HTTP Cookie File\n"
        
        # Add 1000 cookies
        for i in range(1000):
            large_cookies += f".domain{i}.com	TRUE	/	FALSE	1735689600	COOKIE{i}	value{i}\n"
        
        result = validator._validate_cookies(large_cookies, "netscape")
        
        assert result['valid'] is True
        assert result['cookie_count'] == 1000
        assert len(result['domains']) == 1000
    
    def test_special_characters_in_cookies(self, validator):
        """Test handling of special characters in cookie values."""
        special_cookies = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	FALSE	1735689600	SPECIAL	value%20with%20spaces
.google.com	TRUE	/	FALSE	1735689600	UNICODE	value_with_ñ_and_emojis_🍪
.googleapis.com	TRUE	/	FALSE	1735689600	ENCODED	eyJhbGciOiJIUzI1NiJ9
"""
        
        result = validator._validate_cookies(special_cookies, "netscape")
        
        assert result['valid'] is True
        assert result['cookie_count'] == 3
    
    def test_validation_performance(self, validator):
        """Test validation performance with timing."""
        import time
        
        # Create moderately large cookie file
        large_cookies = "# Netscape HTTP Cookie File\n"
        for i in range(100):
            large_cookies += f".domain{i}.com	TRUE	/	FALSE	1735689600	COOKIE{i}	value{i}\n"
        
        start_time = time.time()
        result = validator._validate_cookies(large_cookies, "netscape")
        end_time = time.time()
        
        validation_time = end_time - start_time
        
        assert result['valid'] is True
        assert result['cookie_count'] == 100
        # Validation should be fast (less than 1 second for 100 cookies)
        assert validation_time < 1.0
    
    @pytest.mark.parametrize("format_type,content,expected_valid", [
        ("netscape", "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t1735689600\tTEST\tvalue", True),
        ("netscape", ".youtube.com\tTRUE\t/\tFALSE\t1735689600\tTEST\tvalue", True),
        ("netscape", "invalid format", False),
        ("json", '[{"domain": ".youtube.com", "name": "TEST", "value": "123"}]', True),
        ("json", '{"domain": ".youtube.com", "name": "TEST", "value": "123"}', True),
        ("json", 'invalid json', False),
        ("unknown", "anything", False),
    ])
    def test_validation_edge_cases(self, validator, format_type, content, expected_valid):
        """Test validation edge cases with parametrized inputs."""
        result = validator._validate_cookies(content, format_type)
        
        assert result['valid'] == expected_valid
        if expected_valid:
            assert result['cookie_count'] >= 0
        else:
            assert len(result['issues']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])