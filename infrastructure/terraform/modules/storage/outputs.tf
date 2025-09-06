# Storage Module Outputs

# S3 Bucket Information
output "s3_bucket_id" {
  description = "S3 bucket ID"
  value       = aws_s3_bucket.videos.id
}

output "s3_bucket_name" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.videos.bucket
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.videos.arn
}

output "s3_bucket_domain_name" {
  description = "S3 bucket domain name"
  value       = aws_s3_bucket.videos.bucket_domain_name
}

output "s3_bucket_regional_domain_name" {
  description = "S3 bucket regional domain name"
  value       = aws_s3_bucket.videos.bucket_regional_domain_name
}

output "s3_bucket_hosted_zone_id" {
  description = "S3 bucket hosted zone ID"
  value       = aws_s3_bucket.videos.hosted_zone_id
}

output "s3_bucket_region" {
  description = "S3 bucket region"
  value       = data.aws_region.current.name
}

# CloudFront Information (if enabled)
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.videos[0].id : null
}

output "cloudfront_distribution_arn" {
  description = "CloudFront distribution ARN"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.videos[0].arn : null
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.videos[0].domain_name : null
}

output "cloudfront_hosted_zone_id" {
  description = "CloudFront distribution hosted zone ID"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.videos[0].hosted_zone_id : null
}

# Access Logs Bucket (if enabled)
output "access_logs_bucket_name" {
  description = "Access logs bucket name"
  value       = var.enable_access_logging ? aws_s3_bucket.access_logs[0].bucket : null
}

output "access_logs_bucket_arn" {
  description = "Access logs bucket ARN"
  value       = var.enable_access_logging ? aws_s3_bucket.access_logs[0].arn : null
}

# Systems Manager Parameters
output "s3_bucket_name_parameter" {
  description = "Systems Manager parameter name for S3 bucket name"
  value       = aws_ssm_parameter.s3_bucket_name.name
}

output "s3_bucket_region_parameter" {
  description = "Systems Manager parameter name for S3 bucket region"
  value       = aws_ssm_parameter.s3_bucket_region.name
}

output "cloudfront_domain_parameter" {
  description = "Systems Manager parameter name for CloudFront domain"
  value       = var.enable_cloudfront ? aws_ssm_parameter.cloudfront_domain[0].name : null
}

# Configuration Summary
output "storage_configuration" {
  description = "Storage configuration summary"
  value = {
    bucket_name       = aws_s3_bucket.videos.bucket
    region           = data.aws_region.current.name
    versioning       = var.enable_versioning
    lifecycle        = var.enable_lifecycle_management
    cloudfront       = var.enable_cloudfront
    access_logging   = var.enable_access_logging
    cors_enabled     = var.enable_cors
  }
}