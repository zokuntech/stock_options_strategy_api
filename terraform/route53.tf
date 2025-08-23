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

# Root domain redirect (optional)
resource "aws_route53_record" "root" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "snipethedip.com"
  type    = "A"
  ttl     = 300
  records = ["185.199.108.153"]  # GitHub Pages IP or your preferred redirect
}

# Output the nameservers
output "nameservers" {
  description = "Route 53 nameservers - add these to Namecheap"
  value       = aws_route53_zone.main.name_servers
}
