"""
Security middleware for FastAPI application.

This module provides:
- Authentication middleware for API key validation
- Rate limiting middleware
- Security headers middleware
- Request/response security handling
"""

import time
from typing import Optional, Callable, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import HTTPException
import logging

from app.core.auth import (
    SecurityConfig, 
    get_current_api_key_info,
    get_client_identifier,
    rate_limiter,
    AuthenticationError,
    RateLimitError
)

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add security headers to response.
        
        Args:
            request: The incoming request
            call_next: The next middleware/endpoint
            
        Returns:
            Response: Response with added security headers
        """
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Add security headers
            for header, value in SecurityConfig.SECURITY_HEADERS.items():
                response.headers[header] = value
            
            # Add processing time header (useful for monitoring)
            processing_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(processing_time)
            
            return response
            
        except Exception as e:
            logger.error(f"Security headers middleware error: {e}")
            # Return error response with security headers
            error_response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
            
            for header, value in SecurityConfig.SECURITY_HEADERS.items():
                error_response.headers[header] = value
                
            return error_response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle rate limiting for all requests.
    """
    
    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.excluded_paths = excluded_paths or ["/health", "/health/detailed", "/docs", "/redoc", "/openapi.json"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Check rate limits before processing request.
        
        Args:
            request: The incoming request
            call_next: The next middleware/endpoint
            
        Returns:
            Response: Response or rate limit error
        """
        # Skip rate limiting for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        try:
            # Try to get API key info (may be None for unauthenticated requests)
            api_key_info = None
            try:
                api_key_info = await get_current_api_key_info(request)
            except (AuthenticationError, RateLimitError):
                # These will be handled by authentication middleware if needed
                pass
            
            # Get client identifier for rate limiting
            client_id = get_client_identifier(request, api_key_info)
            
            # Determine permission level for rate limiting
            if api_key_info:
                permission_level = api_key_info["permission_level"]
                # Use custom rate limit if set
                if api_key_info.get("custom_rate_limit"):
                    custom_limit = api_key_info["custom_rate_limit"]
                    SecurityConfig.RATE_LIMITS[permission_level] = custom_limit
            else:
                permission_level = "anonymous"
            
            # Check rate limit
            if not await rate_limiter.check_rate_limit(client_id, permission_level):
                rate_info = await rate_limiter.get_rate_limit_info(client_id, permission_level)
                
                error_response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded. Max {rate_info['limit']} requests per minute.",
                        "rate_limit": rate_info
                    }
                )
                
                # Add rate limit headers
                error_response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
                error_response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
                error_response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])
                
                return error_response
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit info headers to successful responses
            if api_key_info or permission_level:
                rate_info = await rate_limiter.get_rate_limit_info(client_id, permission_level)
                response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
                response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
                response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limiting middleware error: {e}")
            # On error, allow request to proceed (fail open for availability)
            return await call_next(request)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle API key authentication and set user context.
    
    This middleware doesn't enforce authentication - it just sets the context.
    Individual endpoints can use dependencies to require authentication.
    """
    
    def __init__(self, app, public_paths: Optional[list] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/health", 
            "/health/detailed", 
            "/docs", 
            "/redoc", 
            "/openapi.json",
            "/api/v1/info"  # Allow info endpoint without auth
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Set authentication context for request.
        
        Args:
            request: The incoming request
            call_next: The next middleware/endpoint
            
        Returns:
            Response: Response with authentication context
        """
        try:
            # Check if this is a public path
            is_public_path = any(request.url.path.startswith(path) for path in self.public_paths)
            
            # Try to authenticate the request (but don't enforce it here)
            api_key_info = None
            if not is_public_path:
                try:
                    api_key_info = await get_current_api_key_info(request)
                except AuthenticationError:
                    # Don't block request here - let endpoint handle auth requirements
                    pass
                except RateLimitError as e:
                    # Rate limiting is enforced at middleware level
                    return JSONResponse(
                        status_code=429,
                        content={"detail": str(e)}
                    )
            
            # Set authentication context in request state
            request.state.api_key_info = api_key_info
            request.state.is_authenticated = api_key_info is not None
            
            # Process request
            response = await call_next(request)
            
            # Add authentication status headers (for debugging/monitoring)
            if api_key_info:
                response.headers["X-Auth-Status"] = "authenticated"
                response.headers["X-Auth-Permission"] = api_key_info["permission_level"]
            else:
                response.headers["X-Auth-Status"] = "anonymous"
            
            return response
            
        except Exception as e:
            logger.error(f"Authentication middleware error: {e}")
            # On error, proceed without authentication (let endpoints handle requirements)
            request.state.api_key_info = None
            request.state.is_authenticated = False
            return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log requests and responses for monitoring and debugging.
    """
    
    def __init__(self, app, log_sensitive_data: bool = False):
        super().__init__(app)
        self.log_sensitive_data = log_sensitive_data
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log request and response information.
        
        Args:
            request: The incoming request
            call_next: The next middleware/endpoint
            
        Returns:
            Response: Response with logging
        """
        start_time = time.time()
        
        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Get authentication info if available
        api_key_info = getattr(request.state, "api_key_info", None)
        auth_user = api_key_info["name"] if api_key_info else "anonymous"
        
        try:
            response = await call_next(request)
            processing_time = time.time() - start_time
            
            # Log successful request
            logger.info(
                f"{method} {path} - {response.status_code} "
                f"({processing_time:.3f}s) - {client_ip} - {auth_user}"
            )
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Log failed request
            logger.error(
                f"{method} {path} - ERROR ({processing_time:.3f}s) - "
                f"{client_ip} - {auth_user} - {str(e)}"
            )
            
            # Re-raise the exception
            raise


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """
    Enhanced CORS middleware with security considerations.
    """
    
    def __init__(
        self, 
        app, 
        allow_origins: list = None,
        allow_methods: list = None,
        allow_headers: list = None,
        allow_credentials: bool = True
    ):
        super().__init__(app)
        self.allow_origins = allow_origins or ["https://yourdomain.com"] if not hasattr(app, "_debug") else ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Handle CORS with security considerations.
        
        Args:
            request: The incoming request
            call_next: The next middleware/endpoint
            
        Returns:
            Response: Response with CORS headers
        """
        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
        else:
            response = await call_next(request)
        
        # Add CORS headers
        origin = request.headers.get("origin")
        if origin and (origin in self.allow_origins or "*" in self.allow_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
        
        response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
        response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
        
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response


# Convenience function to add all security middleware
def add_security_middleware(app, debug_mode: bool = False):
    """
    Add all security middleware to FastAPI application.
    
    Args:
        app: FastAPI application instance
        debug_mode: Whether debug mode is enabled
    """
    # Add middleware in reverse order (last added = first executed)
    
    # 1. Request logging (outermost)
    app.add_middleware(RequestLoggingMiddleware, log_sensitive_data=debug_mode)
    
    # 2. Security headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 3. CORS handling
    app.add_middleware(
        CORSSecurityMiddleware,
        allow_origins=["*"] if debug_mode else ["https://yourdomain.com"],
        allow_credentials=True
    )
    
    # 4. Rate limiting
    app.add_middleware(RateLimitingMiddleware)
    
    # 5. Authentication context (innermost)
    app.add_middleware(AuthenticationMiddleware)
    
    logger.info("All security middleware added to FastAPI application")


# Export main classes and functions
__all__ = [
    "SecurityHeadersMiddleware",
    "RateLimitingMiddleware", 
    "AuthenticationMiddleware",
    "RequestLoggingMiddleware",
    "CORSSecurityMiddleware",
    "add_security_middleware"
]