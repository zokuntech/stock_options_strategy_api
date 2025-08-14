resource "aws_secretsmanager_secret" "openai_key" {
  name = "${var.project_name}/${var.environment}/OPENAI_API_KEY"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "vantage_key" {
  name = "${var.project_name}/${var.environment}/VANTAGE_API_KEY"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret_version" "openai_key" {
  secret_id     = aws_secretsmanager_secret.openai_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret_version" "vantage_key" {
  secret_id     = aws_secretsmanager_secret.vantage_key.id
  secret_string = var.vantage_api_key
} 