# S3 backend for Terraform state - SECURE and SHARED
# Temporarily disabled due to lock issues
# terraform {
#   backend "s3" {
#     bucket         = "stock-options-strategy-api-terraform-state"
#     key            = "terraform.tfstate"
#     region         = "us-west-2"
#     encrypt        = true
#     dynamodb_table = "stock-options-strategy-api-terraform-locks"
#   }
# }
