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
```

## 📚 API Documentation

Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

- `POST /api/v1/download` - Start a new download job
- `GET /api/v1/status/{job_id}` - Get job status and details
- `GET /api/v1/jobs` - List all download jobs with pagination
- `GET /api/v1/info?url={youtube_url}` - Extract video information without downloading
- `POST /api/v1/retry/{job_id}` - Retry a failed download job
- `GET /health` - Basic health check
- `GET /health/detailed` - Comprehensive system health
- `WS /ws/progress/{job_id}` - WebSocket for real-time progress updates

### Example Usage

```bash
# Extract video information
curl "http://localhost:8000/api/v1/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Start a download with options
curl -X POST "http://localhost:8000/api/v1/download" \
     -H "Content-Type: application/json" \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "quality": "720p",
       "output_format": "mp4",
       "include_transcription": true,
       "subtitle_languages": ["en"]
     }'

# Check job status
curl "http://localhost:8000/api/v1/status/{job_id}"

# List all jobs with filtering
curl "http://localhost:8000/api/v1/jobs?status=completed&page=1&per_page=10"

# Retry a failed job
curl -X POST "http://localhost:8000/api/v1/retry/{job_id}"
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

### Phase 3: 📊 Advanced Features (Next)
- Batch download capabilities
- Playlist support  
- Advanced metadata extraction
- User management and authentication
- Download scheduling and webhooks

See [TASKS.md](docs/TASKS.md) for detailed development progress.