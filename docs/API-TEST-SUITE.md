# API Test Suite - YouTube Video Downloading Service

## Overview

This test suite provides comprehensive end-to-end testing of the YouTube video downloading service deployed on AWS infrastructure. Tests are designed to be run systematically to validate all components from infrastructure to video processing.

## Prerequisites

- AWS infrastructure deployed via `./scripts/deploy-infrastructure.sh`
- Docker images built and pushed to ECR
- ALB DNS name available (replace `{ALB_DNS}` in commands)
- `jq` installed for JSON parsing

## Test Environment Variables

```bash
export ALB_DNS="youtube-do-dev-alb-ff494fc6-1992147449.us-east-1.elb.amazonaws.com"
export S3_BUCKET="youtube-downloader-dev-videos-dc6abb7746a3ee7b"
```

---

## Phase 1: Health Checks (No Authentication Required)

### Test 1: Basic Health Check

**Purpose:** Verify service is running and responsive  
**Expected Outcome:** 200 OK with basic service information

```bash
curl "http://${ALB_DNS}/health" \
     -w "\n--- Response Info ---\nHTTP Status: %{http_code}\nTotal time: %{time_total}s\n" \
     -v
```

**Expected Response:**

```json
{
  "status": "healthy",
  "environment": "aws",
  "version": "1.0.0"
}
```

### Test 2: Detailed Health Check

**Purpose:** Verify all system components (database, storage)  
**Expected Outcome:** 200 OK with detailed component status

```bash
curl "http://${ALB_DNS}/health/detailed" -s | jq .
```

**Expected Response:**

```json
{
  "status": "healthy",
  "environment": "aws",
  "version": "1.0.0",
  "timestamp": "2025-09-06T12:05:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "connected": true,
      "database_url": "youtube-downloader-dev-postgres-*.rds.amazonaws.com:5432/youtube_service?ssl=require",
      "version": "PostgreSQL 15.8 ..."
    },
    "storage": {
      "status": "healthy",
      "storage_type": "S3StorageHandler",
      "base_path": null,
      "bucket_name": "youtube-downloader-dev-videos-*"
    }
  }
}
```

**Key Validation Points:**

- `environment` must be `"aws"` (not "dev")
- `storage_type` must be `"S3StorageHandler"` (not "LocalStorageHandler")  
- `bucket_name` must not be `null`

---

## Phase 2: Bootstrap Setup

### Test 3: Bootstrap Status

**Purpose:** Check if system needs initial setup  
**Expected Outcome:** 200 OK with bootstrap availability status

```bash
curl "http://${ALB_DNS}/api/v1/bootstrap/status" -s | jq .
```

**Expected Response (Before Setup):**

```json
{
  "bootstrap_available": true,
  "message": "System requires bootstrap setup",
  "status": "needs_setup",
  "endpoint": "POST /api/v1/bootstrap/admin-key",
  "required_header": "X-Setup-Token"
}
```

### Test 4: Create Admin Key via Bootstrap

**Purpose:** Create initial admin API key  
**Expected Outcome:** 200 OK with admin API key

```bash
# Get setup token
SETUP_TOKEN=$(aws ssm get-parameter --name "/youtube-downloader/dev/bootstrap/setup-token" --with-decryption --query 'Parameter.Value' --output text)

curl -X POST "http://${ALB_DNS}/api/v1/bootstrap/admin-key" \
     -H "Content-Type: application/json" \
     -H "X-Setup-Token: ${SETUP_TOKEN}" \
     -d '{
       "name": "Initial Admin Key",
       "description": "Bootstrap admin key for initial setup"
     }' -s | jq .
```

**Expected Response:**

```json
{
  "api_key": "yvs_hOP-...",
  "key_id": "dd11ec81-9c98-43f9-b83f-dc024ea360b7",
  "name": "Initial Admin Key",
  "permission_level": "admin",
  "message": "Bootstrap admin key created successfully! This endpoint is now disabled.",
  "next_steps": "Use this API key to create additional keys via /api/v1/admin/api-keys endpoints..."
}
```

**Important:** Save the `api_key` value for subsequent tests!

### Test 4b: Verify Bootstrap Disabled

**Purpose:** Confirm bootstrap endpoint is properly secured  
**Expected Outcome:** 200 OK showing system is configured

```bash
curl "http://${ALB_DNS}/api/v1/bootstrap/status" -s | jq .
```

**Expected Response (After Setup):**

```json
{
  "bootstrap_available": false,
  "message": "System is already set up with admin keys",
  "status": "configured"
}
```

---

## Phase 3: Public Endpoints

### Test 5: Video Info Extraction

**Purpose:** Test video information extraction (no auth required)  
**Expected Outcome:** 200 OK with video metadata OR 502 due to ALB timeout

```bash
curl "http://${ALB_DNS}/api/v1/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
     --max-time 60 -s | head -20
```

**Expected Behavior:**

- **Success**: JSON with video title, duration, available formats
- **502 Bad Gateway**: Expected due to ALB timeout (~29s processing time)
- **Verification**: Check logs to confirm processing completed successfully

**Log Verification:**

```bash
aws logs filter-log-events \
  --log-group-name "/ecs/youtube-downloader-dev-app" \
  --start-time $(python3 -c "import time; print(int((time.time() - 120) * 1000))") \
  --query 'events[?contains(message, `Extracted info for video`)].message'
```

---

## Phase 4: Authentication Tests

### Test 6: List API Keys (Admin Endpoint)

**Purpose:** Test admin authentication and API key management  
**Expected Outcome:** 200 OK with API key list

```bash
ADMIN_KEY="yvs_hOP-..." # From Test 4

curl "http://${ALB_DNS}/api/v1/admin/api-keys" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq .
```

**Expected Response:**

```json
{
  "api_keys": [
    {
      "id": "dd11ec81-9c98-43f9-b83f-dc024ea360b7",
      "name": "Initial Admin Key",
      "permission_level": "admin",
      "is_active": true,
      "description": "Bootstrap admin key for initial setup",
      "usage_count": 1,
      "created_at": "2025-09-06T13:15:30.379354Z",
      "is_valid": true
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 10
}
```

### Test 7: Create Download API Key

**Purpose:** Create API key with download permissions  
**Expected Outcome:** 200 OK with new download API key

```bash
curl -X POST "http://${ALB_DNS}/api/v1/admin/api-keys" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: ${ADMIN_KEY}" \
     -d '{
       "name": "Video Download Key",
       "permission_level": "download",
       "description": "API key for testing video downloads with S3 storage"
     }' -s | jq .
```

**Expected Response:**

```json
{
  "api_key": "yvs_37e1fb69...",
  "key_info": {
    "id": "a2a5b8ab-7eb6-44f6-8f8a-39f07ce9ccc4",
    "name": "Video Download Key",
    "permission_level": "download",
    "is_active": true,
    "usage_count": 0,
    "is_valid": true
  }
}
```

**Important:** Save the `api_key` value for download tests!

---

## Phase 5: Download Operations

### Test 8: Start Video Download

**Purpose:** Test core video download functionality  
**Expected Outcome:** 200 OK with job ID (fast async response)

```bash
DOWNLOAD_KEY="yvs_37e1fb69..." # From Test 7

curl -X POST "http://${ALB_DNS}/api/v1/download" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: ${DOWNLOAD_KEY}" \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "quality": "720p",
       "output_format": "mp4"
     }' -s | jq .
```

**Expected Response:**

```json
{
  "job_id": "2eee8e33-af7f-472f-be54-8d1bc3d4752b",
  "status": "queued",
  "message": "Download job queued successfully",
  "estimated_time": 300
}
```

**Key Validation:**

- Response time should be < 1 second (async job queuing)
- `job_id` should be a valid UUID
- `status` should be `"queued"`

### Test 9: Check Job Status

**Purpose:** Monitor download progress and completion  
**Expected Outcome:** Status progression from queued → processing → completed

```bash
JOB_ID="2eee8e33-af7f-472f-be54-8d1bc3d4752b" # From Test 8

# Initial status (should be "queued" or "processing")
curl "http://${ALB_DNS}/api/v1/status/${JOB_ID}" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq '.status, .progress'

# Wait 30 seconds
sleep 30

# Check completion
curl "http://${ALB_DNS}/api/v1/status/${JOB_ID}" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq '{status, video_path, file_size_formatted, duration_formatted, completed_at}'
```

**Expected Status Progression:**

1. `"queued"` → Job accepted, waiting for worker
2. `"processing"` → Worker actively downloading
3. `"completed"` → Download finished successfully

**Expected Final Response:**

```json
{
  "status": "completed",
  "video_path": "downloads/{job_id}/Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).mp4",
  "file_size_formatted": "11.7 MB",
  "duration_formatted": "03:33",
  "completed_at": "2025-09-06T13:22:56.265871"
}
```

**Permission Note:** Download key lacks READ_ONLY permission for status checking. Use admin key.

### Test 10: Verify S3 Storage

**Purpose:** Confirm files are stored in S3 bucket  
**Expected Outcome:** Files present in S3 with correct structure

```bash
aws s3 ls s3://${S3_BUCKET}/ --recursive
```

**Expected S3 Structure:**

```text
downloads/{job_id}/
├── Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).mp4  (~11.7 MB)
├── subtitles/
│   └── Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster).en.srt  (~4.4 KB)
└── thumbnail.webp  (~28.6 KB)
```

**Key Validation:**

- Video file should be 10-15 MB (720p quality)
- Subtitles should be present if available
- Thumbnail should be included
- Files organized in job-specific directory

---

## Phase 6: Cookie Management Tests

> **⚠️ Security Warning:** Cookie files contain sensitive authentication data. Never commit real cookie files to version control. The `.gitignore` file has been updated to exclude cookie files.

### Test 12: Cookie Manager Health Check

**Purpose:** Verify cookie management system is operational  
**Expected Outcome:** 200 OK with cookie manager status in detailed health check

```bash
curl "http://${ALB_DNS}/health/detailed" -s | jq '.checks.cookie_manager'
```

**Expected Response (Healthy):**

```json
{
  "status": "healthy",
  "message": "Cookie manager is operational",
  "details": {
    "s3_bucket": "youtube-downloader-dev-secure-cookies-abc123def456",
    "encryption_enabled": true,
    "validation_enabled": true,
    "metadata_available": true
  }
}
```

**Expected Response (Disabled):**

```json
{
  "status": "disabled",
  "message": "Cookie management is disabled"
}
```

**Key Validation Points:**

- If enabled: `status` should be `"healthy"`
- `encryption_enabled` should always be `true`
- `s3_bucket` should show the secure storage bucket name

### Test 13: Cookie File Upload & Validation

**Purpose:** Test secure cookie upload system using the dedicated script  
**Expected Outcome:** Successful validation and upload of test cookie file

**Prerequisites:**

```bash
# Use existing test cookie file from repository
# The scripts/test-cookies.txt file already contains comprehensive test cookies
# You can inspect the existing test cookies (36+ cookies from multiple domains):
cat scripts/test-cookies.txt

# File contains cookies for:
# - .youtube.com (YouTube-specific cookies)
# - .google.com (Google authentication cookies) 
# - chromewebstore.google.com (Chrome Web Store cookies)
```

**Validation Only (Safe Test):**

```bash
# Test validation without uploading
python scripts/upload-cookies.py --validate-only scripts/test-cookies.txt
```

**Expected Output:**

```text
Validating cookie file: scripts/test-cookies.txt
Validation Results:
  Format: netscape
  Valid: True
  Cookie Count: 3
  File Size: 234 bytes
  Domains: .google.com, .youtube.com, youtube.com
  Warnings: 0

✅ Validation completed (upload skipped)
```

**Full Upload Test (After Deployment):**

```bash
# Upload test cookies to secure S3 storage
python scripts/upload-cookies.py --source "API Test Suite" \
    --description "Test cookies for integration testing" \
    scripts/test-cookies.txt
```

**Expected Output:**

```text
Uploading cookies...
Upload Verification:
  Success: True
  Active Cookies Present: True
  Metadata Present: True
  Decryption Successful: True
  Cookie Count: 3

✅ Cookie upload completed successfully!
🧹 Cleaned up 0 old backup files
```

### Test 14: List Existing Cookies

**Purpose:** Verify cookie management system shows uploaded cookies  
**Expected Outcome:** Display current cookie information

```bash
python scripts/upload-cookies.py --list-existing
```

**Expected Output:**

```text
Existing Cookies Information:
==================================================
Active Cookies:
  Last Modified: 2025-01-09T14:30:45+00:00
  Size: 234 bytes

Metadata:
  Upload Date: 2025-01-09T14:30:45.123456
  Cookie Count: 3
  Source: API Test Suite
  Uploader: testuser

Recent Backups (0 of 0):
```

### Test 15: Cookie-Enabled Video Download

**Purpose:** Test video download using cookie authentication for enhanced access  
**Expected Outcome:** Successful download with cookie authentication

```bash
# Test download that may require cookies (age-restricted or region-locked)
curl -X POST "http://${ALB_DNS}/api/v1/download" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: ${DOWNLOAD_KEY}" \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "quality": "720p",
       "output_format": "mp4",
       "use_cookies": true
     }' -s | jq .
```

**Expected Response:**

```json
{
  "job_id": "abc123-def4-5678-9012-345678901234",
  "status": "queued",
  "message": "Download job queued successfully with cookie authentication",
  "estimated_time": 300,
  "cookie_enabled": true
}
```

### Test 16: Cookie Manager Status Endpoint

**Purpose:** Test administrative cookie status endpoint  
**Expected Outcome:** Detailed cookie system status

```bash
curl "http://${ALB_DNS}/api/v1/admin/cookies/status" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq .
```

**Expected Response:**

```json
{
  "cookie_manager_status": "operational",
  "active_cookies": {
    "present": true,
    "last_updated": "2025-01-09T14:30:45.123456",
    "cookie_count": 3,
    "expires_earliest": "2024-12-31T23:59:59",
    "domains": [".google.com", ".youtube.com", "youtube.com"]
  },
  "backup_cookies": {
    "present": true,
    "backup_count": 1
  },
  "cache_status": {
    "active_cached": false,
    "backup_cached": false,
    "cache_ttl_seconds": 3600
  },
  "rate_limiting": {
    "requests_per_window": 10,
    "window_seconds": 60,
    "active_identifiers": 0
  }
}
```

### Test 17: Cookie Fallback Testing

**Purpose:** Test cookie fallback mechanisms  
**Expected Outcome:** System gracefully handles cookie failures

```bash
# Temporarily disable/corrupt cookies by renaming in S3
aws s3 mv s3://${COOKIE_BUCKET}/cookies/youtube-cookies-active.txt \
    s3://${COOKIE_BUCKET}/cookies/youtube-cookies-active.txt.disabled

# Test download without cookies
curl -X POST "http://${ALB_DNS}/api/v1/download" \
     -H "Content-Type: application/json" \
     -H "X-API-Key: ${DOWNLOAD_KEY}" \
     -d '{
       "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
       "quality": "720p",
       "use_cookies": true
     }' -s | jq '.status, .message'

# Restore cookies
aws s3 mv s3://${COOKIE_BUCKET}/cookies/youtube-cookies-active.txt.disabled \
    s3://${COOKIE_BUCKET}/cookies/youtube-cookies-active.txt
```

**Expected Behavior:**

- Download should still proceed but with warning about cookie unavailability
- System should not crash or fail completely

### Test 18: Cookie Rotation Testing

**Purpose:** Test cookie rotation functionality  
**Expected Outcome:** Successful rotation from backup to active

```bash
# First, upload a backup cookie set (different from active)
cat > scripts/backup-cookies.txt << 'EOF'
# Backup cookie set
.youtube.com TRUE / FALSE 1735689600 VISITOR_INFO1_LIVE backup123
EOF

python scripts/upload-cookies.py --source "Backup Test" scripts/backup-cookies.txt

# Test manual rotation via API (if endpoint exists)
curl -X POST "http://${ALB_DNS}/api/v1/admin/cookies/rotate" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq .
```

**Expected Response:**

```json
{
  "status": "success",
  "timestamp": "2025-01-09T14:35:00.000000",
  "actions": [
    "validated_backup_cookies",
    "archived_active_cookies", 
    "promoted_backup_to_active",
    "cleared_cache",
    "updated_metadata"
  ],
  "next_rotation": "2025-02-08T14:35:00.000000",
  "warning": "New backup cookies should be uploaded soon"
}
```

---

## Phase 7: Additional API Tests

### Test 19: List Download Jobs

**Purpose:** Test job listing functionality  
**Expected Outcome:** 200 OK with paginated job list

```bash
curl "http://${ALB_DNS}/api/v1/jobs" \
     -H "X-API-Key: ${ADMIN_KEY}" -s | jq .
```

**Expected Response Structure:**

```json
{
  "jobs": [...],
  "total": 1,
  "page": 1,
  "per_page": 10,
  "pages": 1
}
```

---

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. S3 Storage Handler Not Working

**Symptoms:** `storage_type: "LocalStorageHandler"` in health check  
**Cause:** Wrong ENVIRONMENT variable in ECS task definition  
**Solution:** Ensure `ENVIRONMENT=aws` in task definition (not "dev")

#### 2. Database Migration Failures

**Symptoms:** Bootstrap returns table errors  
**Cause:** SSL parameter incompatibility or missing security groups  
**Solution:** Check `alembic/env.py` SSL conversion and ECS security groups

#### 3. ALB 502 Bad Gateway

**Symptoms:** Video info endpoint times out  
**Cause:** Processing time exceeds ALB timeout  
**Expected:** This is normal for video processing (check logs for success)

#### 4. Permission Denied Errors

**Symptoms:** "Permission 'APIKeyPermission.READ_ONLY' required"  
**Cause:** API key lacks required permissions  
**Solution:** Use admin key or create key with appropriate permissions

#### 5. Bootstrap Already Disabled

**Symptoms:** Bootstrap endpoint returns "already configured"  
**Cause:** Admin keys already exist in database  
**Solution:** Normal behavior after initial setup - use existing admin key

#### 6. Cookie Manager Health Check Failed

**Symptoms:** Cookie manager shows "unhealthy" status in detailed health check  
**Cause:** S3 bucket access issues, missing encryption key, or AWS credentials  
**Solution:** Check S3 bucket permissions, verify COOKIE_ENCRYPTION_KEY environment variable

#### 7. Cookie Upload Script Fails

**Symptoms:** "COOKIE_S3_BUCKET environment variable required" error  
**Cause:** Missing cookie S3 bucket configuration  
**Solution:** Set environment variables or use --bucket parameter with upload script

#### 8. Cookie Files Committed to Git

**Symptoms:** Git shows cookie files in tracked changes  
**Cause:** Cookie files not properly excluded from version control  
**Solution:** Verify `.gitignore` includes cookie file patterns, remove from git if committed

---

## Performance Benchmarks

### Expected Response Times

- **Health Checks:** < 1 second
- **API Key Operations:** < 1 second  
- **Download Job Submission:** < 1 second
- **Video Info Extraction:** 20-30 seconds (may timeout at ALB)
- **Video Download (720p):** 20-60 seconds depending on video length
- **Job Status Check:** < 1 second
- **Cookie Upload/Validation:** 1-3 seconds
- **Cookie Manager Operations:** < 1 second

### Expected File Sizes (720p MP4)

- **3-4 minute videos:** 10-20 MB
- **Subtitles:** 2-10 KB
- **Thumbnails:** 20-50 KB

---

## Test Automation Script

```bash
#!/bin/bash
# Quick test runner - save as test-runner.sh

set -e

# Configuration
ALB_DNS="${ALB_DNS:-youtube-do-dev-alb-ff494fc6-1992147449.us-east-1.elb.amazonaws.com}"
S3_BUCKET="${S3_BUCKET:-youtube-downloader-dev-videos-dc6abb7746a3ee7b}"
COOKIE_BUCKET="${COOKIE_BUCKET:-youtube-downloader-dev-secure-cookies-abc123def456}"

echo "Starting YouTube Downloader API Test Suite"
echo "ALB DNS: $ALB_DNS"
echo "S3 Bucket: $S3_BUCKET"
echo "Cookie Bucket: $COOKIE_BUCKET"

# Test 1: Health Check
echo "Test 1: Health Check"
curl -s "http://$ALB_DNS/health" | jq -r '.status // "FAILED"'

# Test 2: Bootstrap Status  
echo "Test 2: Bootstrap Status"
curl -s "http://$ALB_DNS/api/v1/bootstrap/status" | jq -r '.status // "FAILED"'

# Test 3: Cookie Manager Health
echo "Test 3: Cookie Manager Health"
curl -s "http://$ALB_DNS/health/detailed" | jq -r '.checks.cookie_manager.status // "DISABLED"'

# Test 4: Cookie Validation (if test file exists)
if [ -f "scripts/test-cookies.txt" ]; then
    echo "Test 4: Cookie Validation"
    python scripts/upload-cookies.py --validate-only scripts/test-cookies.txt | grep -q "✅" && echo "PASSED" || echo "FAILED"
else
    echo "Test 4: Cookie Validation - SKIPPED (no test file)"
fi

# Add more automated tests as needed...

echo "Test Suite Complete"
```

---

## Maintenance Notes

### Regular Health Checks

Run these commands periodically to verify system health:

```bash
# Quick health verification
curl -s "http://${ALB_DNS}/health/detailed" | jq '.checks.database.status, .checks.storage.storage_type, .checks.cookie_manager.status'

# S3 storage verification  
aws s3 ls s3://${S3_BUCKET}/ --recursive | wc -l

# Recent download jobs
curl -s "http://${ALB_DNS}/api/v1/jobs?per_page=5" -H "X-API-Key: ${ADMIN_KEY}" | jq '.total'

# Cookie system status (if enabled)
python scripts/upload-cookies.py --list-existing | grep -E "(Active Cookies|Cookie Count)" || echo "Cookies disabled or not configured"
```

### Log Monitoring

```bash
# Application logs
aws logs tail /ecs/youtube-downloader-dev-app --follow

# Worker logs  
aws logs tail /ecs/youtube-downloader-dev-worker --follow
```

---

## Security Notes for Cookie Testing

### Important Cookie Security Guidelines

1. **Never commit real cookie files to version control**
   - Use only test/dummy cookies for documentation examples
   - Real cookies contain sensitive authentication tokens
   - The `.gitignore` file excludes common cookie file patterns

2. **Cookie file handling best practices**
   - Store real cookies outside the repository
   - Use descriptive but non-sensitive names for test files
   - Rotate cookies regularly in production environments
   - Monitor cookie expiration dates and update proactively

3. **Testing with production cookies**
   - Copy real cookies to a secure location outside the repo
   - Use the `--validate-only` flag first to test without uploading
   - Test cookie functionality in a staging environment before production
   - Always verify cookie upload success with the verification steps

4. **Environment variables for cookie testing**

   ```bash
   export COOKIE_S3_BUCKET="youtube-downloader-dev-secure-cookies-xxxxx"
   export COOKIE_ENCRYPTION_KEY="your-encryption-key-here"
   export AWS_REGION="us-east-1"
   ```

---

**Last Updated:** January 9, 2025  
**Test Suite Version:** 1.1  
**Compatible with:** YouTube Downloader Service v1.0 with Cookie Management
