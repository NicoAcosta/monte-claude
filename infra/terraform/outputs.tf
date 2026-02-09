output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.main.dns_name
}

output "alb_zone_id" {
  description = "Route 53 zone ID of the ALB (for alias records)"
  value       = aws_lb.main.zone_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.postgres.port
}

output "game_api_instance_id" {
  description = "EC2 instance ID for Game API"
  value       = aws_instance.game_api.id
}

output "data_api_instance_id" {
  description = "EC2 instance ID for Data API"
  value       = aws_instance.data_api.id
}

output "ecr_game_repository_url" {
  description = "ECR repository URL for Game API image"
  value       = aws_ecr_repository.game_api.repository_url
}

output "ecr_data_repository_url" {
  description = "ECR repository URL for Data API image"
  value       = aws_ecr_repository.data_api.repository_url
}

output "nat_instance_public_ip" {
  description = "Public IP of the NAT instance"
  value       = aws_instance.nat.public_ip
}
