# Route 53 Hosted Zone for snipethedip.com
resource "aws_route53_zone" "main" {
  name = "snipethedip.com"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# DNS Records for the domain
resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.snipethedip.com"
  type    = "CNAME"
  ttl     = 300
  records = [aws_lb.main.dns_name]
}

resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "app.snipethedip.com"
  type    = "CNAME"
  ttl     = 300
  records = ["d3bjg7e6h8jm1k.cloudfront.net"]  # Your CloudFront distribution
}

resource "aws_route53_record" "www" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "www.snipethedip.com"
  type    = "CNAME"
  ttl     = 300
  records = ["d3bjg7e6h8jm1k.cloudfront.net"]
}

# Root domain points to load balancer
resource "aws_route53_record" "root_alias" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "snipethedip.com"
  type    = "A"
  
  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# Nameservers output moved to outputs.tf
