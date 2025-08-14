variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "project_name" {
  type    = string
  default = "stock-options-strategy-api"
}

variable "environment" {
  type    = string
  default = "prod"
}

# GitHub repo for OIDC (owner and repo name)
variable "gh_owner" {
  type = string
}

variable "gh_repo" {
  type = string
}

# Your OpenAI API key (stored in Secrets Manager; used at runtime)
variable "openai_api_key" {
  description = "OpenAI API key for AI analysis"
  type        = string
  sensitive   = true
}

variable "vantage_api_key" {
  description = "Alpha Vantage API key for stock data"
  type        = string
  sensitive   = true
} 