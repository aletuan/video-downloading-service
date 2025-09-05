# YouTube Video Download Service

> A cloud-native Python service for downloading YouTube videos with transcriptions and intelligent storage management.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

The YouTube Video Download Service is a production-ready, cloud-native application that automatically downloads YouTube videos along with their transcriptions. The service features intelligent environment detection and adapts storage behavior based on deployment context (local development vs AWS cloud).

### Key Features

- **Multi-format Video Downloads** - Support for MP4, WebM, MKV in various resolutions (720p-4K)
- **Automatic Transcription Extraction** - Downloads captions in SRT, VTT, and TXT formats
- **Smart Storage Management** - Auto-detects environment and routes to appropriate storage (Local/S3)
- **Async Processing** - FastAPI with Celery for background job processing
- **Real-time Progress** - WebSocket support for live download status
- **Enterprise Security** - API key authentication with permission-based access control
- **Rate Limiting** - Redis-based rate limiting with configurable limits
- **Health Monitoring** - Comprehensive health checks for all system components
- **Docker Ready** - Complete containerization for development and deployment

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

For detailed development setup, see [Development Guide](docs/DEVELOPMENT.md).

## Usage Example

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
```

## Documentation

- **[API Documentation](docs/API.md)** - Complete API reference, authentication, and examples
- **[Development Guide](docs/DEVELOPMENT.md)** - Setup, testing, and development workflow
- **[Deployment Guide](docs/DEPLOYMENT.md)** - AWS deployment and production setup
- **[Architecture](docs/ARCHITECTURE.md)** - Technical architecture and design patterns

### Interactive API Docs
Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `python -m pytest`
5. Commit your changes: `git commit -m 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

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
- Background job processing with Celery

### Phase 3: ✅ API Layer (COMPLETED)
- Complete REST API with 6 endpoints
- Real-time WebSocket progress updates
- Request/response validation with Pydantic
- API documentation with OpenAPI/Swagger

### Phase 4: ✅ Authentication & Security (COMPLETED)
- API key authentication with permission levels
- Rate limiting with Redis
- Security middleware and headers
- Input validation and sanitization
- Admin API for key management

### Phase 5: ✅ Environment Configuration (COMPLETED)
- Local development setup with Docker
- Database migrations and health checks
- Production-ready containerization

### Phase 6: 🎯 AWS Production Setup (Next)
- ECS/Fargate deployment with Terraform
- RDS PostgreSQL and ElastiCache Redis
- S3 storage with CloudFront CDN
- Load balancer and auto-scaling

### Future Phases
- **Phase 7**: Monitoring & observability
- **Phase 8**: Testing & quality assurance  
- **Phase 9**: Documentation & deployment automation
- **Phase 10**: Performance optimization & scalability

### Advanced Features (Roadmap)
- Batch download capabilities
- Playlist support  
- Advanced metadata extraction
- User management and multi-tenancy
- Download scheduling and webhooks

See [TASKS.md](docs/TASKS.md) for detailed development progress and task breakdown.