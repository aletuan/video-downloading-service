# S3 Directory Structure for YouTube Cookie Management

## Overview

This directory contains templates and specifications for the S3 directory structure used to store YouTube cookies and related metadata securely.

## Directory Structure

```
s3://secure-config-bucket/cookies/
├── youtube-cookies-active.txt      # Current active cookies
├── youtube-cookies-backup.txt      # Backup cookies for failover
├── metadata.json                   # Cookie metadata and configuration
├── archive/                        # Historical cookie files
│   ├── youtube-cookies-2025-09-01-abc123.txt
│   └── youtube-cookies-2025-08-01-def456.txt
└── temp/                          # Temporary files during rotation
    └── (temporary files during upload/rotation)
```

## File Naming Conventions

### Active Cookies
- **Filename**: `youtube-cookies-active.txt`
- **Purpose**: Current cookies used by the download service
- **Format**: Netscape HTTP Cookie File format
- **Update frequency**: Every 30 days or when authentication fails

### Backup Cookies
- **Filename**: `youtube-cookies-backup.txt`
- **Purpose**: Fallback cookies when active cookies fail
- **Format**: Netscape HTTP Cookie File format
- **Update frequency**: Updated when active cookies are rotated

### Metadata
- **Filename**: `metadata.json`
- **Purpose**: Tracking cookie status, expiration, usage statistics
- **Format**: JSON with defined schema
- **Update frequency**: Updated with every cookie operation

### Archive Files
- **Pattern**: `youtube-cookies-{YYYY-MM-DD}-{hash}.txt`
- **Purpose**: Historical cookie files for audit and rollback
- **Retention**: 90 days (configured via lifecycle policy)
- **Hash**: SHA-256 hash of cookie content for integrity

## Security Specifications

### Access Control
- **Read Access**: ECS task role only (`s3:GetObject`, `s3:ListBucket`)
- **Write Access**: Admin roles only (for cookie uploads)
- **Public Access**: Completely blocked
- **Encryption**: AES-256 server-side encryption

### File Permissions
```json
{
  "read_roles": ["ecs-task-role"],
  "write_roles": ["admin-role"], 
  "public_access": false,
  "encryption_required": true
}
```

## Cookie File Format

### Netscape HTTP Cookie File Format
```
# Netscape HTTP Cookie File
domain	flag	path	secure	expiration	name	value
.youtube.com	TRUE	/	TRUE	1234567890	session_token	abc123...
.youtube.com	TRUE	/	FALSE	1234567890	VISITOR_INFO1_LIVE	def456...
```

### Required Cookie Types
1. **Session Cookies**: Authentication tokens
2. **Visitor Cookies**: Browser identification
3. **Preference Cookies**: User settings and preferences

## Metadata Schema

### Cookie Metadata Structure
```json
{
  "active_cookies": {
    "filename": "youtube-cookies-active.txt",
    "created_at": "ISO 8601 timestamp",
    "expires_at": "ISO 8601 timestamp", 
    "status": "active|expired|invalid",
    "validation": {
      "last_tested": "ISO 8601 timestamp",
      "test_result": "success|failure",
      "next_test_due": "ISO 8601 timestamp"
    },
    "usage_stats": {
      "success_count": 0,
      "failure_count": 0,
      "success_rate": 0.0
    }
  }
}
```

## Upload and Rotation Procedures

### Initial Setup
1. Export cookies from authenticated browser session
2. Validate cookie format and content
3. Upload using admin script with encryption
4. Update metadata with cookie information
5. Test cookie authentication

### Regular Rotation
1. Export new cookies from browser
2. Upload as temporary file
3. Validate new cookies work
4. Move current active to backup
5. Promote new cookies to active
6. Update metadata
7. Archive old cookies

### Emergency Replacement
1. Detect authentication failures
2. Automatically switch to backup cookies
3. Alert administrators
4. Schedule emergency cookie refresh

## Monitoring and Alerting

### Key Metrics
- Cookie expiration dates
- Authentication success rates
- File access patterns
- Security events

### Alert Triggers
- Cookie expiring within 7 days
- Authentication failure rate > 10%
- Unusual access patterns
- Security policy violations

## Compliance and Audit

### Data Classification
- **Level**: Sensitive
- **Retention**: 90 days
- **Access Logging**: Enabled
- **Encryption**: Required

### Audit Trail
- All cookie access logged
- Metadata changes tracked
- Administrative actions recorded
- Security events monitored

## Usage by Application

### Cookie Manager Integration
The application's `CookieManager` class reads from this structure:

```python
# Active cookies
active_cookies = s3.get_object('cookies/youtube-cookies-active.txt')

# Metadata
metadata = s3.get_object('cookies/metadata.json')

# Backup fallback
backup_cookies = s3.get_object('cookies/youtube-cookies-backup.txt')
```

### Error Handling
- Automatic fallback to backup cookies
- Graceful degradation on cookie failures
- Administrator alerts on critical failures
- Detailed error logging for troubleshooting