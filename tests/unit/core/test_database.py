import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy import Engine

from app.core.database import (
    get_sync_database_url,
    create_database_engine,
    create_sync_database_engine,
    DatabaseManager
)


class TestDatabaseURL:
    """Test cases for database URL conversion."""

    def test_get_sync_database_url_sqlite(self):
        """Test conversion of async SQLite URL to sync."""
        async_url = "sqlite+aiosqlite:///./test.db"
        sync_url = get_sync_database_url(async_url)
        assert sync_url == "sqlite:///./test.db"

    def test_get_sync_database_url_postgresql(self):
        """Test conversion of async PostgreSQL URL to sync."""
        async_url = "postgresql+asyncpg://user:pass@localhost/db"
        sync_url = get_sync_database_url(async_url)
        assert sync_url == "postgresql+psycopg2://user:pass@localhost/db"

    def test_get_sync_database_url_no_change(self):
        """Test that other URLs remain unchanged."""
        other_url = "mysql://user:pass@localhost/db"
        sync_url = get_sync_database_url(other_url)
        assert sync_url == other_url


class TestDatabaseEngineCreation:
    """Test cases for database engine creation."""

    @patch('app.core.database.create_async_engine')
    @patch('app.core.database.settings')
    def test_create_database_engine_sqlite(self, mock_settings, mock_create_engine):
        """Test creation of async database engine for SQLite."""
        mock_settings.database_url = "sqlite+aiosqlite:///./test.db"
        mock_settings.debug = True
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        result = create_database_engine()

        mock_create_engine.assert_called_once()
        args, kwargs = mock_create_engine.call_args
        assert args[0] == "sqlite+aiosqlite:///./test.db"
        assert kwargs["echo"] is True
        assert kwargs["future"] is True
        assert "poolclass" in kwargs
        assert "connect_args" in kwargs
        assert result == mock_engine

    @patch('app.core.database.create_async_engine')
    @patch('app.core.database.settings')
    def test_create_database_engine_postgresql(self, mock_settings, mock_create_engine):
        """Test creation of async database engine for PostgreSQL."""
        mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
        mock_settings.debug = False
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        result = create_database_engine()

        mock_create_engine.assert_called_once()
        args, kwargs = mock_create_engine.call_args
        assert args[0] == "postgresql+asyncpg://user:pass@localhost/db"
        assert kwargs["echo"] is False
        assert kwargs["future"] is True
        assert kwargs["pool_size"] == 5
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_recycle"] == 3600
        assert kwargs["max_overflow"] == 10
        assert result == mock_engine

    @patch('app.core.database.create_engine')
    @patch('app.core.database.settings')
    def test_create_sync_database_engine_sqlite(self, mock_settings, mock_create_engine):
        """Test creation of sync database engine for SQLite."""
        mock_settings.database_url = "sqlite+aiosqlite:///./test.db"
        mock_settings.debug = True
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        result = create_sync_database_engine()

        mock_create_engine.assert_called_once()
        args, kwargs = mock_create_engine.call_args
        assert args[0] == "sqlite:///./test.db"
        assert kwargs["echo"] is True
        assert kwargs["future"] is True
        assert "poolclass" in kwargs
        assert "connect_args" in kwargs
        assert result == mock_engine

    @patch('app.core.database.create_engine')
    @patch('app.core.database.settings')
    def test_create_sync_database_engine_postgresql(self, mock_settings, mock_create_engine):
        """Test creation of sync database engine for PostgreSQL."""
        mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
        mock_settings.debug = False
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        result = create_sync_database_engine()

        mock_create_engine.assert_called_once()
        args, kwargs = mock_create_engine.call_args
        assert args[0] == "postgresql+psycopg2://user:pass@localhost/db"
        assert kwargs["echo"] is False
        assert kwargs["future"] is True
        assert "poolclass" in kwargs
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_recycle"] == 3600
        assert result == mock_engine


@pytest.mark.asyncio
class TestDatabaseManager:
    """Test cases for DatabaseManager class."""

    async def test_database_manager_init(self):
        """Test DatabaseManager initialization."""
        manager = DatabaseManager()
        assert manager.engine is None
        assert manager.session_factory is None

    @patch('app.core.database.init_database')
    @patch('app.core.database.engine', new_callable=MagicMock)
    @patch('app.core.database.async_session_factory', new_callable=MagicMock)
    async def test_database_manager_initialize(self, mock_session_factory, mock_engine, mock_init):
        """Test DatabaseManager initialize method."""
        manager = DatabaseManager()
        
        await manager.initialize()
        
        mock_init.assert_called_once()
        assert manager.engine == mock_engine
        assert manager.session_factory == mock_session_factory

    @patch('app.core.database.close_database')
    async def test_database_manager_close(self, mock_close):
        """Test DatabaseManager close method."""
        manager = DatabaseManager()
        manager.engine = MagicMock()
        manager.session_factory = MagicMock()
        
        await manager.close()
        
        mock_close.assert_called_once()
        assert manager.engine is None
        assert manager.session_factory is None

    @patch('app.core.database.check_database_connection')
    @patch('app.core.database.get_db_session')
    @patch('app.core.database.settings')
    async def test_database_manager_health_check_healthy(self, mock_settings, mock_get_session, mock_check):
        """Test DatabaseManager health check when database is healthy."""
        mock_settings.database_url = "postgresql://user:pass@localhost:5432/test"
        mock_check.return_value = True
        
        # Mock session and result
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "PostgreSQL 15.0"
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        manager = DatabaseManager()
        health = await manager.health_check()
        
        assert health["status"] == "healthy"
        assert health["connected"] is True
        assert "localhost:5432/test" in health["database_url"]
        assert health["version"] == "PostgreSQL 15.0"

    @patch('app.core.database.check_database_connection')
    async def test_database_manager_health_check_unhealthy(self, mock_check):
        """Test DatabaseManager health check when database is unhealthy."""
        mock_check.return_value = False
        
        manager = DatabaseManager()
        health = await manager.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["connected"] is False
        assert "error" in health

    @patch('app.core.database.check_database_connection')
    async def test_database_manager_health_check_exception(self, mock_check):
        """Test DatabaseManager health check when exception occurs."""
        mock_check.side_effect = Exception("Connection failed")
        
        manager = DatabaseManager()
        health = await manager.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["connected"] is False
        assert health["error"] == "Connection failed"