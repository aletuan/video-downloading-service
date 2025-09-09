from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.core.database import init_database, close_database, db_manager
from app.core.storage import init_storage, health_check_storage
from app.core.security_middleware import add_security_middleware
from app.core.auth import require_authentication
from app.core.cookie_manager import CookieManager

# Import routers
from app.routers import downloads, websocket, admin, bootstrap

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def check_cookie_manager_health():
    """Check cookie manager health status."""
    if not settings.cookie_s3_bucket:
        return {
            "status": "disabled",
            "message": "Cookie management is disabled"
        }
    
    try:
        cookie_manager = CookieManager()
        
        # Test cookie manager initialization
        metadata = await cookie_manager.get_cookie_metadata()
        
        return {
            "status": "healthy",
            "message": "Cookie manager is operational",
            "details": {
                "s3_bucket": settings.cookie_s3_bucket,
                "encryption_enabled": True,
                "validation_enabled": settings.cookie_validation_enabled,
                "metadata_available": metadata is not None
            }
        }
    except Exception as e:
        logger.error(f"Cookie manager health check failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Cookie manager error: {str(e)}",
            "details": {
                "s3_bucket": settings.cookie_s3_bucket,
                "error_type": type(e).__name__
            }
        }


async def validate_container_startup():
    """Validate container startup requirements and configuration."""
    validation_results = {
        "environment_vars": [],
        "dependencies": [],
        "configuration": []
    }
    
    # Check critical environment variables
    required_env_vars = ["DATABASE_URL", "REDIS_URL", "ENVIRONMENT"]
    for var in required_env_vars:
        if hasattr(settings, var.lower()) and getattr(settings, var.lower()):
            validation_results["environment_vars"].append({
                "name": var,
                "status": "present",
                "message": "Required environment variable is set"
            })
        else:
            validation_results["environment_vars"].append({
                "name": var,
                "status": "missing",
                "message": f"Required environment variable {var} is missing"
            })
    
    # Check cookie management configuration
    if settings.cookie_s3_bucket:
        validation_results["configuration"].append({
            "component": "cookie_management",
            "status": "enabled",
            "message": f"Cookie management enabled with bucket: {settings.cookie_s3_bucket}"
        })
        
        # Validate encryption key presence
        if settings.cookie_encryption_key and len(settings.cookie_encryption_key) >= 32:
            validation_results["configuration"].append({
                "component": "cookie_encryption",
                "status": "valid",
                "message": "Cookie encryption key is properly configured"
            })
        else:
            validation_results["configuration"].append({
                "component": "cookie_encryption",
                "status": "invalid",
                "message": "Cookie encryption key is missing or too short"
            })
    else:
        validation_results["configuration"].append({
            "component": "cookie_management",
            "status": "disabled",
            "message": "Cookie management is disabled (no S3 bucket configured)"
        })
    
    # Check database configuration
    try:
        validation_results["dependencies"].append({
            "service": "database",
            "status": "configurable",
            "message": "Database URL is configured"
        })
    except Exception as e:
        validation_results["dependencies"].append({
            "service": "database",
            "status": "error",
            "message": f"Database configuration error: {str(e)}"
        })
    
    # Check Redis configuration
    try:
        validation_results["dependencies"].append({
            "service": "redis",
            "status": "configurable", 
            "message": "Redis URL is configured"
        })
    except Exception as e:
        validation_results["dependencies"].append({
            "service": "redis",
            "status": "error",
            "message": f"Redis configuration error: {str(e)}"
        })
    
    return validation_results


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting YouTube Download Service...")
    
    try:
        # Validate startup configuration
        validation_results = await validate_container_startup()
        logger.info("Container startup validation completed")
        
        # Log validation results
        for category, results in validation_results.items():
            for result in results:
                if result.get("status") in ["missing", "invalid", "error"]:
                    logger.warning(f"Validation {category}: {result.get('message', 'Unknown issue')}")
                else:
                    logger.info(f"Validation {category}: {result.get('message', 'OK')}")
        # Initialize database
        await init_database()
        logger.info("Database initialized successfully")
        
        # Initialize storage
        storage = init_storage()
        logger.info(f"Storage initialized: {type(storage).__name__}")
        
        # Initialize cookie manager (only if cookie management is enabled)
        if settings.cookie_s3_bucket:
            try:
                cookie_manager = CookieManager()
                logger.info("Cookie manager initialized successfully")
            except Exception as e:
                logger.warning(f"Cookie manager initialization failed (will run without cookies): {e}")
        else:
            logger.info("Cookie management disabled (no S3 bucket configured)")
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down YouTube Download Service...")
    try:
        await close_database()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


app = FastAPI(
    title="YouTube Download Service",
    description="A Python-based cloud-native application for downloading YouTube videos with transcriptions",
    version="1.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# Security middleware (includes CORS, authentication, rate limiting, security headers)
add_security_middleware(app, debug_mode=settings.debug)

# Health check endpoints
@app.get("/health")
async def basic_health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "1.0.0"
    }


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with database and storage status."""
    try:
        # Check database health
        db_health = await db_manager.health_check()
        
        # Check storage health  
        storage_health = await health_check_storage()
        
        # Check cookie manager health
        cookie_health = await check_cookie_manager_health()
        
        # Determine overall status
        overall_status = "healthy"
        if (db_health.get("status") != "healthy" or 
            storage_health.get("status") != "healthy" or
            cookie_health.get("status") == "unhealthy"):
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "environment": settings.environment,
            "version": "1.0.0",
            "timestamp": "2025-09-04T12:05:00Z",  # Will be replaced with actual timestamp
            "checks": {
                "database": db_health,
                "storage": storage_health,
                "cookie_manager": cookie_health,
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "environment": settings.environment,
            "version": "1.0.0",
            "error": str(e)
        }


# Static file serving for local storage
if settings.environment == "localhost":
    downloads_path = Path(settings.download_base_path).resolve()
    downloads_path.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(downloads_path)), name="files")
    logger.info(f"Static file serving enabled at /files -> {downloads_path}")

# Include routers
app.include_router(bootstrap.router, prefix="/api/v1", tags=["bootstrap"])  # No auth required for bootstrap
app.include_router(downloads.router, prefix="/api/v1", tags=["downloads"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )