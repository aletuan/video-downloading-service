# Random suffix for unique naming
resource "random_id" "alb_suffix" {
  byte_length = 4
}

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${substr(var.project_name, 0, 10)}-${var.environment}-alb-${random_id.alb_suffix.hex}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.subnet_ids

  enable_deletion_protection       = var.enable_deletion_protection
  enable_http2                     = var.enable_http2
  enable_cross_zone_load_balancing = var.enable_cross_zone_load_balancing
  idle_timeout                     = var.idle_timeout

  access_logs {
    enabled = false
    bucket  = ""
  }

  tags = merge(
    {
      Name        = "${var.project_name}-${var.environment}-alb"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

# Target Group for FastAPI Application
resource "aws_lb_target_group" "app" {
  name     = "${substr(var.project_name, 0, 8)}-${var.environment}-app-tg-${random_id.alb_suffix.hex}"
  port     = 80  # Use port 80 for nginx placeholder
  protocol = var.target_group_protocol
  vpc_id   = var.vpc_id

  target_type                       = "ip"
  deregistration_delay              = 300
  load_balancing_algorithm_type     = "round_robin"
  slow_start                        = 0
  protocol_version                  = "HTTP1"

  health_check {
    enabled             = var.health_check_enabled
    healthy_threshold   = var.healthy_threshold
    interval            = var.health_check_interval
    matcher             = "200"
    path                = "/"  # Use root path for nginx compatibility
    port                = "traffic-port"
    protocol            = var.target_group_protocol
    timeout             = var.health_check_timeout
    unhealthy_threshold = var.unhealthy_threshold
  }

  stickiness {
    enabled         = false
    type            = "lb_cookie"
    cookie_duration = 86400
  }

  tags = merge(
    {
      Name        = "${var.project_name}-${var.environment}-app-target-group"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )

  lifecycle {
    create_before_destroy = true
  }
}

# HTTP Listener (redirects to HTTPS if certificate is provided)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  # If certificate is provided, redirect HTTP to HTTPS
  # Otherwise, forward directly to target group
  dynamic "default_action" {
    for_each = var.certificate_arn != "" ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.app.arn
    }
  }

  tags = merge(
    {
      Name        = "${var.project_name}-${var.environment}-http-listener"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

# HTTPS Listener (only if certificate is provided)
resource "aws_lb_listener" "https" {
  count = var.certificate_arn != "" ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  tags = merge(
    {
      Name        = "${var.project_name}-${var.environment}-https-listener"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )
}

# Data source for current region
data "aws_region" "current" {}