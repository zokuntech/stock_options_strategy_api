#!/bin/bash

echo "🚨 CRITICAL: Cleaning up Terraform state files from git"
echo "This will remove sensitive state files from git history"

# Remove state files from git tracking
echo "Removing state files from git tracking..."
git rm --cached terraform.tfstate
git rm --cached terraform.tfstate.backup
git rm --cached terraform/terraform.tfstate
git rm --cached terraform/terraform.tfstate.backup
git rm --cached terraform/tfplan
git rm --cached terraform/.terraform.lock.hcl
git rm --cached terraform/terraform.tfvars

# Remove .terraform directory if it exists
if [ -d "terraform/.terraform" ]; then
    echo "Removing .terraform directory..."
    rm -rf terraform/.terraform
fi

echo "✅ State files removed from git tracking"
echo "⚠️  IMPORTANT: You need to set up remote state storage!"
echo ""
echo "Next steps:"
echo "1. Set up S3 backend for Terraform state"
echo "2. Run: terraform init -migrate-state"
echo "3. Commit the .gitignore changes"
echo ""
echo "Run this script with: bash cleanup_terraform_state.sh"
