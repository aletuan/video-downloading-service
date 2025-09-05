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

### Bootstrap Endpoints (Setup Only)
- `GET /api/v1/bootstrap/status` - Check if system needs initial setup
- `POST /api/v1/bootstrap/admin-key` - Create initial admin API key (one-time setup)

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

### Bootstrap Setup (First-time Setup)

#### Check if system needs setup
```bash
curl "http://localhost:8000/api/v1/bootstrap/status"
```

#### Create initial admin API key (one-time setup)
```bash
curl -X POST "http://localhost:8000/api/v1/bootstrap/admin-key" \
     -H "Content-Type: application/json" \
     -H "X-Setup-Token: dev-bootstrap-token-12345" \
     -d '{
       "name": "Initial Admin Key",
       "description": "Bootstrap admin key for initial setup"
     }'
```

**Important Notes:**
- This endpoint only works when **no admin keys exist** in the database
- Requires `BOOTSTRAP_SETUP_TOKEN` environment variable
- **Auto-disables** after creating the first admin key
- Use the returned API key to create additional keys via admin endpoints

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

## API Response Examples

### Video Information Response
```json
{
  "status": "success",
  "data": {
    "title": "Amazing YouTube Video Title",
    "description": "This is an amazing video about...",
    "duration": 300,
    "uploader": "Channel Name",
    "upload_date": "2024-01-15",
    "view_count": 1500000,
    "like_count": 25000,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "available_formats": [
      {
        "format_id": "720p",
        "ext": "mp4",
        "resolution": "1280x720",
        "filesize": 45000000
      },
      {
        "format_id": "1080p", 
        "ext": "mp4",
        "resolution": "1920x1080",
        "filesize": 80000000
      }
    ],
    "available_subtitles": ["en", "es", "fr", "de"]
  }
}
```

### Download Job Creation Response
```json
{
  "status": "accepted",
  "message": "Download job created successfully",
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "created_at": "2024-01-15T10:30:00Z",
    "estimated_time": 120,
    "websocket_url": "ws://localhost:8000/ws/progress/550e8400-e29b-41d4-a716-446655440000"
  }
}
```

### Job Status Response

#### Queued Job
```json
{
  "status": "success",
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "queued",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:05Z",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "quality": "720p",
    "output_format": "mp4",
    "include_transcription": true,
    "subtitle_languages": ["en"],
    "progress": 0,
    "estimated_time_remaining": 120
  }
}
```

#### In Progress Job
```json
{
  "status": "success", 
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "processing",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:31:30Z",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "quality": "720p",
    "output_format": "mp4",
    "include_transcription": true,
    "subtitle_languages": ["en"],
    "progress": 45,
    "current_step": "downloading_video",
    "video_info": {
      "title": "Amazing YouTube Video Title",
      "duration": 300,
      "uploader": "Channel Name"
    },
    "estimated_time_remaining": 65
  }
}
```

#### Completed Job
```json
{
  "status": "success",
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000", 
    "status": "completed",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:32:45Z",
    "completed_at": "2024-01-15T10:32:45Z",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "quality": "720p",
    "output_format": "mp4",
    "include_transcription": true,
    "subtitle_languages": ["en"],
    "progress": 100,
    "video_info": {
      "title": "Amazing YouTube Video Title",
      "duration": 300,
      "uploader": "Channel Name",
      "upload_date": "2024-01-15",
      "view_count": 1500000
    },
    "files": {
      "video_url": "https://cdn.example.com/videos/550e8400-e29b-41d4-a716-446655440000.mp4",
      "video_path": "/downloads/videos/550e8400-e29b-41d4-a716-446655440000.mp4",
      "video_size": 45000000,
      "transcripts": {
        "en": {
          "srt_url": "https://cdn.example.com/transcripts/550e8400-e29b-41d4-a716-446655440000_en.srt",
          "vtt_url": "https://cdn.example.com/transcripts/550e8400-e29b-41d4-a716-446655440000_en.vtt",
          "txt_url": "https://cdn.example.com/transcripts/550e8400-e29b-41d4-a716-446655440000_en.txt"
        }
      }
    },
    "processing_time": 165
  }
}
```

#### Failed Job
```json
{
  "status": "success",
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "failed", 
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:31:15Z",
    "failed_at": "2024-01-15T10:31:15Z",
    "url": "https://www.youtube.com/watch?v=invalid",
    "quality": "720p",
    "output_format": "mp4",
    "progress": 15,
    "error": {
      "code": "VIDEO_NOT_AVAILABLE",
      "message": "Video is private or unavailable",
      "details": "The requested video cannot be accessed. It may be private, deleted, or geo-restricted."
    },
    "retry_count": 0,
    "can_retry": true
  }
}
```

### Job Listing Response
```json
{
  "status": "success",
  "data": {
    "jobs": [
      {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "status": "completed",
        "created_at": "2024-01-15T10:30:00Z",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_title": "Amazing YouTube Video Title",
        "quality": "720p",
        "output_format": "mp4",
        "progress": 100
      },
      {
        "job_id": "660e8400-e29b-41d4-a716-446655440001", 
        "status": "processing",
        "created_at": "2024-01-15T10:35:00Z",
        "url": "https://www.youtube.com/watch?v=another_video",
        "video_title": "Another Great Video",
        "quality": "1080p",
        "output_format": "mp4", 
        "progress": 30
      }
    ],
    "pagination": {
      "page": 1,
      "per_page": 10,
      "total": 25,
      "total_pages": 3,
      "has_next": true,
      "has_prev": false
    }
  }
}
```

### API Key Creation Response
```json
{
  "status": "success",
  "message": "API key created successfully",
  "data": {
    "id": 123,
    "name": "My Application Key",
    "key": "yk_live_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
    "permission_level": "download",
    "description": "API key for my application",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z",
    "expires_at": null,
    "usage_count": 0,
    "created_by": "admin"
  }
}
```

### WebSocket Progress Messages

#### Connection Established
```json
{
  "type": "connection",
  "status": "connected",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Connected to progress updates",
  "timestamp": "2024-01-15T10:30:10Z"
}
```

#### Progress Update
```json
{
  "type": "progress",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 45,
  "current_step": "downloading_video",
  "message": "Downloading video: 45% complete",
  "estimated_time_remaining": 65,
  "timestamp": "2024-01-15T10:31:30Z"
}
```

#### Status Change
```json
{
  "type": "status",
  "job_id": "550e8400-e29b-41d4-a716-446655440000", 
  "status": "completed",
  "progress": 100,
  "message": "Download completed successfully",
  "files": {
    "video_url": "https://cdn.example.com/videos/550e8400-e29b-41d4-a716-446655440000.mp4"
  },
  "timestamp": "2024-01-15T10:32:45Z"
}
```

#### Error Message
```json
{
  "type": "error",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed", 
  "error": {
    "code": "DOWNLOAD_ERROR",
    "message": "Failed to download video",
    "details": "Network timeout while downloading video content"
  },
  "timestamp": "2024-01-15T10:31:45Z"
}
```

## Error Responses

### Authentication Errors
```json
{
  "status": "error",
  "error": {
    "code": "INVALID_API_KEY",
    "message": "Invalid or missing API key",
    "details": "Please provide a valid API key using X-API-Key header"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Rate Limiting
```json
{
  "status": "error", 
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests",
    "details": "Rate limit exceeded. Please try again in 60 seconds",
    "retry_after": 60
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Validation Errors
```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR", 
    "message": "Invalid request data",
    "details": {
      "url": ["Invalid YouTube URL format"],
      "quality": ["Quality must be one of: 144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p"]
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Resource Not Found
```json
{
  "status": "error",
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job not found", 
    "details": "No job found with ID: 550e8400-e29b-41d4-a716-446655440000"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Interactive Documentation

Once running, access the interactive API documentation at:
- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc