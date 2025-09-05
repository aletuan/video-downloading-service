# API Documentation

## Authentication

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

## Endpoints

### Public Endpoints (No Authentication)
- `GET /health` - Basic health check
- `GET /health/detailed` - Comprehensive system health
- `GET /api/v1/info?url={youtube_url}` - Extract video information without downloading

### Protected Endpoints (Require Authentication)
- `POST /api/v1/download` - Start a new download job (DOWNLOAD permission required)
- `GET /api/v1/status/{job_id}` - Get job status and details (READ_ONLY permission required)
- `GET /api/v1/jobs` - List all download jobs with pagination (READ_ONLY permission required) 
- `POST /api/v1/retry/{job_id}` - Retry a failed download job (DOWNLOAD permission required)
- `WS /ws/progress/{job_id}?api_key={key}` - WebSocket for real-time progress updates

### Admin Endpoints (ADMIN Permission Required)
- `POST /api/v1/admin/api-keys` - Create new API key
- `GET /api/v1/admin/api-keys` - List all API keys
- `GET /api/v1/admin/api-keys/{key_id}` - Get specific API key details
- `PUT /api/v1/admin/api-keys/{key_id}` - Update API key
- `DELETE /api/v1/admin/api-keys/{key_id}` - Delete API key

## Usage Examples

### Extract video information (public endpoint)
```bash
curl "http://localhost:8000/api/v1/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

### Start a download with authentication
```bash
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

### Check job status with API key
```bash
curl -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/status/{job_id}"
```

### List all jobs with filtering and authentication
```bash
curl -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/jobs?status=completed&page=1&per_page=10"
```

### Retry a failed job with authentication
```bash
curl -X POST \
     -H "X-API-Key: your-api-key-here" \
     "http://localhost:8000/api/v1/retry/{job_id}"
```

### Connect to WebSocket with authentication
```bash
wscat -c "ws://localhost:8000/ws/progress/{job_id}?api_key=your-api-key-here"
```

### Admin: Create a new API key
```bash
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

## Interactive Documentation

Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc