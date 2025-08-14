output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.repo.repository_url
}

output "github_actions_role_arn" {
  description = "GitHub Actions IAM role ARN"
  value       = aws_iam_role.gha_ecr_push.arn
}

output "openai_secret_arn" {
  description = "OpenAI API key secret ARN"
  value       = aws_secretsmanager_secret.openai_key.arn
}

output "vantage_secret_arn" {
  description = "Vantage API key secret ARN"
  value       = aws_secretsmanager_secret.vantage_key.arn
}

output "app_url" {
  description = "Application URL"
  value       = "http://${aws_lb.main.dns_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.main.dns_name
} 