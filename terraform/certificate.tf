# Certificate with automatic Route 53 validation
resource "aws_acm_certificate" "app" {
  domain_name       = "snipethedip.com"
  subject_alternative_names = ["*.snipethedip.com"]
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Automatic validation records
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
  zone_id         = aws_route53_zone.main.zone_id
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for record in aws_route53_record.app_validation : record.fqdn]

  timeouts {
    create = "10m"
  }
}

# Use the terraform-managed certificate
locals {
  certificate_arn = aws_acm_certificate_validation.app.certificate_arn
}