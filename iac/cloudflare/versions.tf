terraform {
  required_version = ">= 1.7.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.28" # v5 schema: cloudflare_dns_record, attribute-style rules
    }
  }

  # Real setup: remote state with locking, e.g.
  # backend "s3" { bucket = "acme-tfstate" key = "cloudflare/quote-api.tfstate" use_lockfile = true }
}

# Auth comes from the CLOUDFLARE_API_TOKEN environment variable (scoped token:
# Zone.DNS:Edit + Zone.Cache Rules:Edit on this zone only). Never in code/state vars.
provider "cloudflare" {}
