# YouTube Video Download Service

> A cloud-native Python service for downloading YouTube videos with transcriptions and intelligent storage management.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 Overview

The YouTube Video Download Service is a production-ready, cloud-native application that automatically downloads YouTube videos along with their transcriptions. The service features intelligent environment detection and adapts storage behavior based on deployment context (local development vs AWS cloud).

### ✨ Key Features

- **🎥 Multi-format Video Downloads** - Support for MP4, WebM, MKV in various resolutions (720p-4K)
- **📝 Automatic Transcription Extraction** - Downloads captions in SRT, VTT, and TXT formats
- **🌩️ Smart Storage Management** - Auto-detects environment and routes to appropriate storage (Local/S3)
- **⚡ Async Processing** - FastAPI with Celery for background job processing
- **📊 Real-time Progress** - WebSocket support for live download status
- **🔐 Enterprise Security** - API key authentication with permission-based access control
- **🛡️ Rate Limiting** - Redis-based rate limiting with configurable limits
- **🔍 Health Monitoring** - Comprehensive health checks for all system components
- **🐳 Docker Ready** - Complete containerization for development and deployment

## 🏗️ Architecture

```
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

| Component | Role |
|-----------|------|
| **FastAPI App** | REST API server with WebSocket support for real-time updates |
| **Celery Worker** | Background task processor for video downloads |
| **yt-dlp Engine** | Core YouTube video extraction and download engine |
| **PostgreSQL** | Persistent storage for job metadata and download history |
| **Redis** | Message broker for Celery and caching layer |
| **Storage Handler** | Abstraction layer supporting Local filesystem and AWS S3 |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- FFmpeg (for video processing)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/andy/video-downloading-service.git
   cd video-downloading-service
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start with Docker (Recommended):**
   ```bash
   docker compose up -d --build
   ```

4. **Or run locally:**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run database migrations
   alembic upgrade head
   
   # Start services (requires PostgreSQL and Redis running)
   # Terminal 1: FastAPI app
   uvicorn app.main:app --reload --port 8000
   
   # Terminal 2: Celery worker
   celery -A app.tasks.download_tasks worker --loglevel=info
   ```

### 🔧 Configuration

Key environment variables in `.env`:

```env
# Environment
ENVIRONMENT=localhost  # or 'aws' for production
DEBUG=true

# Database (Docker uses these defaults)
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/youtube_service

# Redis (Docker uses these defaults)
REDIS_URL=redis://redis:6379/0

# AWS (for S3 storage when ENVIRONMENT=aws)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket
S3_CLOUDFRONT_DOMAIN=your-cloudfront-domain.amazonaws.com

# Storage (automatically detected based on environment)
DOWNLOAD_BASE_PATH=./downloads

# Security (API keys required for production use)
# Note: API keys are created via admin endpoints - see Authentication section
```

## 📚 API Documentation

Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔐 Authentication

The API uses **API key authentication** for secure access. All endpoints (except health checks) require a valid API key.

### Permission Levels
- **READ_ONLY**: Can access status, job listings, and video info endpoints
- **DOWNLOAD**: Can create download jobs and access all read operations  
- **ADMIN**: Can manage API keys and access all endpoints
- **FULL_ACCESS**: Complete access to all functionality

### API Key Usage

Include the API key in requests using any of these methods:

1. **Header (Recommended)**: `X-API-Key: your-api-key`
2. **Query Parameter**: `?api_key=your-api-key`
3. **Bearer Token**: `Authorization: Bearer your-api-key`

### Creating API Keys

API keys must be created through the admin endpoints or directly in the database:

```bash
# Create an API key via admin endpoint (requires existing admin key)
curl -X POST "http://localhost:8000/api/v1/admin/api-keys" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: admin-api-key" \
     -d '{
       "name": "My Application Key",
       "permission_level": "download",
       "description": "API key for my application"
     }'
```

### Key Endpoints

#### Public Endpoints (No Authentication)
- `GET /health` - Basic health check
- `GET /health/detailed` - Comprehensive system health
- `GET /api/v1/info?url={youtube_url}` - Extract video information without downloading

#### Protected Endpoints (Require Authentication)
- `POST /api/v1/download` - Start a new download job (DOWNLOAD permission required)
- `GET /api/v1/status/{job_id}` - Get job status and details (READ_ONLY permission required)
- `GET /api/v1/jobs` - List all download jobs with pagination (READ_ONLY permission required) 
- `POST /api/v1/retry/{job_id}` - Retry a failed download job (DOWNLOAD permission required)
- `WS /ws/progress/{job_id}?api_key={key}` - WebSocket for real-time progress updates

#### Admin Endpoints (ADMIN Permission Required)
- `POST /api/v1/admin/api-keys` - Create new API key
- `GET /api/v1/admin/api-keys` - List all API keys
- `GET /api/v1/admin/api-keys/{key_id}` - Get specific API key details
- `PUT /api/v1/admin/api-keys/{key_id}` - Update API key
- `DELETE /api/v1/admin/api-keys/{key_id}` - Delete API key

### Example Usage

```bash
# Extract video information (public endpoint)
curl "http://localhost:8000/api/v1/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Start a download with authentication
curl -X POST "http://localhost:8000/api/v1/download" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: your-api-key-here" \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "quality": "720p",
       "output_format": "mp4",
       "include_transcription": true,
       "subtitle_languages": ["en"]
     }'

# Check job status with API key
curl -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/status/{job_id}"

# List all jobs with filtering and authentication
curl -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/jobs?status=completed&page=1&per_page=10"

# Retry a failed job with authentication
curl -X POST \
     -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/retry/{job_id}"

# Connect to WebSocket with authentication
wscat -c "ws://localhost:8000/ws/progress/{job_id}?api_key=your-api-key-here"

# Admin: Create a new API key
curl -X POST "http://localhost:8000/api/v1/admin/api-keys" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: admin-api-key-here" \
     -d '{
       "name": "Development Key",
       "permission_level": "download",
       "description": "API key for development testing",
       "expires_at": "2024-12-31T23:59:59Z"
     }'
```

## 🛠️ Development

### Project Structure

```
video-downloading-service/
├── app/                      # Main application code
│   ├── api/                  # FastAPI routes and endpoints
│   ├── core/                 # Core configuration and utilities
│   ├── models/               # Database models
│   ├── services/             # Business logic services
│   └── tasks/                # Celery background tasks
├── docs/                     # Project documentation
├── scripts/                  # Utility scripts
├── tests/                    # Test suites
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── alembic/                  # Database migrations
├── docker-compose.yml        # Development environment
└── Dockerfile               # Container definition
```

### Running Tests

```bash
# Inside Docker container
docker compose exec app pytest tests/unit/
docker compose exec app pytest tests/integration/
docker compose exec app pytest --cov=app tests/

# Local development
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest --cov=app tests/
```

### Database Migrations

```bash
# Inside Docker container
docker compose exec app alembic upgrade head
docker compose exec app alembic revision --autogenerate -m "Description"

# Local development
alembic upgrade head
alembic revision --autogenerate -m "Description"
alembic downgrade -1
```

### 🔐 Security Development

The service includes comprehensive security features:

```bash
# Create initial admin API key (run once after setup)
docker compose exec app python -c "
import asyncio
from app.core.auth import APIKeyGenerator
from app.models.database import APIKey
from app.core.database import get_db_session
from datetime import datetime, timezone

async def create_admin_key():
    api_key = APIKeyGenerator.generate_api_key()
    api_key_hash = APIKeyGenerator.hash_api_key(api_key)
    print(f'Admin API Key: {api_key}')
    
    async with get_db_session() as session:
        admin_key = APIKey(
            name='Admin Key',
            key_hash=api_key_hash,
            permission_level='admin',
            is_active=True,
            description='Initial admin API key',
            usage_count=0,
            created_by='system',
            created_at=datetime.now(timezone.utc)
        )
        session.add(admin_key)
        await session.commit()
        print('Admin key created successfully')

asyncio.run(create_admin_key())
"

# Test authentication
curl -H "X-API-Key: your-admin-key-here" http://localhost:8000/api/v1/admin/api-keys
```

## 🔍 Monitoring & Health Checks

The service includes comprehensive health monitoring:

- **Basic Health**: `GET /health` - Simple status check
- **Detailed Health**: `GET /health/detailed` - Full system validation including:
  - Database connectivity and version
  - Storage handler read/write validation (Local/S3)
  - System environment detection

```bash
# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/health/detailed | jq .

# Test Celery worker
docker compose exec celery-worker celery -A app.tasks.download_tasks inspect ping
```

## 🚢 Deployment

### AWS Deployment

The service is designed for AWS deployment with:
- **ECS/Fargate** for container orchestration
- **RDS PostgreSQL** for database
- **ElastiCache Redis** for caching
- **S3** for video storage
- **CloudFront** for content delivery

### Environment Detection

The service automatically detects its environment:
- **Local Development**: Uses local filesystem storage
- **AWS Cloud**: Uses S3 with CloudFront integration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `python -m pytest`
5. Commit your changes: `git commit -m 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check the `docs/` directory
- **Issues**: Report bugs on [GitHub Issues](https://github.com/andy/video-downloading-service/issues)
- **Discussions**: Join the conversation in [GitHub Discussions](https://github.com/andy/video-downloading-service/discussions)

## 🚀 Roadmap

### Phase 1: ✅ Core Infrastructure (COMPLETED)
- FastAPI application with async support
- Database layer with SQLAlchemy
- Storage abstraction (Local/S3)
- Docker development environment

### Phase 2: ✅ Core Download Engine (COMPLETED)
- YouTube downloader implementation with yt-dlp
- Format selection and quality options
- Progress tracking and error handling
- WebSocket real-time updates
- Background job processing with Celery

### Phase 4: ✅ Authentication & Security (COMPLETED)
- API key authentication with permission levels
- Rate limiting with Redis
- Security middleware and headers
- Input validation and sanitization
- Admin API for key management

### Phase 5: 📊 Advanced Features (Next)
- Batch download capabilities
- Playlist support  
- Advanced metadata extraction
- User management and multi-tenancy
- Download scheduling and webhooks

See [TASKS.md](docs/TASKS.md) for detailed development progress.