# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Docker Development (Primary)
```bash
# Start all services (recommended for development)
docker compose up -d --build

# View logs for all services
docker compose logs -f

# View logs for specific service
docker compose logs -f app
docker compose logs -f celery-worker

# Stop all services
docker compose down

# Rebuild specific service
docker compose up -d --build app

# Access running container
docker compose exec app bash
```

### Database Management
```bash
# Run database migrations (inside container)
docker compose exec app alembic upgrade head

# Generate new migration
docker compose exec app alembic revision --autogenerate -m "migration description"

# Mark migration as applied without running
docker compose exec app alembic stamp head
```

### Code Quality
```bash
# Format code
black app/ tests/

# Sort imports
isort app/ tests/

# Lint code
flake8 app/ tests/

# Type checking
mypy app/

# Run all quality checks
black app/ tests/ && isort app/ tests/ && flake8 app/ tests/ && mypy app/
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_storage.py

# Run async tests
pytest -v tests/
```

## Architecture Overview

### Core Design Pattern
This is a **FastAPI-based microservice** with **async-first architecture** using the **Repository and Factory patterns**. The service follows a **clean architecture** approach with clear separation between layers.

### Key Architectural Decisions

**Environment Detection**: The application automatically detects runtime environment (`localhost` vs `aws`) and configures storage, database, and other services accordingly. This is handled in `app/core/config.py` with `Settings` and `AWSSettings` classes.

**Storage Abstraction**: Uses the **Factory Pattern** for storage backends. `get_storage_handler()` in `app/core/storage.py` returns either `LocalStorageHandler` or `S3StorageHandler` based on environment detection. All storage operations go through the abstract `StorageHandler` interface.

**Database Layer**: Implements **async SQLAlchemy 2.0** with proper connection pooling. The `app/core/database.py` module handles both development (SQLite) and production (PostgreSQL) databases seamlessly through URL detection.

**Task Processing**: Uses **Celery with Redis** for background job processing. The `app/tasks/download_tasks.py` contains placeholder task implementation that will be extended for actual video downloading.

**Application Lifecycle**: FastAPI uses a **lifespan manager** in `app/main.py` to handle startup/shutdown events, initializing database connections and storage handlers during application boot.

### Important Implementation Details

**Dual Database Support**: The application works with both SQLite (development) and PostgreSQL (production). Alembic migrations automatically convert async URLs to sync for migration execution.

**Health Monitoring**: Two health check endpoints exist:
- `/health` - Basic status
- `/health/detailed` - Full system health with database and storage validation

**Configuration Management**: Settings use **Pydantic Settings** with automatic environment variable loading. The `model_config = SettingsConfigDict(env_file=".env")` pattern is used instead of the deprecated `class Config`.

**Async Everywhere**: All database operations, file I/O, and HTTP requests use async/await. The storage layer uses `aiofiles` for async file operations and `asyncio.run_in_executor()` for blocking operations like S3 calls.

### Service Dependencies
- **PostgreSQL**: Primary database (port 5433 locally to avoid conflicts)
- **Redis**: Message broker and cache (port 6380 locally to avoid conflicts)
- **Celery Workers**: Background task processing
- **FFmpeg**: Video processing (installed in Docker container)

### Development Notes

**Port Conflicts**: Docker Compose uses non-standard ports (5433 for PostgreSQL, 6380 for Redis) to avoid conflicts with locally running services.

**Container Communication**: Services communicate using Docker network names (`db`, `redis`) rather than localhost.

**Migration Strategy**: Database tables are created both via application startup (SQLAlchemy) and Alembic migrations. Use `alembic stamp head` to sync migration state if tables already exist.

**Storage Testing**: The health check performs actual file write/read/delete operations to validate storage functionality, not just connection tests.

### Current Implementation Status
- **Phase 1 (Complete)**: Core infrastructure, database layer, storage abstraction, FastAPI application with health checks
- **Phase 2 (Next)**: YouTube downloader service with yt-dlp integration
- **Phase 3 (Future)**: API endpoints, WebSocket progress tracking

Run health checks at `http://localhost:8000/health/detailed` to verify all systems are operational.