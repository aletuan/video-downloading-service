# YouTube Video Download Service - Production Description (Python)

## Overview

The YouTube Video Download Service is a Python-based cloud-native application designed to download YouTube videos along with their transcriptions (when available) and store them in the appropriate storage system based on the deployment environment. The service automatically detects its runtime environment and adapts storage behavior accordingly.

## Technology Stack

**Core Framework:**
- **FastAPI** - Modern, fast web framework with automatic API documentation
- **yt-dlp** - Advanced YouTube video downloader and extractor
- **boto3** - AWS SDK for Python
- **SQLAlchemy** - Database ORM with async support
- **Celery** - Distributed task queue for background processing
- **Redis** - Message broker and caching layer
- **Pydantic** - Data validation and serialization

**Supporting Libraries:**
- **ffmpeg-python** - Video processing and format conversion
- **pysrt / webvtt-py** - Subtitle and transcription processing
- **aiofiles** - Async file operations
- **httpx** - Async HTTP client
- **python-multipart** - File upload support

## Service Capabilities

**Core Functionality:**
- Download YouTube videos using yt-dlp in multiple quality formats
- Extract and download video transcriptions when available
- Automatic environment detection (localhost vs AWS)
- Intelligent storage routing based on deployment context
- Metadata extraction and preservation
- Background job processing with Celery
- Real-time progress tracking via WebSockets

**Supported Video Formats:**
- MP4 (multiple resolutions: 720p, 1080p, 1440p, 2160p)
- WebM, MKV
- Audio-only formats (MP3, M4A, WAV)
- Format conversion using FFmpeg

**Transcription Support:**
- Auto-generated captions via yt-dlp
- Manual/professional captions
- Multiple language support
- SRT, VTT, and TXT format output
- Subtitle translation capabilities

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           YouTube Download Service                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌──────────────┐
│   Client     │───▶│   FastAPI   │───▶│  Download API   │───▶│    Celery    │
│ (Browser/API)│    │ Application │    │   Controller    │    │   Worker     │
└──────────────┘    └─────────────┘    └─────────────────┘    └──────────────┘
        │                   │                    │                    │
        │                   ▼                    │                    ▼
        │            ┌─────────────┐             │           ┌──────────────┐
        │            │    CORS     │             │           │  yt-dlp      │
        │            │ Middleware  │             │           │  Engine      │
        │            └─────────────┘             │           └──────────────┘
        │                   │                    │                    │
        ▼                   ▼                    ▼                    ▼
┌──────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌──────────────┐
│  WebSocket   │    │   Health    │    │    Database     │    │   Storage    │
│  Progress    │    │   Checks    │    │  (PostgreSQL)   │    │   Handler    │
│  Tracking    │    └─────────────┘    └─────────────────┘    └──────────────┘
└──────────────┘            │                    │                    │
        │                   ▼                    │                    ▼
        │            ┌─────────────┐             │           ┌──────────────┐
        │            │    Redis    │◀────────────┘           │   Local FS   │
        │            │   Message   │                         │      OR      │
        │            │   Broker    │                         │   AWS S3     │
        └────────────┤             │                         └──────────────┘
                     └─────────────┘

Legend:
───▶  HTTP/API Requests
│     Component Dependencies
◀──   Data Flow
```

### Component Architecture Table

| Component | Description | Role |
|-----------|-------------|------|
| **Client (Browser/API)** | External users and API consumers | Initiates download requests, receives progress updates via WebSocket |
| **FastAPI Application** | Main web framework and API gateway | Routes requests, handles authentication, serves API documentation |
| **CORS Middleware** | Cross-Origin Resource Sharing handler | Manages browser security policies for web client access |
| **Download API Controller** | REST API endpoints for downloads | Validates requests, queues jobs, returns job status and metadata |
| **Health Checks** | System monitoring endpoints | Monitors database, storage, and service health status |
| **WebSocket Progress Tracking** | Real-time communication channel | Streams live download progress updates to connected clients |
| **Celery Worker** | Distributed background task processor | Executes video download tasks asynchronously in separate processes |
| **yt-dlp Engine** | YouTube video extraction library | Downloads videos, extracts metadata, handles various video formats |
| **Database (PostgreSQL)** | Persistent data storage | Stores download jobs, metadata, progress, and system state |
| **Redis Message Broker** | In-memory message queue and cache | Manages Celery task queues and caches temporary data |
| **Storage Handler** | File storage abstraction layer | Provides unified interface for local filesystem and cloud storage |
| **Local FS / AWS S3** | Physical storage backends | Stores downloaded video files, subtitles, and thumbnails |

### Core Components

**1. FastAPI Application Layer**
```python
# app/main.py
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.routers import downloads, status, health
from app.core.config import settings

app = FastAPI(
    title="YouTube Download Service",
    version="1.0.0",
    docs_url="/api/docs"
)

app.include_router(downloads.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")
```

**2. Download Engine**
```python
# app/services/downloader.py
import yt_dlp
from app.core.storage import get_storage_handler

class YouTubeDownloader:
    def __init__(self):
        self.storage = get_storage_handler()
        
    async def download_video(self, url: str, options: dict):
        ydl_opts = {
            'format': options.get('quality', 'best'),
            'writesubtitles': options.get('include_transcription', True),
            'writeautomaticsub': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Process download with storage routing
```

**3. Storage Abstraction**
```python
# app/core/storage.py
from abc import ABC, abstractmethod
import os
import boto3
from app.core.config import settings

class StorageHandler(ABC):
    @abstractmethod
    async def save_file(self, file_path: str, content: bytes): pass

class LocalStorageHandler(StorageHandler):
    def __init__(self, base_path: str = "./downloads"):
        self.base_path = base_path

class S3StorageHandler(StorageHandler):
    def __init__(self, bucket_name: str):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
```

**4. Background Job Processing**
```python
# app/tasks/download_tasks.py
from celery import Celery
from app.services.downloader import YouTubeDownloader

celery_app = Celery("youtube_service")

@celery_app.task(bind=True)
def process_download(self, job_id: str, url: str, options: dict):
    downloader = YouTubeDownloader()
    return downloader.download_video(url, options)
```

## Deployment Scenarios

### Localhost Deployment

**Python Environment Setup:**
```bash
# Python 3.9+ required
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Dependencies (requirements.txt):**
```text
fastapi==0.104.1
uvicorn[standard]==0.24.0
yt-dlp==2023.10.13
boto3==1.29.7
sqlalchemy[asyncio]==2.0.23
asyncpg==0.29.0
celery[redis]==5.3.4
redis==5.0.1
pydantic==2.5.0
pydantic-settings==2.1.0
ffmpeg-python==0.2.0
pysrt==1.1.2
webvtt-py==0.4.6
aiofiles==23.2.1
httpx==0.25.2
python-multipart==0.0.6
```

**Local Configuration:**
```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Environment
    environment: str = "localhost"
    debug: bool = True
    
    # Service
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Storage
    download_base_path: str = "./downloads"
    max_file_size_gb: int = 5
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./youtube_service.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Processing
    max_concurrent_downloads: int = 3
    download_timeout: int = 3600
    
    class Config:
        env_file = ".env"

settings = Settings()
```

**Startup Scripts:**
```bash
# Start Redis
redis-server

# Start Celery Worker
celery -A app.tasks.download_tasks worker --loglevel=info

# Start FastAPI Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### AWS Cloud Deployment

**Infrastructure Components:**
- **Compute:** ECS Fargate with Application Load Balancer
- **Storage:** S3 bucket with CloudFront CDN
- **Database:** RDS PostgreSQL or Amazon Aurora
- **Cache:** ElastiCache Redis cluster
- **Queue:** Amazon SQS + ECS tasks for Celery workers

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**AWS Configuration:**
```python
# app/core/config.py - AWS Environment
class AWSSettings(Settings):
    environment: str = "aws"
    
    # AWS Services
    aws_region: str = "us-east-1"
    s3_bucket_name: str
    s3_cloudfront_domain: str = None
    
    # Database
    database_url: str  # RDS PostgreSQL connection string
    
    # Redis
    redis_url: str  # ElastiCache Redis endpoint
    
    # SQS for Celery
    broker_url: str  # SQS broker URL
    result_backend: str  # Redis or RDS for results
    
    # Monitoring
    cloudwatch_log_group: str = "/aws/ecs/youtube-service"
    enable_xray: bool = True
```

## API Specification

### FastAPI Endpoints

**Download Request Model:**
```python
# app/models/download.py
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from enum import Enum

class VideoQuality(str, Enum):
    BEST = "best"
    WORST = "worst"
    HD720 = "720p"
    HD1080 = "1080p"
    HD1440 = "1440p"
    UHD2160 = "2160p"

class DownloadRequest(BaseModel):
    url: HttpUrl
    quality: VideoQuality = VideoQuality.HD1080
    include_transcription: bool = True
    audio_only: bool = False
    subtitle_languages: List[str] = ["en"]
    output_format: str = "mp4"
```

**API Routes:**
```python
# app/routers/downloads.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.models.download import DownloadRequest, DownloadResponse
from app.tasks.download_tasks import process_download

router = APIRouter()

@router.post("/download", response_model=DownloadResponse)
async def create_download(
    request: DownloadRequest,
    background_tasks: BackgroundTasks
):
    job_id = str(uuid4())
    
    # Validate YouTube URL
    if not is_valid_youtube_url(str(request.url)):
        raise HTTPException(400, "Invalid YouTube URL")
    
    # Queue background task
    task = process_download.delay(job_id, str(request.url), request.dict())
    
    return DownloadResponse(
        job_id=job_id,
        status="queued",
        task_id=task.id
    )

@router.get("/status/{job_id}")
async def get_download_status(job_id: str):
    # Implementation with database lookup
    pass

@router.get("/downloads")
async def list_downloads(skip: int = 0, limit: int = 20):
    # Implementation with pagination
    pass
```

**WebSocket for Real-time Progress:**
```python
# app/routers/websocket.py
from fastapi import WebSocket, WebSocketDisconnect
from app.core.websocket_manager import ConnectionManager

manager = ConnectionManager()

@router.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    try:
        while True:
            # Send progress updates
            progress = await get_job_progress(job_id)
            await manager.send_progress(job_id, progress)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
```

## Database Models

**SQLAlchemy Models:**
```python
# app/models/database.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

class DownloadJob(Base):
    __tablename__ = "download_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued, processing, completed, failed
    progress = Column(Float, default=0.0)
    
    # Video metadata
    title = Column(String)
    duration = Column(Integer)  # seconds
    channel_name = Column(String)
    upload_date = Column(DateTime)
    
    # Processing options
    quality = Column(String)
    include_transcription = Column(Boolean, default=True)
    audio_only = Column(Boolean, default=False)
    
    # Storage paths
    video_path = Column(String)
    transcription_path = Column(String)
    thumbnail_path = Column(String)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
```

## Configuration Management

### Environment-Specific Settings

**Local Development (.env):**
```bash
# Environment
ENVIRONMENT=localhost
DEBUG=true

# Service
HOST=0.0.0.0
PORT=8000

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/youtube_service

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
DOWNLOAD_BASE_PATH=./downloads
MAX_FILE_SIZE_GB=5

# Processing
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_TIMEOUT=3600

# YouTube
YT_DLP_UPDATE_CHECK=false
EXTRACT_FLAT=false
```

**Production AWS (.env.prod):**
```bash
# Environment
ENVIRONMENT=aws
DEBUG=false

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db.cluster-xxx.us-east-1.rds.amazonaws.com:5432/youtube_service

# Redis
REDIS_URL=redis://prod-redis.xxx.cache.amazonaws.com:6379/0

# AWS
AWS_REGION=us-east-1
S3_BUCKET_NAME=youtube-downloads-prod
S3_CLOUDFRONT_DOMAIN=d1234567890.cloudfront.net

# Celery
BROKER_URL=sqs://
RESULT_BACKEND=redis://prod-redis.xxx.cache.amazonaws.com:6379/1

# Monitoring
CLOUDWATCH_LOG_GROUP=/aws/ecs/youtube-service
ENABLE_XRAY=true

# Security
SECRET_KEY=your-secret-key-here
API_KEY_HEADER=X-API-Key
```

## Deployment Procedures

### Local Development Setup

**1. Environment Setup:**
```bash
# Clone repository
git clone https://github.com/yourorg/youtube-service.git
cd youtube-service

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies

# Setup pre-commit hooks
pre-commit install
```

**2. Database Setup:**
```bash
# Start PostgreSQL (or use SQLite for development)
# Create database
createdb youtube_service

# Run migrations
alembic upgrade head

# Optional: Load sample data
python scripts/seed_data.py
```

**3. Start Services:**
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery Worker
celery -A app.tasks.download_tasks worker --loglevel=info --concurrency=2

# Terminal 3: FastAPI Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### AWS Production Deployment

**1. Infrastructure as Code (Terraform):**
```hcl
# infrastructure/main.tf
module "vpc" {
  source = "./modules/vpc"
}

module "ecs_cluster" {
  source = "./modules/ecs"
  vpc_id = module.vpc.vpc_id
}

module "rds" {
  source = "./modules/rds"
  vpc_id = module.vpc.vpc_id
}

module "elasticache" {
  source = "./modules/elasticache"
  vpc_id = module.vpc.vpc_id
}

module "s3" {
  source = "./modules/s3"
}
```

**2. Container Deployment:**
```bash
# Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

docker build -t youtube-service .
docker tag youtube-service:latest 123456789.dkr.ecr.us-east-1.amazonaws.com/youtube-service:latest
docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/youtube-service:latest

# Deploy ECS service
aws ecs update-service --cluster youtube-service --service youtube-api --force-new-deployment
```

**3. Database Migration:**
```bash
# Run migrations in ECS task
aws ecs run-task \
  --cluster youtube-service \
  --task-definition youtube-migration \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

## Monitoring & Observability

### Logging Configuration

**Python Logging Setup:**
```python
# app/core/logging.py
import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    logHandler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.addHandler(logHandler)
    logger.setLevel(logging.INFO)
    
    # Suppress noisy third-party logs
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
```

### Metrics and Health Checks

**Health Check Endpoint:**
```python
# app/routers/health.py
@router.get("/health")
async def health_check():
    checks = {
        "database": await check_database_connection(),
        "redis": await check_redis_connection(),
        "storage": await check_storage_access(),
        "celery": await check_celery_workers()
    }
    
    status = "healthy" if all(checks.values()) else "unhealthy"
    
    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }
```

### Performance Monitoring

**Custom Metrics:**
```python
# app/core/metrics.py
import time
from functools import wraps

def track_download_metrics(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            # Log success metrics
            duration = time.time() - start_time
            logger.info("download_completed", duration=duration, **kwargs)
            return result
        except Exception as e:
            # Log error metrics
            logger.error("download_failed", error=str(e), **kwargs)
            raise
    return wrapper
```

## Security Implementation

### Authentication & Authorization

**API Key Authentication:**
```python
# app/core/auth.py
from fastapi import HTTPException, Depends
from fasta