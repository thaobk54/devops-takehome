# Part 5b - DNS + cache rules for quote-api.example.com

# Proxied (orange-cloud) record: traffic goes through Cloudflare's CDN/WAF and
# the origin address is not exposed in DNS.
resource "cloudflare_dns_record" "quote_api" {
  zone_id = var.zone_id
  name    = "quote-api.example.com"
  type    = "CNAME"
  content = var.origin_hostname
  proxied = true
  ttl     = 1 # 1 = "automatic"; required for proxied records
  comment = "Managed by Terraform (devops-takehome) - do not edit in the dashboard"
}

# --- adopting a manually created record -------------------------------------
# Someone created status.example.com by hand. The import block brings it under
# Terraform on the next plan/apply WITHOUT recreating it (no DNS blip).
# Workflow: `terraform plan` shows "will be imported" + any drift; align the
# resource below until the plan shows no changes, apply, then this block can
# stay (it is idempotent) or be removed.
import {
  to = cloudflare_dns_record.status_legacy
  id = "${var.zone_id}/${var.legacy_record_id}"
}

resource "cloudflare_dns_record" "status_legacy" {
  zone_id = var.zone_id
  name    = "status.example.com"
  type    = "CNAME"
  content = "statuspage.example-hosted.io"
  proxied = false
  ttl     = 300
  comment = "Adopted into Terraform via import block (was created manually)"
}

# --- cache rules ------------------------------------------------------------------
# One ruleset per zone & phase. Rules are evaluated in order and LATER matching
# rules override earlier ones, so the API bypass goes last as the final word.
resource "cloudflare_ruleset" "quote_api_cache" {
  zone_id     = var.zone_id
  name        = "quote-api cache rules"
  description = "Cache static assets aggressively, never cache the API"
  kind        = "zone"
  phase       = "http_request_cache_settings"

  rules = [
    {
      ref         = "cache_static_assets"
      description = "Static assets: cache at the edge for 30d, in browsers for 1d"
      expression  = <<-EOT
        (http.host eq "quote-api.example.com" and
         http.request.uri.path.extension in {"js" "css" "png" "jpg" "jpeg" "gif" "svg" "webp" "avif" "ico" "woff" "woff2" "ttf"})
      EOT
      action      = "set_cache_settings"
      action_parameters = {
        cache = true
        edge_ttl = {
          mode    = "override_origin"
          default = var.static_cache_ttl_seconds
        }
        browser_ttl = {
          mode    = "override_origin"
          default = 86400
        }
      }
    },
    {
      ref         = "bypass_api"
      description = "Dynamic API responses must never be served from cache"
      expression  = "(http.host eq \"quote-api.example.com\" and starts_with(http.request.uri.path, \"/api/\"))"
      action      = "set_cache_settings"
      action_parameters = {
        cache = false
      }
    },
  ]
}
