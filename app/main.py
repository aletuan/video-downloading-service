from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_database, close_database, db_manager
from app.core.storage import init_storage, health_check_storage

# Import routers (will be implemented later)
# from app.routers import downloads, health, websocket

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting YouTube Download Service...")
    
    try:
        # Initialize database
        await init_database()
        logger.info("Database initialized successfully")
        
        # Initialize storage
        storage = init_storage()
        logger.info(f"Storage initialized: {type(storage).__name__}")
        
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        
        # Determine overall status
        overall_status = "healthy"
        if (db_health.get("status") != "healthy" or 
            storage_health.get("status") != "healthy"):
            overall_status = "unhealthy"
        
        return {
            "status": overall_status,
            "environment": settings.environment,
            "version": "1.0.0",
            "timestamp": "2025-09-04T12:05:00Z",  # Will be replaced with actual timestamp
            "checks": {
                "database": db_health,
                "storage": storage_health,
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

# Include routers (commented out until implemented)
# app.include_router(downloads.router, prefix="/api/v1", tags=["downloads"])
# app.include_router(health.router, prefix="/api/v1", tags=["health"])
# app.include_router(websocket.router, prefix="/ws", tags=["websocket"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )