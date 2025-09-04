"""
Authentication and security module for the YouTube Video Download Service.

This module provides:
- API key generation and validation
- FastAPI authentication dependencies
- Security utilities and middleware
- Rate limiting integration
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from enum import Enum

from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery, APIKeyCookie
import redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.config import settings
from app.core.database import get_db_session

logger = logging.getLogger(__name__)

# Security schemes for FastAPI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)
bearer_security = HTTPBearer(auto_error=False)

# Redis connection for rate limiting (reuse existing Redis connection)
def get_redis_client():
    """Get Redis client for rate limiting."""
    return redis.from_url(settings.redis_url, decode_responses=True)


class APIKeyPermission(str, Enum):
    """API key permission levels."""
    READ_ONLY = "read_only"      # Can only get status, info, list jobs
    DOWNLOAD = "download"         # Can create download jobs
    ADMIN = "admin"              # Can manage API keys and access admin endpoints
    FULL_ACCESS = "full_access"  # All permissions


class SecurityConfig:
    """Security configuration and constants."""
    
    # API Key settings
    API_KEY_LENGTH = 32
    API_KEY_PREFIX = "yvs_"  # YouTube Video Service prefix
    
    # Rate limiting settings (per minute)
    RATE_LIMITS = {
        APIKeyPermission.READ_ONLY: 100,
        APIKeyPermission.DOWNLOAD: 10,
        APIKeyPermission.ADMIN: 20,
        APIKeyPermission.FULL_ACCESS: 50,
        "anonymous": 5  # For unauthenticated requests
    }
    
    # Security headers
    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }


class AuthenticationError(HTTPException):
    """Custom authentication error."""
    
    def __init__(self, detail: str = "Authentication failed"):
        super().__init__(status_code=401, detail=detail)


class RateLimitError(HTTPException):
    """Rate limiting error."""
    
    def __init__(self, detail: str = "Rate limit exceeded"):
        super().__init__(status_code=429, detail=detail)


class APIKeyGenerator:
    """Utility class for generating and validating API keys."""
    
    @staticmethod
    def generate_api_key() -> str:
        """
        Generate a secure API key.
        
        Returns:
            str: Generated API key with prefix
        """
        # Generate random bytes and encode as hex
        random_bytes = secrets.token_bytes(SecurityConfig.API_KEY_LENGTH)
        key_suffix = random_bytes.hex()
        
        return f"{SecurityConfig.API_KEY_PREFIX}{key_suffix}"
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """
        Hash an API key for secure storage.
        
        Args:
            api_key: The API key to hash
            
        Returns:
            str: SHA-256 hash of the API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def verify_api_key_format(api_key: str) -> bool:
        """
        Verify API key format is valid.
        
        Args:
            api_key: The API key to verify
            
        Returns:
            bool: True if format is valid
        """
        if not api_key.startswith(SecurityConfig.API_KEY_PREFIX):
            return False
        
        # Check length (prefix + hex string)
        expected_length = len(SecurityConfig.API_KEY_PREFIX) + (SecurityConfig.API_KEY_LENGTH * 2)
        return len(api_key) == expected_length


class RateLimiter:
    """Rate limiting implementation using Redis."""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client()
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        permission_level: str, 
        window_minutes: int = 1
    ) -> bool:
        """
        Check if identifier is within rate limit.
        
        Args:
            identifier: Unique identifier (API key hash, IP, etc.)
            permission_level: Permission level to get rate limit
            window_minutes: Time window in minutes
            
        Returns:
            bool: True if within rate limit
        """
        try:
            # Get rate limit for permission level
            rate_limit = SecurityConfig.RATE_LIMITS.get(permission_level, SecurityConfig.RATE_LIMITS["anonymous"])
            
            # Create Redis key with time window
            current_minute = int(time.time() // (60 * window_minutes))
            redis_key = f"rate_limit:{identifier}:{current_minute}"
            
            # Increment counter and set expiry
            current_count = self.redis.incr(redis_key)
            if current_count == 1:
                self.redis.expire(redis_key, 60 * window_minutes)
            
            return current_count <= rate_limit
            
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # On Redis error, allow request (fail open)
            return True
    
    async def get_rate_limit_info(self, identifier: str, permission_level: str) -> Dict[str, int]:
        """
        Get current rate limit status.
        
        Args:
            identifier: Unique identifier
            permission_level: Permission level
            
        Returns:
            dict: Rate limit information
        """
        try:
            rate_limit = SecurityConfig.RATE_LIMITS.get(permission_level, SecurityConfig.RATE_LIMITS["anonymous"])
            current_minute = int(time.time() // 60)
            redis_key = f"rate_limit:{identifier}:{current_minute}"
            
            current_count = self.redis.get(redis_key)
            current_count = int(current_count) if current_count else 0
            
            return {
                "limit": rate_limit,
                "current": current_count,
                "remaining": max(0, rate_limit - current_count),
                "reset_time": (current_minute + 1) * 60
            }
        except Exception as e:
            logger.error(f"Rate limit info error: {e}")
            return {
                "limit": 0,
                "current": 0, 
                "remaining": 0,
                "reset_time": 0
            }


# Global rate limiter instance
rate_limiter = RateLimiter()


async def get_api_key_from_request(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query),
    authorization: Optional[HTTPAuthorizationCredentials] = Security(bearer_security)
) -> Optional[str]:
    """
    Extract API key from various sources in the request.
    
    Priority order:
    1. X-API-Key header
    2. api_key query parameter  
    3. Bearer token in Authorization header
    
    Args:
        api_key_header: API key from X-API-Key header
        api_key_query: API key from query parameter
        authorization: Bearer token from Authorization header
        
    Returns:
        Optional[str]: API key if found, None otherwise
    """
    # Check header first
    if api_key_header:
        return api_key_header
    
    # Check query parameter
    if api_key_query:
        return api_key_query
    
    # Check Authorization header (Bearer token)
    if authorization and authorization.scheme.lower() == "bearer":
        return authorization.credentials
    
    return None


async def validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Validate API key against database.
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Optional[Dict]: API key info if valid, None otherwise
    """
    if not APIKeyGenerator.verify_api_key_format(api_key):
        return None
    
    try:
        # Hash the API key for database lookup
        api_key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Query database for API key
        from app.models.database import APIKey
        
        async with get_db_session() as session:
            # Find API key by hash
            result = await session.execute(
                select(APIKey).where(APIKey.key_hash == api_key_hash)
            )
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record or not api_key_record.is_valid:
                return None
            
            # Update last used timestamp and usage count
            api_key_record.last_used_at = datetime.now(timezone.utc)
            api_key_record.usage_count += 1
            await session.commit()
            
            # Return API key information
            return {
                "id": str(api_key_record.id),
                "name": api_key_record.name,
                "permission_level": api_key_record.permission_level,
                "is_active": api_key_record.is_active,
                "created_at": api_key_record.created_at,
                "last_used_at": api_key_record.last_used_at,
                "usage_count": api_key_record.usage_count,
                "custom_rate_limit": api_key_record.custom_rate_limit,
                "expires_at": api_key_record.expires_at
            }
        
    except Exception as e:
        logger.error(f"API key validation error: {e}")
        return None


async def get_current_api_key_info(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query), 
    authorization: Optional[HTTPAuthorizationCredentials] = Security(bearer_security)
) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated API key information.
    
    Returns:
        Optional[Dict]: API key info if authenticated, None otherwise
    """
    # Extract API key from request
    api_key = await get_api_key_from_request(
        api_key_header,
        api_key_query,
        authorization
    )
    
    if not api_key:
        return None
    
    # Validate API key
    api_key_info = await validate_api_key(api_key)
    if not api_key_info:
        return None
    
    # Check rate limiting
    identifier = APIKeyGenerator.hash_api_key(api_key)
    permission_level = api_key_info["permission_level"]
    
    if not await rate_limiter.check_rate_limit(identifier, permission_level):
        raise RateLimitError(
            detail=f"Rate limit exceeded for permission level: {permission_level}"
        )
    
    return api_key_info


# Authentication dependency functions

async def require_authentication(
    api_key_info: Optional[Dict[str, Any]] = Depends(get_current_api_key_info)
) -> Dict[str, Any]:
    """
    Require valid authentication for endpoint access.
        
    Returns:
        Dict: API key information
        
    Raises:
        AuthenticationError: If authentication fails
        RateLimitError: If rate limit exceeded
    """
    
    if not api_key_info:
        raise AuthenticationError("Valid API key required")
    
    return api_key_info


def require_permission(required_permission: APIKeyPermission):
    """
    Create a dependency that requires specific permission level.
    
    Args:
        required_permission: Required permission level
        
    Returns:
        Dependency function
    """
    async def check_permission(api_key_info: Dict = Depends(require_authentication)) -> Dict[str, Any]:
        user_permission = api_key_info["permission_level"]
        
        # Check if user has required permission or full access
        if (user_permission != required_permission and 
            user_permission != APIKeyPermission.FULL_ACCESS and
            user_permission != APIKeyPermission.ADMIN):
            raise HTTPException(
                status_code=403,
                detail=f"Permission '{required_permission}' required"
            )
        
        return api_key_info
    
    return check_permission


async def require_admin_permission(api_key_info: Dict = Depends(require_authentication)) -> Dict[str, Any]:
    """
    Require admin permission level.
    
    Args:
        api_key_info: API key information from authentication
        
    Returns:
        Dict: API key information
        
    Raises:
        HTTPException: If admin permission not granted
    """
    if api_key_info["permission_level"] not in [APIKeyPermission.ADMIN, APIKeyPermission.FULL_ACCESS]:
        raise HTTPException(
            status_code=403,
            detail="Admin permission required"
        )
    
    return api_key_info


# Optional authentication (for endpoints that work with or without auth)
async def optional_authentication(request: Request) -> Optional[Dict[str, Any]]:
    """
    Optional authentication - returns API key info if present, None otherwise.
    Does not raise errors for missing authentication.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Optional[Dict]: API key info if authenticated, None otherwise
    """
    try:
        return await get_current_api_key_info(request)
    except (AuthenticationError, RateLimitError):
        return None


def get_client_identifier(request: Request, api_key_info: Optional[Dict[str, Any]] = None) -> str:
    """
    Get a unique identifier for the client (for rate limiting).
    
    Args:
        request: FastAPI request object
        api_key_info: Optional API key information
        
    Returns:
        str: Unique client identifier
    """
    if api_key_info:
        # Use API key hash as identifier
        return api_key_info.get("id", "unknown")
    
    # Fall back to IP address for anonymous requests
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


# Export main authentication dependencies
__all__ = [
    "APIKeyPermission",
    "SecurityConfig", 
    "APIKeyGenerator",
    "RateLimiter",
    "AuthenticationError",
    "RateLimitError",
    "require_authentication",
    "require_permission", 
    "require_admin_permission",
    "optional_authentication",
    "get_client_identifier",
    "rate_limiter"
]