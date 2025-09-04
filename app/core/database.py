from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.models.database import Base

logger = logging.getLogger(__name__)

# Global variables for database engine and session factory
engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def create_database_engine() -> AsyncEngine:
    """Create and configure the async database engine."""
    
    # Engine configuration based on database type
    engine_kwargs = {
        "echo": settings.debug,  # Log SQL queries in debug mode
        "future": True,  # Use SQLAlchemy 2.0 style
    }
    
    # SQLite-specific configuration
    if "sqlite" in settings.database_url:
        engine_kwargs.update({
            "poolclass": StaticPool,
            "connect_args": {
                "check_same_thread": False,
                "timeout": 20,
            },
        })
    # PostgreSQL-specific configuration
    else:
        engine_kwargs.update({
            "pool_size": 5,
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "max_overflow": 10,
        })
    
    return create_async_engine(settings.database_url, **engine_kwargs)


async def init_database() -> None:
    """Initialize the database connection and create tables."""
    global engine, async_session_factory
    
    try:
        # Create database engine
        engine = create_database_engine()
        
        # Create session factory
        async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create database tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_database() -> None:
    """Close the database connection."""
    global engine
    
    if engine:
        await engine.dispose()
        logger.info("Database connection closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session.
    
    Usage:
        async with get_db_session() as session:
            # Use session here
            result = await session.execute(...)
    """
    if not async_session_factory:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to get a database session.
    
    Usage in FastAPI endpoints:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            # Use db session here
    """
    async with get_db_session() as session:
        yield session


async def check_database_connection() -> bool:
    """
    Check if the database connection is healthy.
    
    Returns:
        bool: True if connection is healthy, False otherwise
    """
    if not engine:
        return False
    
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


class DatabaseManager:
    """Database manager class for handling database operations."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
    
    async def initialize(self) -> None:
        """Initialize the database manager."""
        await init_database()
        self.engine = engine
        self.session_factory = async_session_factory
    
    async def close(self) -> None:
        """Close the database manager."""
        await close_database()
        self.engine = None
        self.session_factory = None
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session from the manager."""
        async with get_db_session() as session:
            yield session
    
    async def health_check(self) -> dict:
        """Perform a comprehensive database health check."""
        try:
            is_connected = await check_database_connection()
            
            if is_connected:
                # Get additional database info
                async with get_db_session() as session:
                    result = await session.execute(text("SELECT version()"))
                    db_version = result.scalar_one_or_none()
                
                return {
                    "status": "healthy",
                    "connected": True,
                    "database_url": settings.database_url.split("@")[-1],  # Hide credentials
                    "version": db_version,
                }
            else:
                return {
                    "status": "unhealthy",
                    "connected": False,
                    "error": "Could not connect to database"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


# Global database manager instance
db_manager = DatabaseManager()