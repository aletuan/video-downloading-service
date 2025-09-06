# Storage Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "youtube-downloader"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# S3 Configuration
variable "enable_versioning" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = false  # Disabled for development cost optimization
}

variable "enable_lifecycle_management" {
  description = "Enable S3 lifecycle management to optimize costs"
  type        = bool
  default     = true  # Enabled to manage storage costs
}

variable "enable_access_logging" {
  description = "Enable S3 access logging"
  type        = bool
  default     = false  # Disabled for development
}

# CORS Configuration
variable "enable_cors" {
  description = "Enable CORS configuration for direct uploads"
  type        = bool
  default     = false  # Disabled for development (uploads go through API)
}

variable "cors_allowed_origins" {
  description = "List of allowed origins for CORS"
  type        = list(string)
  default     = ["*"]
}

# CloudFront Configuration
variable "enable_cloudfront" {
  description = "Enable CloudFront CDN"
  type        = bool
  default     = false  # Disabled for development cost optimization
}

variable "cloudfront_price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100"  # Use only North America and Europe edges
  
  validation {
    condition = contains([
      "PriceClass_All",
      "PriceClass_200", 
      "PriceClass_100"
    ], var.cloudfront_price_class)
    error_message = "Price class must be PriceClass_All, PriceClass_200, or PriceClass_100."
  }
}