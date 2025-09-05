# Storage Module - S3 for video and transcript storage
# Optimized for development with basic features

# Random suffix for unique bucket name
resource "random_id" "bucket_suffix" {
  byte_length = 8
}

# S3 Bucket for video storage
resource "aws_s3_bucket" "videos" {
  bucket = "${var.project_name}-${var.environment}-videos-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-videos"
    Environment = var.environment
    Purpose     = "video-storage"
  }
}

# S3 Bucket Versioning
resource "aws_s3_bucket_versioning" "videos" {
  bucket = aws_s3_bucket.videos.id
  
  versioning_configuration {
    status = var.enable_versioning ? "Enabled" : "Disabled"
  }
}

# S3 Bucket Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "videos" {
  bucket = aws_s3_bucket.videos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# S3 Bucket Public Access Block (secure by default)
resource "aws_s3_bucket_public_access_block" "videos" {
  bucket = aws_s3_bucket.videos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket Lifecycle Configuration
resource "aws_s3_bucket_lifecycle_configuration" "videos" {
  count  = var.enable_lifecycle_management ? 1 : 0
  bucket = aws_s3_bucket.videos.id

  rule {
    id     = "video_lifecycle"
    status = "Enabled"

    # Transition to Infrequent Access after 30 days
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    # Transition to Glacier after 90 days
    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    # Delete old versions after 30 days (if versioning is enabled)
    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    # Delete incomplete multipart uploads after 7 days
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# S3 Bucket CORS Configuration (for direct uploads if needed)
resource "aws_s3_bucket_cors_configuration" "videos" {
  count  = var.enable_cors ? 1 : 0
  bucket = aws_s3_bucket.videos.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = var.cors_allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# S3 Bucket Logging (optional, for access logs)
resource "aws_s3_bucket" "access_logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = "${var.project_name}-${var.environment}-access-logs-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-${var.environment}-access-logs"
    Environment = var.environment
    Purpose     = "access-logging"
  }
}

resource "aws_s3_bucket_public_access_block" "access_logs" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.access_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "videos" {
  count  = var.enable_access_logging ? 1 : 0
  bucket = aws_s3_bucket.videos.id

  target_bucket = aws_s3_bucket.access_logs[0].id
  target_prefix = "access-logs/"
}

# CloudFront Distribution (optional, for production)
resource "aws_cloudfront_distribution" "videos" {
  count = var.enable_cloudfront ? 1 : 0

  origin {
    domain_name              = aws_s3_bucket.videos.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.videos[0].id
    origin_id                = "S3-${aws_s3_bucket.videos.bucket}"
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-${aws_s3_bucket.videos.bucket}"
    compress               = true
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  price_class = var.cloudfront_price_class

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-cdn"
    Environment = var.environment
  }
}

# CloudFront Origin Access Control (for S3 access)
resource "aws_cloudfront_origin_access_control" "videos" {
  count = var.enable_cloudfront ? 1 : 0

  name                              = "${var.project_name}-${var.environment}-oac"
  description                       = "OAC for ${var.project_name} ${var.environment} S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 Bucket Policy for CloudFront access
resource "aws_s3_bucket_policy" "videos_cloudfront" {
  count  = var.enable_cloudfront ? 1 : 0
  bucket = aws_s3_bucket.videos.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontAccess"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.videos.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.videos[0].arn
          }
        }
      }
    ]
  })
}

# Systems Manager Parameters for S3 configuration
resource "aws_ssm_parameter" "s3_bucket_name" {
  name        = "/${var.project_name}/${var.environment}/storage/s3_bucket_name"
  description = "S3 bucket name for video storage"
  type        = "String"
  value       = aws_s3_bucket.videos.bucket

  tags = {
    Name = "${var.project_name}-${var.environment}-s3-bucket-name"
  }
}

resource "aws_ssm_parameter" "s3_bucket_region" {
  name        = "/${var.project_name}/${var.environment}/storage/s3_bucket_region"
  description = "S3 bucket region"
  type        = "String"
  value       = data.aws_region.current.name

  tags = {
    Name = "${var.project_name}-${var.environment}-s3-bucket-region"
  }
}

resource "aws_ssm_parameter" "cloudfront_domain" {
  count       = var.enable_cloudfront ? 1 : 0
  name        = "/${var.project_name}/${var.environment}/storage/cloudfront_domain"
  description = "CloudFront distribution domain name"
  type        = "String"
  value       = aws_cloudfront_distribution.videos[0].domain_name

  tags = {
    Name = "${var.project_name}-${var.environment}-cloudfront-domain"
  }
}

# Data source for current AWS region
data "aws_region" "current" {}