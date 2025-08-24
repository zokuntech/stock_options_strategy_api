# Simple approach: Use existing certificate
# This avoids the for_each dependency issue

# Use your existing certificate
locals {
  certificate_arn = "arn:aws:acm:us-west-2:106383253452:certificate/f32eabfb-6b45-4b3d-856a-70327e1f109b"
}