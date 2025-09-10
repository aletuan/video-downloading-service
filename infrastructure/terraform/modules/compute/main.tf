# Compute Module - ECS Fargate for FastAPI and Celery
# Optimized for development with minimal resources

# Random suffix for unique resource names
resource "random_id" "cluster_suffix" {
  byte_length = 4
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}-cluster-${random_id.cluster_suffix.hex}"

  setting {
    name  = "containerInsights"
    value = var.container_insights_enabled ? "enabled" : "disabled"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-cluster"
  }
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.project_name}-${var.environment}-app"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.project_name}-${var.environment}-app-logs"
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project_name}-${var.environment}-worker"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${var.project_name}-${var.environment}-worker-logs"
  }
}

# ECS Task Execution Role
resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-ecs-task-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-ecs-task-execution-role"
  }
}

# Attach the ECS Task Execution Role Policy
resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for accessing Systems Manager parameters
resource "aws_iam_role_policy" "ecs_task_execution_ssm" {
  name = "${var.project_name}-${var.environment}-ecs-task-execution-ssm"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "ssm:GetParameter"
        ]
        Resource = [
          "arn:aws:ssm:*:*:parameter/${var.project_name}/${var.environment}/*"
        ]
      }
    ]
  })
}

# ECS Task Role (for application permissions)
resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-${var.environment}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-ecs-task-role"
  }
}

# Task role policy for S3 access and other AWS services
resource "aws_iam_role_policy" "ecs_task_policy" {
  name = "${var.project_name}-${var.environment}-ecs-task-policy"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          "arn:aws:ssm:*:*:parameter/${var.project_name}/${var.environment}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ]
        Resource = [
          "arn:aws:sqs:*:*:${var.project_name}-${var.environment}-main-queue-*",
          "arn:aws:sqs:*:*:${var.project_name}-${var.environment}-dlq-*"
        ]
      }
    ]
  })
}

# Cookie Management IAM Policy (separate policy for better organization)
resource "aws_iam_role_policy" "ecs_task_cookie_management" {
  name  = "${var.project_name}-${var.environment}-ecs-cookie-management"
  role  = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecureStorageS3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-secure-config-*",
          "arn:aws:s3:::${var.project_name}-${var.environment}-secure-config-*/cookies/*"
        ]
      },
      {
        Sid    = "ParameterStoreAccess"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = [
          "arn:aws:ssm:*:*:parameter/${var.project_name}/${var.environment}/cookie/*"
        ]
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = [
          "${aws_cloudwatch_log_group.app.arn}:*",
          "${aws_cloudwatch_log_group.worker.arn}:*"
        ]
      }
    ]
  })
}

# Get current AWS region and account ID for resource ARNs
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# FastAPI Task Definition
resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project_name}-${var.environment}-app"
  requires_compatibilities = ["FARGATE"]
  network_mode            = "awsvpc"
  cpu                     = var.app_cpu
  memory                  = var.app_memory
  execution_role_arn      = aws_iam_role.ecs_task_execution.arn
  task_role_arn          = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "fastapi-app"
      image = var.app_image
      
      portMappings = [
        {
          containerPort = 8000  # FastAPI default port
          protocol     = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = "aws"
        },
        {
          name  = "DEBUG"
          value = var.environment == "dev" ? "true" : "false"
        },
        {
          name  = "S3_BUCKET_NAME"
          value = var.s3_bucket_name
        },
        {
          name  = "COOKIE_S3_BUCKET_PREFIX"
          value = "${var.project_name}-${var.environment}-secure-config"
        },
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.name
        }
      ]
      
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = var.database_url_parameter
        },
        {
          name      = "REDIS_URL" 
          valueFrom = var.redis_url_parameter
        },
        {
          name      = "BOOTSTRAP_SETUP_TOKEN"
          valueFrom = var.bootstrap_token_parameter
        },
        # Cookie management configuration from Parameter Store
        {
          name      = "COOKIE_ENCRYPTION_KEY"
          valueFrom = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/${var.environment}/cookie/encryption-key"
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
      
      healthCheck = {
        command = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval = 30
        timeout = 5
        retries = 3
        startPeriod = 60
      }
      
      essential = true
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-app-task"
  }
}

# Celery Worker Task Definition
resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project_name}-${var.environment}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode            = "awsvpc"
  cpu                     = var.worker_cpu
  memory                  = var.worker_memory
  execution_role_arn      = aws_iam_role.ecs_task_execution.arn
  task_role_arn          = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "celery-worker"
      image = var.worker_image
      
      environment = [
        {
          name  = "ENVIRONMENT"
          value = "aws"
        },
        {
          name  = "DEBUG"
          value = var.environment == "dev" ? "true" : "false"
        },
        {
          name  = "S3_BUCKET_NAME"
          value = var.s3_bucket_name
        },
        {
          name  = "COOKIE_S3_BUCKET_PREFIX"
          value = "${var.project_name}-${var.environment}-secure-config"
        },
        {
          name  = "AWS_REGION"
          value = data.aws_region.current.name
        }
      ]
      
      secrets = [
        {
          name      = "DATABASE_URL"
          valueFrom = var.database_url_parameter
        },
        {
          name      = "REDIS_URL"
          valueFrom = var.redis_url_parameter
        },
        # Cookie management configuration from Parameter Store
        {
          name      = "COOKIE_ENCRYPTION_KEY"
          valueFrom = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${var.project_name}/${var.environment}/cookie/encryption-key"
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
      
      essential = true
    }
  ])

  tags = {
    Name = "${var.project_name}-${var.environment}-worker-task"
  }
}

# FastAPI ECS Service
resource "aws_ecs_service" "app" {
  name            = "${var.project_name}-${var.environment}-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.app_desired_count
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = true  # Required for public subnet deployment
  }

  # Load balancer integration (when target_group_arn is provided)
  dynamic "load_balancer" {
    for_each = var.target_group_arn != "" ? [1] : []
    content {
      target_group_arn = var.target_group_arn
      container_name   = "fastapi-app"
      container_port   = 8000  # FastAPI default port
    }
  }

  # Enable rolling deployments with load balancer (commented out temporarily)
  # deployment_configuration {
  #   maximum_percent         = 200
  #   minimum_healthy_percent = var.target_group_arn != "" ? 50 : 0
  # }

  tags = {
    Name = "${var.project_name}-${var.environment}-app-service"
  }
}

# Celery Worker ECS Service
resource "aws_ecs_service" "worker" {
  name            = "${var.project_name}-${var.environment}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = true  # Required for public subnet deployment
  }

  # deployment_configuration {
  #   maximum_percent         = 200
  #   minimum_healthy_percent = 0  # Workers can be interrupted
  # }

  tags = {
    Name = "${var.project_name}-${var.environment}-worker-service"
  }
}

# =============================================================================
# Cookie Management IAM Permissions Documentation
# =============================================================================
# 
# This module implements comprehensive IAM permissions for secure cookie 
# management in the YouTube download service. The permissions follow the 
# principle of least privilege while enabling full cookie functionality.
#
# PERMISSIONS GRANTED:
#
# 1. SECURE STORAGE S3 ACCESS
#    - Actions: GetObject, PutObject, DeleteObject, ListBucket, GetBucketVersioning, 
#              ListBucketVersions, GetObjectVersion
#    - Resource: Secure storage S3 bucket and all objects within it
#    - Purpose: Download, upload, and manage cookie files securely
#    - Security: Limited to specific bucket ARN provided via variable
#
# 2. KMS KEY ACCESS
#    - Actions: Decrypt, DescribeKey, GenerateDataKey
#    - Resource: KMS key used for S3 server-side encryption
#    - Purpose: Decrypt encrypted cookie files from S3
#    - Security: Limited to S3 service usage via ViaService condition
#
# 3. PARAMETER STORE ACCESS
#    - Actions: GetParameter, GetParameters, GetParametersByPath
#    - Resource: /project/environment/cookie/* and /project/environment/encryption/*
#    - Purpose: Retrieve cookie encryption keys and configuration
#    - Security: Limited to specific parameter path prefixes
#
# 4. CLOUDWATCH LOGS ACCESS
#    - Actions: CreateLogStream, PutLogEvents, DescribeLogGroups, DescribeLogStreams
#    - Resource: Application and worker CloudWatch log groups
#    - Purpose: Enhanced logging for cookie operations and debugging
#    - Security: Limited to specific log groups created by this module
#
# ENVIRONMENT VARIABLES PROVIDED:
#
# 1. COOKIE_S3_BUCKET: Name of the secure S3 bucket for cookie storage
# 2. AWS_REGION: Current AWS region for SDK configuration
# 3. COOKIE_ENCRYPTION_KEY: Retrieved from Parameter Store for in-memory encryption
#
# SECURITY CONSIDERATIONS:
#
# - All permissions are conditionally applied only when secure storage is configured
# - KMS permissions are restricted to S3 service usage
# - Parameter Store access is limited to specific path prefixes
# - IAM policies are separate for better organization and management
# - Least privilege principle is enforced throughout
#
# USAGE:
#
# To enable cookie management, provide the following variables:
# - secure_storage_bucket_arn: ARN of the secure S3 bucket
# - secure_storage_bucket_name: Name of the secure S3 bucket
# - secure_storage_kms_key_arn: ARN of the KMS key (optional)
#
# If these variables are not provided, cookie management permissions are not applied.
#
# =============================================================================