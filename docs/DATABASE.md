# Database Documentation

## Overview

The YouTube Video Download Service uses **PostgreSQL** as its primary database for storing job metadata, API key management, and system state. The database is designed to support both local development (with Docker) and production AWS deployments.

## Database Configuration

### Local Development
- **Database**: PostgreSQL 15 (Docker container)
- **Host**: localhost:5433 (non-standard port to avoid conflicts)
- **Database Name**: `youtube_service`
- **User**: `postgres`

### Production (AWS)
- **Database**: Amazon RDS PostgreSQL
- **Connection**: Via environment variables
- **SSL**: Enabled with certificate validation

## Database Schema

### Migration Management

The database uses **Alembic** for schema migrations:

```sql
-- Migration tracking table
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
```

Current migration version: `0ac7509dc1a4` (add_apikey_table_for_authentication)

## Core Tables

### 1. `download_jobs` - Video Download Jobs

Stores all YouTube video download requests and their processing status.

```sql
CREATE TABLE download_jobs (
    -- Primary identification
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Core download information
    url                   VARCHAR NOT NULL,              -- YouTube video URL
    status                VARCHAR NOT NULL DEFAULT 'queued',  -- queued, processing, completed, failed
    progress              DOUBLE PRECISION DEFAULT 0.0,  -- Download progress (0-100)
    
    -- Video metadata (populated after extraction)
    title                 VARCHAR,                       -- Video title
    duration              INTEGER,                       -- Duration in seconds
    channel_name          VARCHAR,                       -- YouTube channel name
    upload_date           TIMESTAMP WITHOUT TIME ZONE,  -- Video upload date
    view_count            INTEGER,                       -- Number of views
    like_count            INTEGER,                       -- Number of likes
    
    -- Processing options (set by user)
    quality               VARCHAR DEFAULT 'best',       -- Video quality (720p, 1080p, etc.)
    include_transcription BOOLEAN DEFAULT true,          -- Include subtitle files
    audio_only            BOOLEAN DEFAULT false,         -- Audio-only download
    output_format         VARCHAR DEFAULT 'mp4',        -- Output format (mp4, mkv, webm)
    subtitle_languages    VARCHAR,                       -- JSON array of language codes
    
    -- Storage paths (populated after download)
    video_path            VARCHAR,                       -- Path to downloaded video file
    transcription_path    VARCHAR,                       -- Path to subtitle file
    thumbnail_path        VARCHAR,                       -- Path to thumbnail image
    
    -- File information
    file_size             INTEGER,                       -- File size in bytes
    video_codec           VARCHAR,                       -- Video codec used
    audio_codec           VARCHAR,                       -- Audio codec used
    
    -- Timestamps
    created_at            TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    started_at            TIMESTAMP WITHOUT TIME ZONE,   -- When processing began
    completed_at          TIMESTAMP WITHOUT TIME ZONE,   -- When processing finished
    
    -- Error handling
    error_message         TEXT,                          -- Error details if failed
    retry_count           INTEGER DEFAULT 0,             -- Number of retry attempts
    max_retries           INTEGER DEFAULT 3,             -- Maximum retry attempts
    
    -- Request tracking
    user_agent            VARCHAR,                       -- Client user agent
    ip_address            VARCHAR                        -- Client IP address
);

-- Indexes for performance
CREATE INDEX ix_download_jobs_id ON download_jobs(id);
CREATE INDEX ix_download_jobs_status ON download_jobs(status);
CREATE INDEX ix_download_jobs_url ON download_jobs(url);
```

### 2. `api_keys` - Authentication Management

Manages API keys for system authentication and authorization.

```sql
CREATE TABLE api_keys (
    -- Primary identification
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- API key information
    name                  VARCHAR NOT NULL,              -- Human-readable name
    key_hash              VARCHAR NOT NULL UNIQUE,       -- SHA-256 hash of API key
    permission_level      VARCHAR NOT NULL DEFAULT 'read_only', -- Permission level
    
    -- Status and metadata
    is_active             BOOLEAN NOT NULL DEFAULT true, -- Active status
    description           TEXT,                          -- Optional description
    
    -- Usage tracking
    last_used_at          TIMESTAMP WITH TIME ZONE,     -- Last usage timestamp
    usage_count           INTEGER NOT NULL DEFAULT 0,    -- Total usage count
    
    -- Rate limiting
    custom_rate_limit     INTEGER,                       -- Custom rate limit (requests/min)
    
    -- Timestamps
    created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at            TIMESTAMP WITH TIME ZONE,      -- Optional expiration
    
    -- Metadata
    created_by            VARCHAR,                       -- Creator identifier
    notes                 TEXT                           -- Additional notes
);

-- Indexes for performance
CREATE INDEX ix_api_keys_id ON api_keys(id);
CREATE INDEX ix_api_keys_name ON api_keys(name);
CREATE INDEX ix_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX ix_api_keys_is_active ON api_keys(is_active);
```

## Permission Levels

The `api_keys.permission_level` field supports these values:

- **`read_only`**: Can access job status and listing endpoints
- **`download`**: Can create download jobs + all read operations
- **`admin`**: Can manage API keys + all download operations
- **`full_access`**: Complete system access (reserved for system operations)

## Sample Data

### Download Jobs Example

```sql
-- Completed video download job
INSERT INTO download_jobs VALUES (
    '747446bf-708f-4044-87ed-fc875b7592ae',              -- id
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',        -- url
    'completed',                                          -- status
    100.0,                                                -- progress
    'Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)', -- title
    213,                                                  -- duration (3:33)
    'Rick Astley',                                        -- channel_name
    NULL,                                                 -- upload_date
    1691342467,                                           -- view_count (1.6B views)
    18536364,                                             -- like_count (18.5M likes)
    '720p',                                               -- quality
    true,                                                 -- include_transcription
    false,                                                -- audio_only
    'mp4',                                                -- output_format
    'en',                                                 -- subtitle_languages
    'downloads/747446bf-708f-4044-87ed-fc875b7592ae/Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).mp4', -- video_path
    'downloads/747446bf-708f-4044-87ed-fc875b7592ae/subtitles/Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).en.srt', -- transcription_path
    'downloads/747446bf-708f-4044-87ed-fc875b7592ae/thumbnail.webp', -- thumbnail_path
    11750943,                                             -- file_size (11.75 MB)
    NULL,                                                 -- video_codec
    NULL,                                                 -- audio_codec
    '2025-09-06 16:41:40.160613',                        -- created_at
    '2025-09-06 16:41:40.335438',                        -- started_at
    '2025-09-06 16:42:07.557304',                        -- completed_at
    NULL,                                                 -- error_message
    0,                                                    -- retry_count
    3,                                                    -- max_retries
    NULL,                                                 -- user_agent
    NULL                                                  -- ip_address
);
```

**Key Statistics from Sample Data:**
- **Processing Time**: 27 seconds (from start to completion)
- **File Size**: 11.75 MB for 3:33 video at 720p quality
- **Success Rate**: 100% (completed on first attempt, no retries needed)
- **Files Generated**: Video (MP4) + English subtitles (SRT) + Thumbnail (WebP)

### API Keys Example

```sql
-- Admin API key (bootstrap created)
INSERT INTO api_keys VALUES (
    '89a42cc0-cc34-4399-b860-0d68d55c9ab0',              -- id
    'Initial Admin Key - Test',                           -- name
    '[SHA-256-HASH]',                                     -- key_hash (actual hash omitted)
    'admin',                                              -- permission_level
    true,                                                 -- is_active
    'Bootstrap admin key for localhost testing',          -- description
    '2025-09-06 16:43:07.390006+00',                     -- last_used_at
    5,                                                    -- usage_count
    NULL,                                                 -- custom_rate_limit
    '2025-09-06 16:37:39.095799+00',                     -- created_at
    '2025-09-06 16:43:07.391746+00',                     -- updated_at
    NULL,                                                 -- expires_at (permanent)
    'bootstrap_endpoint',                                 -- created_by
    NULL                                                  -- notes
);

-- Download API key (user created)
INSERT INTO api_keys VALUES (
    '90c7ddf8-004b-4319-9893-72c92d1037a2',              -- id
    'Video Download Key - Test',                          -- name
    '[SHA-256-HASH]',                                     -- key_hash (actual hash omitted)
    'download',                                           -- permission_level
    true,                                                 -- is_active
    'API key for testing video downloads with localhost storage', -- description
    '2025-09-06 16:41:40.14523+00',                      -- last_used_at
    1,                                                    -- usage_count
    NULL,                                                 -- custom_rate_limit
    '2025-09-06 16:41:25.805252+00',                     -- created_at
    '2025-09-06 16:41:40.146757+00',                     -- updated_at
    NULL,                                                 -- expires_at (permanent)
    'Initial Admin Key - Test',                           -- created_by
    NULL                                                  -- notes
);
```

**Usage Statistics from Sample Data:**
- **Admin Key**: Used 5 times (system management operations)
- **Download Key**: Used 1 time (for the video download above)
- **Creation Pattern**: Bootstrap → Admin Key → Download Key (proper hierarchy)

## File System Integration

The database stores file paths that correspond to actual files on disk:

```text
downloads/
└── downloads/
    └── 747446bf-708f-4044-87ed-fc875b7592ae/    # Job ID as folder name
        ├── Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).mp4  # 11.75 MB
        ├── thumbnail.webp                         # 28.6 KB
        └── subtitles/
            └── Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).en.srt  # 4.4 KB
```

**Sample Subtitle Content:**
```srt
1
00:00:01,360 --> 00:00:03,040
[♪♪♪]

2
00:00:18,640 --> 00:00:21,880
♪ We're no strangers to love ♪

3
00:00:22,640 --> 00:00:26,960
♪ You know the rules and so do I ♪
```

## Database Operations

### Common Queries

```sql
-- Get all active download jobs
SELECT id, url, status, progress, title, created_at 
FROM download_jobs 
WHERE status != 'failed' 
ORDER BY created_at DESC;

-- Get API key usage statistics
SELECT name, permission_level, usage_count, last_used_at, created_at
FROM api_keys 
WHERE is_active = true 
ORDER BY usage_count DESC;

-- Get failed jobs for retry analysis
SELECT id, url, error_message, retry_count, created_at
FROM download_jobs 
WHERE status = 'failed' AND retry_count < max_retries
ORDER BY created_at ASC;

-- Get storage usage by job
SELECT 
    COUNT(*) as total_jobs,
    SUM(file_size) as total_storage_bytes,
    AVG(file_size) as avg_file_size,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_jobs
FROM download_jobs;
```

### Performance Considerations

- **Indexes**: Created on frequently queried columns (id, status, url, is_active)
- **UUID Primary Keys**: Distributed evenly for better performance at scale
- **Timestamp Indexes**: Consider adding for time-based queries
- **File Path Length**: VARCHAR columns can handle long file paths
- **JSON Fields**: `subtitle_languages` stored as JSON string for flexibility

## Migration History

1. **dfbe7de3e5a3** (Initial): Create `download_jobs` table
2. **0ac7509dc1a4** (Current): Add `api_keys` table for authentication

## Maintenance

### Regular Maintenance Tasks

```sql
-- Clean up old completed jobs (optional, based on retention policy)
DELETE FROM download_jobs 
WHERE status = 'completed' 
AND completed_at < NOW() - INTERVAL '90 days';

-- Update API key last_used_at timestamps (handled automatically by application)
-- Archive inactive API keys
UPDATE api_keys SET is_active = false 
WHERE last_used_at < NOW() - INTERVAL '180 days';

-- Analyze table statistics for query optimization
ANALYZE download_jobs;
ANALYZE api_keys;
```

### Backup Recommendations

- **Full Database Backup**: Daily automated backups
- **Point-in-Time Recovery**: Enable WAL archiving
- **Critical Tables**: `api_keys` (essential for system access)
- **File System Sync**: Coordinate database and storage backups

## Monitoring

Key metrics to monitor:

- **Job Success Rate**: `(completed_jobs / total_jobs) * 100`
- **Average Processing Time**: `AVG(completed_at - started_at)`
- **Storage Growth**: `SUM(file_size)` over time
- **API Key Usage**: Rate limiting and usage patterns
- **Failed Jobs**: Error patterns for system improvement

## Security Notes

- **API Keys**: Stored as SHA-256 hashes, never plaintext
- **Connection Security**: SSL/TLS required for production
- **Access Control**: Role-based permissions via API keys
- **Audit Trail**: Usage tracking in `api_keys.usage_count` and `last_used_at`
- **Data Retention**: Consider policies for PII in job metadata