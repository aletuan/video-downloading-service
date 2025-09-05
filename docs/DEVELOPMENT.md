# Development Guide

## Project Structure

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

## Running Tests

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

## Database Migrations

```bash
# Inside Docker container
docker compose exec app alembic upgrade head
docker compose exec app alembic revision --autogenerate -m "Description"

# Local development
alembic upgrade head
alembic revision --autogenerate -m "Description"
alembic downgrade -1
```

## Security Development

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

## Code Quality

### Formatting and Linting
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

## Docker Development Commands

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

## Local Development Setup

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- FFmpeg (for video processing)

### Installation Steps

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

## Configuration

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

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `python -m pytest`
5. Commit your changes: `git commit -m 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request