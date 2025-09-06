# Architecture Documentation

## System Architecture

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │────│  Celery Worker  │────│  yt-dlp Engine  │
│  (REST + WS)    │    │ (Background)    │    │  (Downloader)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │      Redis      │    │ Storage Handler │
│   (Metadata)    │    │  (Job Queue)    │    │  (Local/S3)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Component Overview

| Component | Role |
|-----------|------|
| **FastAPI App** | REST API server with WebSocket support for real-time updates |
| **Celery Worker** | Background task processor for video downloads |
| **yt-dlp Engine** | Core YouTube video extraction and download engine |
| **PostgreSQL** | Persistent storage for job metadata and download history |
| **Redis** | Message broker for Celery and caching layer |
| **Storage Handler** | Abstraction layer supporting Local filesystem and AWS S3 |

## Design Patterns

### Core Design Pattern

This is a **FastAPI-based microservice** with **async-first architecture** using the **Repository and Factory patterns**. The service follows a **clean architecture** approach with clear separation between layers.

### Key Architectural Decisions

**Environment Detection**: The application automatically detects runtime environment (`localhost` vs `aws`) and configures storage, database, and other services accordingly. This is handled in `app/core/config.py` with `Settings` and `AWSSettings` classes.

**Storage Abstraction**: Uses the **Factory Pattern** for storage backends. `get_storage_handler()` in `app/core/storage.py` returns either `LocalStorageHandler` or `S3StorageHandler` based on environment detection. All storage operations go through the abstract `StorageHandler` interface.

**Database Layer**: Implements **async SQLAlchemy 2.0** with proper connection pooling. The `app/core/database.py` module handles both development (SQLite) and production (PostgreSQL) databases seamlessly through URL detection.

**Task Processing**: Uses **Celery with Redis** for background job processing. The `app/tasks/download_tasks.py` contains the complete `process_download` task that handles YouTube video downloads using yt-dlp with progress tracking, error handling, and database status updates.

**Application Lifecycle**: FastAPI uses a **lifespan manager** in `app/main.py` to handle startup/shutdown events, initializing database connections and storage handlers during application boot.

## Implementation Details

### Dual Database Support

The application works with both SQLite (development) and PostgreSQL (production). Alembic migrations automatically convert async URLs to sync for migration execution.

### Health Monitoring

Multiple health check endpoints exist:

- `/health` - Basic status
- `/health/detailed` - Full system health with database and storage validation
- Celery worker health checks via `health_check` task

### Configuration Management

Settings use **Pydantic Settings** with automatic environment variable loading. The `model_config = SettingsConfigDict(env_file=".env")` pattern is used instead of the deprecated `class Config`.

### Async Everywhere

All database operations, file I/O, and HTTP requests use async/await. The storage layer uses `aiofiles` for async file operations and `asyncio.run_in_executor()` for blocking operations like S3 calls. Celery tasks use `asyncio.run()` to execute async download operations in background workers.

### API Structure

The FastAPI application uses a modular router-based structure:

- `app/routers/downloads.py` - Download management endpoints
- `app/routers/admin.py` - API key management endpoints  
- `app/routers/bootstrap.py` - Initial setup endpoints
- `app/routers/websocket.py` - WebSocket connections with `WebSocketManager`

### Authentication & Authorization

Comprehensive API key-based authentication system with:

- **Permission Levels**: READ_ONLY, DOWNLOAD, ADMIN, FULL_ACCESS
- **Rate Limiting**: Redis-based rate limiting per API key
- **Bootstrap Setup**: One-time admin key creation for initial setup
- **Secure Storage**: API keys hashed with bcrypt for database storage

## Service Dependencies

- **PostgreSQL**: Primary database (port 5433 locally to avoid conflicts)
- **Redis**: Message broker and cache (port 6380 locally to avoid conflicts)
- **Celery Workers**: Background task processing
- **FFmpeg**: Video processing (installed in Docker container)

## Development Notes

### Port Conflicts

Docker Compose uses non-standard ports (5433 for PostgreSQL, 6380 for Redis) to avoid conflicts with locally running services.

### Container Communication

Services communicate using Docker network names (`db`, `redis`) rather than localhost.

### Migration Strategy

Database tables are created both via application startup (SQLAlchemy) and Alembic migrations. Use `alembic stamp head` to sync migration state if tables already exist.

### Storage Testing

The health check performs actual file write/read/delete operations to validate storage functionality, not just connection tests.

Run health checks at `http://localhost:8000/health/detailed` (local) or your ALB endpoint (AWS) to verify all systems are operational.

## Workflow Sequence Diagrams

### 1. Video Download Workflow

```text
┌──────┐     ┌─────────┐     ┌──────────┐     ┌──────┐     ┌──────────┐     ┌─────────┐     ┌────────┐     ┌─────────┐
│Client│     │Downloads│     │ Database │     │Celery│     │YouTubeDL │     │ Storage │     │ yt-dlp │     │WSManager│
│      │     │ Router  │     │          │     │ Task │     │ Service  │     │Handler  │     │        │     │         │
└──┬───┘     └────┬────┘     └────┬─────┘     └──┬───┘     └────┬─────┘     └────┬────┘     └───┬────┘     └────┬────┘
   │              │                │              │              │              │              │               │
   │POST /download│                │              │              │              │              │               │
   │+ API-Key     │                │              │              │              │              │               │
   │─────────────>│                │              │              │              │              │               │
   │              │Validate API key│              │              │              │              │               │
   │              │+ permissions   │              │              │              │              │               │
   │              │Create job      │              │              │              │              │               │
   │              │───────────────>│              │              │              │              │               │
   │              │        job_id  │              │              │              │              │               │
   │              │<───────────────│              │              │              │              │               │
   │              │Queue process_  │              │              │              │              │               │
   │              │download task   │              │              │              │              │               │
   │              │───────────────────────────────>│              │              │              │               │
   │202 {job_id}  │                │              │              │              │              │               │
   │<─────────────│                │              │              │              │              │               │
   │              │                │              │              │              │              │               │
   │Connect /ws/progress/{job_id}?api_key=...     │              │              │              │               │
   │──────────────────────────────────────────────────────────────────────────────────────────────────────────────>│
   │              │                │              │              │              │              │               │
   │Connected     │                │              │              │              │              │               │
   │<──────────────────────────────────────────────────────────────────────────────────────────────────────────────│
   │              │                │              │Start async   │              │              │               │
   │              │                │              │download()    │              │              │               │
   │              │                │              │─────────────>│              │              │               │
   │              │                │              │              │Update status │              │               │
   │              │                │              │              │'processing'  │              │               │
   │              │                │              │              │─────────────>│              │               │
   │              │                │              │              │Extract info  │              │               │
   │              │                │              │              │─────────────────────────────>│               │
   │              │                │              │              │   Video info │              │               │
   │              │                │              │              │<─────────────────────────────│               │
   │              │                │              │              │Download with │              │               │
   │              │                │              │              │progress hook │              │               │
   │              │                │              │              │─────────────────────────────>│               │
   │              │                │              │              │Progress 45%  │              │               │
   │              │                │              │              │<─────────────────────────────│               │
   │              │                │              │              │Broadcast via │              │               │
   │              │                │              │              │callback      │              │               │
   │              │                │              │              │──────────────────────────────────────────────>│
   │Progress 45%  │                │              │              │              │              │               │
   │<──────────────────────────────────────────────────────────────────────────────────────────────────────────────│
   │              │                │              │              │Store files   │              │               │
   │              │                │              │              │─────────────>│              │               │
   │              │                │              │              │  File paths  │              │               │
   │              │                │              │              │<─────────────│              │               │
   │              │                │              │              │Update status │              │               │
   │              │                │              │              │'completed'   │              │               │
   │              │                │              │              │─────────────>│              │               │
   │              │                │              │              │Broadcast done│              │               │
   │              │                │              │              │──────────────────────────────────────────────>│
   │Completed     │                │              │              │              │              │               │
   │<──────────────────────────────────────────────────────────────────────────────────────────────────────────────│
```

### 2. Authentication Flow

```text
┌──────┐     ┌─────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐     ┌───────┐
│Client│     │ Router  │     │Auth Deps │     │APIKey Gen │     │ Database │     │ Redis │
│      │     │Endpoint │     │Functions │     │& Validator│     │          │     │       │
└──┬───┘     └────┬────┘     └────┬─────┘     └─────┬─────┘     └────┬─────┘     └───┬───┘
   │              │                │                 │               │               │
   │Request with  │                │                 │               │               │
   │X-API-Key hdr │                │                 │               │               │
   │─────────────>│                │                 │               │               │
   │              │Extract API key │                 │               │               │
   │              │from header/    │                 │               │               │
   │              │query/bearer    │                 │               │               │
   │              │───────────────>│                 │               │               │
   │              │                │Hash key & query│               │               │
   │              │                │database for key│               │               │
   │              │                │────────────────────────────────>│               │
   │              │                │                 │Key record     │               │
   │              │                │<────────────────────────────────│               │
   │              │                │                 │               │               │
   │              │                │    ┌─[Key Not Found]─────────────┐              │
   │              │                │    │                             │              │
   │              │401 Unauthorized│    │                             │              │
   │              │<───────────────│<───┘                             │              │
   │401 Invalid   │                │                                  │              │
   │<─────────────│                │                                  │              │
   │              │                │                                  │              │
   │              │                │    ┌─[Key Found]─────────────────┐              │
   │              │                │    │                             │              │
   │              │                │    │Check rate limit             │              │
   │              │                │    │─────────────────────────────────────────────>│
   │              │                │    │                             │Rate status   │
   │              │                │    │                             │<─────────────│
   │              │                │    │                             │              │
   │              │                │    │ ┌─[Rate Exceeded]────────┐  │              │
   │              │                │    │ │                        │  │              │
   │              │429 Rate Limited│    │ │                        │  │              │
   │              │<───────────────│<───│─┘                        │  │              │
   │429 Too Many  │                │    │                          │  │              │
   │<─────────────│                │    │                          │  │              │
   │              │                │    │                          │  │              │
   │              │                │    │ ┌─[Within Limits]──────┐ │  │              │
   │              │                │    │ │                      │ │  │              │
   │              │                │    │ │Check permissions     │ │  │              │
   │              │                │    │ │for endpoint          │ │  │              │
   │              │                │    │ │                      │ │  │              │
   │              │                │    │ │ ┌─[No Permission]──┐ │ │  │              │
   │              │                │    │ │ │                  │ │ │  │              │
   │              │403 Forbidden   │    │ │ │                  │ │ │  │              │
   │              │<───────────────│<───│─│─┘                  │ │ │  │              │
   │403 Forbidden │                │    │ │                    │ │ │  │              │
   │<─────────────│                │    │ │                    │ │ │  │              │
   │              │                │    │ │                    │ │ │  │              │
   │              │                │    │ │ ┌─[Has Permission]─┐ │ │ │  │              │
   │              │                │    │ │ │                 │ │ │ │  │              │
   │              │                │    │ │ │Increment usage  │ │ │ │  │              │
   │              │                │    │ │ │─────────────────────┐ │ │  │              │
   │              │Authorized with │    │ │ │                 │ │ │ │  │              │
   │              │permissions     │    │ │ │                 │ │ │ │  │              │
   │              │<───────────────│<───│─│─┘                 │ │ │ │  │              │
   │              │                │    │ │                   │ │ │ │  │              │
   │              │Process request │    │ │                   │ │ │ │  │              │
   │              │with API key    │    │ │                   │ │ │ │  │              │
   │              │metadata        │    │ │                   │ │ │ │  │              │
   │200 Success   │                │    │ │                   │ │ │ │  │              │
   │<─────────────│                │    │ │                   │ │ │ │  │              │
   │              │                │    │ │                   │ │ │ │  │              │
   │              │                └────│─│───────────────────┘ │ │ │  │              │
   │              │                     │ │                     │ │ │  │              │
   │              │                     │ └─────────────────────┘ │ │  │              │
   │              │                     │                         │ │  │              │
   │              │                     └─────────────────────────┘ │  │              │
   │              │                                                 │  │              │
   │              │                                                 └──┘              │
   │              │                                                                    │
   │              │                                                                    │
```

### 3. Health Check Flow

```text
┌──────┐     ┌─────────┐     ┌──────────┐     ┌─────────┐     ┌───────┐
│Client│     │ FastAPI │     │ Database │     │ Storage │     │ Redis │
└──┬───┘     └────┬────┘     └────┬─────┘     └────┬────┘     └───┬───┘
   │              │                │                │               │
   │GET /health   │                │                │               │
   │─────────────>│                │                │               │
   │              │                │                │               │
   │              ├─Test connection─>               │               │
   │              ├─Test read/write──────────────────>              │
   │              ├─Test connection────────────────────────────────>│
   │              │                │                │               │
   │              │<──Status + ver──│                │              │
   │              │<──Storage status─────────────────┘              │
   │              │<──Redis status──────────────────────────────────┘
   │              │                │                │               │
   │              │Aggregate health│                │               │
   │              │───────────────>│                │               │
   │Health report │                │                │               │
   │<─────────────│                │                │               │
```

### 4. WebSocket Progress Tracking

```text
┌──────┐     ┌───────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐     ┌──────┐
│Client│     │WebSocket  │     │WSManager  │     │ Database │     │YouTubeDL  │     │Celery│
│      │     │Router     │     │           │     │          │     │Service    │     │Task  │
└──┬───┘     └─────┬─────┘     └─────┬─────┘     └────┬─────┘     └────┬─────┘     └──┬───┘
   │               │                 │                │                │            │
   │Connect /ws/progress/{job_id}    │                │                │            │
   │?api_key=xxx   │                 │                │                │            │
   │──────────────>│                 │                │                │            │
   │               │Extract & validate                │                │            │
   │               │API key          │                │                │            │
   │               │────────────────>│                │                │            │
   │               │                 │Validate job_id │                │            │
   │               │                 │exists & access │                │            │
   │               │                 │───────────────>│                │            │
   │               │                 │     Valid      │                │            │
   │               │                 │<───────────────│                │            │
   │               │    Accept       │                │                │            │
   │               │<────────────────│                │                │            │
   │Connected      │                 │                │                │            │
   │<──────────────│                 │                │                │            │
   │               │                 │Register WS     │                │            │
   │               │                 │for job_id      │                │            │
   │               │                 │                │                │            │
   │               │Send initial     │Get current     │                │            │
   │               │job status       │job status      │                │            │
   │               │<────────────────│───────────────>│                │            │
   │Initial status │                 │    Status      │                │            │
   │<──────────────│                 │<───────────────│                │            │
   │               │                 │                │                │            │
   │               │                 │                │                │Progress    │
   │               │                 │                │                │callback    │
   │               │                 │                │                │<───────────│
   │               │                 │                │                │Broadcast   │
   │               │                 │                │                │to WS       │
   │               │                 │                │                │───────────>│
   │               │                 │Send progress   │                │            │
   │               │                 │to job          │                │            │
   │               │                 │connections     │                │            │
   │               │<────────────────│                │                │            │
   │Progress 45%   │                 │                │                │            │
   │<──────────────│                 │                │                │            │
   │               │                 │                │                │Status      │
   │               │                 │                │                │update      │
   │               │                 │                │                │<───────────│
   │               │                 │                │Update job      │            │
   │               │                 │                │status in DB    │            │
   │               │                 │                │<───────────────│            │
   │               │                 │Broadcast       │                │            │
   │               │                 │status change   │                │            │
   │               │<────────────────│                │                │            │
   │Status update  │                 │                │                │            │
   │<──────────────│                 │                │                │            │
   │               │                 │                │                │            │
   │Disconnect     │                 │                │                │            │
   │──────────────>│                 │                │                │            │
   │               │Unregister WS    │                │                │            │
   │               │────────────────>│                │                │            │
   │               │   Cleanup       │                │                │            │
   │               │<────────────────│                │                │            │
   │Disconnected   │                 │                │                │            │
   │<──────────────│                 │                │                │            │
```
