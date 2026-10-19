output "quote_api_fqdn" {
  value = cloudflare_dns_record.quote_api.name
}

output "cache_ruleset_id" {
  value = cloudflare_ruleset.quote_api_cache.id
}
