resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "gha_assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.gh_owner}/${var.gh_repo}:*"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gha_ecr_push" {
  name               = "${var.project_name}-${var.environment}-gha-ecr-push"
  assume_role_policy = data.aws_iam_policy_document.gha_assume_role.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "gha_ecr_policy" {
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:ListImages",
      "ecr:PutImage",
      "ecr:UploadLayerPart"
    ]
    resources = [aws_ecr_repository.repo.arn]
  }
}

resource "aws_iam_policy" "gha_ecr" {
  name   = "${var.project_name}-${var.environment}-gha-ecr"
  policy = data.aws_iam_policy_document.gha_ecr_policy.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "gha_ecr_attach" {
  role       = aws_iam_role.gha_ecr_push.name
  policy_arn = aws_iam_policy.gha_ecr.arn
}

# ECS deployment permissions for GitHub Actions
data "aws_iam_policy_document" "gha_ecs_policy" {
  statement {
    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
      "ecs:UpdateService",
      "ecs:DescribeServices",
      "ecs:ListTasks",
      "ecs:DescribeTasks"
    ]
    resources = ["*"]
  }
  
  statement {
    actions = [
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::*:role/${var.project_name}-${var.environment}-ecs-execution",
      "arn:aws:iam::*:role/${var.project_name}-${var.environment}-ecs-task"
    ]
  }
}

resource "aws_iam_policy" "gha_ecs" {
  name   = "${var.project_name}-${var.environment}-gha-ecs"
  policy = data.aws_iam_policy_document.gha_ecs_policy.json

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "gha_ecs_attach" {
  role       = aws_iam_role.gha_ecr_push.name
  policy_arn = aws_iam_policy.gha_ecs.arn
} 