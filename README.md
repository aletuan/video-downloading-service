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
   docker-compose up -d
   ```

4. **Or run locally:**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   
   # Run database migrations
   alembic upgrade head
   
   # Start services
   uvicorn app.main:app --reload --port 8000
   celery -A app.tasks.download_tasks worker --loglevel=info
   ```

### 🔧 Configuration

Key environment variables in `.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/youtube_service

# Redis
REDIS_URL=redis://localhost:6380/0

# AWS (for S3 storage)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket

# Storage
STORAGE_TYPE=local  # or 's3'
LOCAL_STORAGE_PATH=./downloads
```

## 📚 API Documentation

Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

- `POST /api/v1/download` - Start a new download job
- `GET /api/v1/jobs/{job_id}` - Get job status and details
- `GET /api/v1/jobs` - List all download jobs
- `GET /health` - Basic health check
- `GET /health/detailed` - Comprehensive system health

### Example Usage

```bash
# Start a download
curl -X POST "http://localhost:8000/api/v1/download" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'

# Check job status
curl "http://localhost:8000/api/v1/jobs/{job_id}"
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

### 🧪 Running Tests

The project includes a comprehensive testing framework with automatic Docker integration for consistent testing environments.

#### Quick Start

```bash
# Automatic environment detection - runs in Docker if available
./scripts/test.sh

# Run unit tests with HTML coverage report
./scripts/test.sh unit --html

# Run fast tests in parallel
./scripts/test.sh fast --parallel --docker
```

#### 🐳 Docker Testing (Recommended)

The testing framework automatically detects and uses Docker for consistent, isolated testing:

```bash
# One-time setup - configures Docker test environment
python scripts/setup_test_env.py

# Run tests with automatic Docker detection
python scripts/test_runner.py --unit --html

# Force Docker execution with environment setup
python scripts/test_runner.py --docker --setup

# Run in development mode with live code reloading
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
docker-compose exec app python -m pytest tests/unit --cov=app
```

#### 🔧 Local Testing

If Docker is not available, tests can run in your local Python environment:

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run tests locally
python -m pytest tests/unit/ --cov=app --cov-report=html
python scripts/test_runner.py --no-docker
```

#### 📊 Test Categories & Coverage

| Test Type | Command | Description |
|-----------|---------|-------------|
| **Unit Tests** | `./scripts/test.sh unit` | Fast, isolated component tests |
| **Integration Tests** | `./scripts/test.sh integration` | Service integration testing |
| **Fast Tests** | `./scripts/test.sh fast` | Excludes slow/external tests |
| **All Tests** | `./scripts/test.sh all` | Complete test suite |

**Coverage Requirements**: 85% minimum coverage with detailed HTML reports

#### 🛠️ Development Workflow

```bash
# Setup development environment
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run tests with file watching (reruns on changes)
python scripts/test_runner.py --watch

# Generate coverage report only
./scripts/test.sh coverage

# Clean coverage data
./scripts/test.sh clean

# Verify environment setup
python scripts/setup_test_env.py --verify-only
```

#### 📈 Coverage Reports

After running tests with coverage, reports are available at:
- **HTML Report**: `./htmlcov/index.html` (interactive, detailed)  
- **XML Report**: `./coverage.xml` (CI/CD integration)
- **Terminal**: Immediate coverage summary with missing lines

#### 🔍 Troubleshooting Tests

```bash
# Check test environment status
python scripts/setup_test_env.py --verify-only

# Reset Docker test environment  
python scripts/setup_test_env.py --clean
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Run specific test file
python scripts/test_runner.py tests/unit/models/test_download.py --docker

# Debug test failures
python scripts/test_runner.py --verbose --stop-on-fail --docker
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 🔍 Monitoring & Health Checks

The service includes comprehensive health monitoring:

- **Basic Health**: `GET /health` - Simple status check
- **Detailed Health**: `GET /health/detailed` - Full system validation including:
  - Database connectivity
  - Redis connectivity  
  - Storage handler status
  - Celery worker status

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

### Phase 2: 🎯 Core Download Engine (Next)
- YouTube downloader implementation
- Format selection and quality options
- Progress tracking and error handling

### Phase 3: 📊 Advanced Features
- Batch download capabilities
- Playlist support
- Advanced metadata extraction

See [TASKS.md](docs/TASKS.md) for detailed development progress.