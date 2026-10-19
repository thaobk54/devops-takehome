variable "zone_id" {
  description = "Cloudflare zone ID of example.com"
  type        = string
  default     = "0123456789abcdef0123456789abcdef" # placeholder - validate-only exercise
}

variable "origin_hostname" {
  description = "Origin the proxied record points to (e.g. the AWS ALB / CloudFront-less origin)"
  type        = string
  default     = "quote-api-alb-123456.ap-southeast-1.elb.amazonaws.com"
}

variable "legacy_record_id" {
  description = "ID of the manually created DNS record being adopted (from the Cloudflare API/dashboard)"
  type        = string
  default     = "fedcba9876543210fedcba9876543210"
}

variable "static_cache_ttl_seconds" {
  description = "Edge TTL for static assets (fingerprinted file names => safe to cache long)"
  type        = number
  default     = 2592000 # 30 days
}
