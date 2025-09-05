output "alb_id" {
  description = "Application Load Balancer ID"
  value       = aws_lb.main.id
}

output "alb_arn" {
  description = "Application Load Balancer ARN"
  value       = aws_lb.main.arn
}

output "alb_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Application Load Balancer zone ID"
  value       = aws_lb.main.zone_id
}

output "alb_security_group_id" {
  description = "Security group ID used by ALB"
  value       = var.security_group_id
}

output "target_group_arn" {
  description = "Target group ARN"
  value       = aws_lb_target_group.app.arn
}

output "target_group_name" {
  description = "Target group name"
  value       = aws_lb_target_group.app.name
}

output "http_listener_arn" {
  description = "HTTP listener ARN"
  value       = aws_lb_listener.http.arn
}

output "https_listener_arn" {
  description = "HTTPS listener ARN (if certificate provided)"
  value       = var.certificate_arn != "" ? aws_lb_listener.https[0].arn : ""
}

output "alb_endpoint" {
  description = "ALB endpoint URL"
  value       = var.certificate_arn != "" ? "https://${aws_lb.main.dns_name}" : "http://${aws_lb.main.dns_name}"
}

output "health_check_path" {
  description = "Health check path configured"
  value       = var.health_check_path
}

output "load_balancer_name" {
  description = "Load balancer name"
  value       = aws_lb.main.name
}