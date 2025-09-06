"""
Input validation and sanitization utilities.

This module provides comprehensive input validation and sanitization
to protect against various attacks and ensure data integrity.
"""

import re
import html
import bleach
from typing import Optional, List, Dict, Any, Union
from urllib.parse import urlparse, parse_qs
import validators
from pydantic import field_validator, model_validator
import logging

logger = logging.getLogger(__name__)


class InputValidator:
    """Comprehensive input validation and sanitization utilities."""
    
    # YouTube URL patterns
    YOUTUBE_PATTERNS = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?m\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    ]
    
    # Dangerous patterns to check for
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',               # JavaScript URLs
        r'vbscript:',                # VBScript URLs  
        r'data:',                    # Data URLs
        r'onload=',                  # Event handlers
        r'onerror=',                 # Error handlers
        r'onclick=',                 # Click handlers
        r'eval\(',                   # eval() calls
        r'exec\(',                   # exec() calls
        r'<iframe',                  # iframes
        r'<object',                  # objects
        r'<embed',                   # embeds
        r'<form',                    # forms
        r'<input',                   # inputs
        r'<meta',                    # meta tags
        r'<link',                    # link tags
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'(?:\'|"|\`|;|--|\|\|)',     # Basic SQL chars
        r'(?:union|select|insert|update|delete|drop|create|alter|exec)',  # SQL keywords
        r'(?:script|javascript|vbscript|onload|onerror)',  # XSS patterns
        r'(?:\<|\>|&lt;|&gt;)',       # HTML brackets
    ]
    
    @staticmethod
    def sanitize_string(
        input_string: str, 
        max_length: Optional[int] = None,
        allow_html: bool = False,
        strip_dangerous: bool = True
    ) -> str:
        """
        Sanitize a string input.
        
        Args:
            input_string: The string to sanitize
            max_length: Maximum allowed length
            allow_html: Whether to allow HTML tags
            strip_dangerous: Whether to strip dangerous patterns
            
        Returns:
            str: Sanitized string
            
        Raises:
            ValueError: If input is invalid
        """
        if not isinstance(input_string, str):
            raise ValueError("Input must be a string")
        
        # Strip whitespace
        sanitized = input_string.strip()
        
        # Check length
        if max_length and len(sanitized) > max_length:
            raise ValueError(f"Input too long: {len(sanitized)} > {max_length}")
        
        # Strip dangerous patterns
        if strip_dangerous:
            for pattern in InputValidator.DANGEROUS_PATTERNS:
                if re.search(pattern, sanitized, re.IGNORECASE):
                    logger.warning(f"Dangerous pattern detected: {pattern}")
                    sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        # Handle HTML
        if not allow_html:
            # Escape HTML entities
            sanitized = html.escape(sanitized)
        else:
            # Allow only safe HTML tags
            allowed_tags = ['b', 'i', 'u', 'strong', 'em', 'p', 'br', 'a']
            allowed_attributes = {'a': ['href', 'title']}
            sanitized = bleach.clean(
                sanitized, 
                tags=allowed_tags, 
                attributes=allowed_attributes,
                strip=True
            )
        
        return sanitized
    
    @staticmethod
    def validate_youtube_url(url: str) -> Dict[str, Any]:
        """
        Validate and extract information from YouTube URL.
        
        Args:
            url: YouTube URL to validate
            
        Returns:
            dict: URL validation result with video_id if valid
            
        Raises:
            ValueError: If URL is invalid
        """
        if not isinstance(url, str):
            raise ValueError("URL must be a string")
        
        # Basic URL validation
        if not validators.url(url) and not url.startswith('youtu'):
            # Try to add protocol if missing
            if not url.startswith('http'):
                url = 'https://' + url
                if not validators.url(url):
                    raise ValueError("Invalid URL format")
        
        # Extract video ID using patterns
        video_id = None
        for pattern in InputValidator.YOUTUBE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                break
        
        if not video_id:
            raise ValueError("Invalid YouTube URL: cannot extract video ID")
        
        # Validate video ID format
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            raise ValueError("Invalid YouTube video ID format")
        
        # Parse URL components
        parsed_url = urlparse(url if url.startswith('http') else 'https://' + url)
        
        return {
            'is_valid': True,
            'video_id': video_id,
            'original_url': url,
            'canonical_url': f'https://www.youtube.com/watch?v={video_id}',
            'domain': parsed_url.netloc,
            'path': parsed_url.path,
            'query_params': parse_qs(parsed_url.query)
        }
    
    @staticmethod
    def validate_api_key_name(name: str) -> str:
        """
        Validate API key name.
        
        Args:
            name: API key name to validate
            
        Returns:
            str: Sanitized name
            
        Raises:
            ValueError: If name is invalid
        """
        if not isinstance(name, str):
            raise ValueError("API key name must be a string")
        
        # Sanitize and validate
        sanitized = InputValidator.sanitize_string(
            name, 
            max_length=100, 
            allow_html=False, 
            strip_dangerous=True
        )
        
        if len(sanitized.strip()) < 1:
            raise ValueError("API key name cannot be empty")
        
        # Check for only alphanumeric, spaces, hyphens, underscores
        if not re.match(r'^[a-zA-Z0-9\s\-_]+$', sanitized):
            raise ValueError("API key name contains invalid characters")
        
        return sanitized.strip()
    
    @staticmethod
    def validate_description(description: Optional[str], max_length: int = 500) -> Optional[str]:
        """
        Validate description field.
        
        Args:
            description: Description to validate
            max_length: Maximum length allowed
            
        Returns:
            Optional[str]: Sanitized description or None
            
        Raises:
            ValueError: If description is invalid
        """
        if description is None:
            return None
        
        if not isinstance(description, str):
            raise ValueError("Description must be a string")
        
        # Sanitize
        sanitized = InputValidator.sanitize_string(
            description,
            max_length=max_length,
            allow_html=False,
            strip_dangerous=True
        )
        
        return sanitized.strip() if sanitized.strip() else None
    
    @staticmethod
    def check_sql_injection(input_string: str) -> bool:
        """
        Check if string contains potential SQL injection patterns.
        
        Args:
            input_string: String to check
            
        Returns:
            bool: True if potential SQL injection detected
        """
        if not isinstance(input_string, str):
            return False
        
        for pattern in InputValidator.SQL_INJECTION_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE):
                logger.warning(f"Potential SQL injection pattern detected: {pattern}")
                return True
        
        return False
    
    @staticmethod
    def validate_integer_range(
        value: Union[int, str], 
        min_val: Optional[int] = None, 
        max_val: Optional[int] = None,
        field_name: str = "value"
    ) -> int:
        """
        Validate integer within range.
        
        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            field_name: Field name for error messages
            
        Returns:
            int: Validated integer
            
        Raises:
            ValueError: If value is invalid
        """
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError:
                raise ValueError(f"{field_name} must be a valid integer")
        
        if not isinstance(value, int):
            raise ValueError(f"{field_name} must be an integer")
        
        if min_val is not None and value < min_val:
            raise ValueError(f"{field_name} must be at least {min_val}")
        
        if max_val is not None and value > max_val:
            raise ValueError(f"{field_name} must be at most {max_val}")
        
        return value
    
    @staticmethod
    def validate_quality_setting(quality: str) -> str:
        """
        Validate video quality setting.
        
        Args:
            quality: Quality setting to validate
            
        Returns:
            str: Validated quality setting
            
        Raises:
            ValueError: If quality is invalid
        """
        valid_qualities = [
            'best', 'worst', 'bestvideo', 'worstvideo',
            '144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p', '4320p'
        ]
        
        if not isinstance(quality, str):
            raise ValueError("Quality must be a string")
        
        quality = quality.strip().lower()
        
        if quality not in valid_qualities:
            raise ValueError(f"Invalid quality setting. Must be one of: {', '.join(valid_qualities)}")
        
        return quality
    
    @staticmethod
    def validate_format_setting(format_setting: str) -> str:
        """
        Validate output format setting.
        
        Args:
            format_setting: Format setting to validate
            
        Returns:
            str: Validated format setting
            
        Raises:
            ValueError: If format is invalid
        """
        valid_formats = ['mp4', 'mkv', 'webm', 'avi', 'flv', 'm4a', 'mp3', 'aac', 'ogg', 'wav']
        
        if not isinstance(format_setting, str):
            raise ValueError("Format must be a string")
        
        format_setting = format_setting.strip().lower()
        
        if format_setting not in valid_formats:
            raise ValueError(f"Invalid format setting. Must be one of: {', '.join(valid_formats)}")
        
        return format_setting
    
    @staticmethod
    def validate_subtitle_languages(languages: Optional[List[str]]) -> Optional[List[str]]:
        """
        Validate subtitle language list.
        
        Args:
            languages: List of language codes to validate
            
        Returns:
            Optional[List[str]]: Validated language list or None
            
        Raises:
            ValueError: If languages are invalid
        """
        if languages is None:
            return None
        
        if not isinstance(languages, list):
            raise ValueError("Subtitle languages must be a list")
        
        if len(languages) > 10:
            raise ValueError("Too many subtitle languages (max 10)")
        
        validated_languages = []
        for lang in languages:
            if not isinstance(lang, str):
                raise ValueError("Language code must be a string")
            
            # Validate language code format (2-3 characters)
            lang = lang.strip().lower()
            if not re.match(r'^[a-z]{2,3}(-[a-z]{2})?$', lang):
                raise ValueError(f"Invalid language code format: {lang}")
            
            validated_languages.append(lang)
        
        return validated_languages if validated_languages else None


class SecurityValidationMixin:
    """
    Mixin class to add security validation to Pydantic models.
    """
    
    @model_validator(mode='before')
    @classmethod
    def validate_strings(cls, values):
        """Pre-validator to check all string fields for security issues."""
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, str):
                    # Check for SQL injection patterns
                    if InputValidator.check_sql_injection(value):
                        raise ValueError(f"Field '{key}' contains potentially dangerous patterns")
                    
                    # Basic sanitization
                    values[key] = InputValidator.sanitize_string(value, strip_dangerous=True)
        
        return values


# Custom Pydantic field types with built-in validation

def YouTubeUrlField(**kwargs):
    """Custom Pydantic field for YouTube URLs with validation."""
    def validate_youtube_url(cls, v):
        try:
            result = InputValidator.validate_youtube_url(v)
            return result['canonical_url']
        except ValueError as e:
            raise ValueError(f"Invalid YouTube URL: {e}")
    
    return validator('*', allow_reuse=True)(validate_youtube_url)


def SafeStringField(max_length: int = 500, **kwargs):
    """Custom Pydantic field for safe string input."""
    def validate_safe_string(cls, v):
        if not isinstance(v, str):
            raise ValueError("Field must be a string")
        return InputValidator.sanitize_string(v, max_length=max_length)
    
    return validator('*', allow_reuse=True)(validate_safe_string)


# Export main classes and functions
__all__ = [
    'InputValidator',
    'SecurityValidationMixin', 
    'YouTubeUrlField',
    'SafeStringField'
]