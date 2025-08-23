# Simple approach: Create a certificate for a custom domain
# You'll need to own a domain name for this to work

# If you have a domain name, uncomment and update these resources:
/*
resource "aws_acm_certificate" "app" {
  domain_name       = "api.yourdomain.com"  # Replace with your domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_route53_record" "app_validation" {
  for_each = {
    for dvo in aws_acm_certificate.app.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = "YOUR_HOSTED_ZONE_ID"  # Replace with your Route53 zone ID
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for record in aws_route53_record.app_validation : record.fqdn]

  timeouts {
    create = "10m"
  }
}
*/

# For now, we'll use a placeholder certificate ARN
# You'll need to create a certificate manually in ACM and update this
locals {
  # Replace this with your actual certificate ARN from AWS Console
  certificate_arn = "arn:aws:acm:us-west-2:106383253452:certificate/7bba664f-317e-454e-953a-c90ddfeeb358"
}
