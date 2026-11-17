# Exact pins, each released at least 14 days before adoption (checked 2026-11-17):
#   terraform     1.11.4  released 2025-04-09 (HashiCorp releases API)
#   hashicorp/aws 6.71.0  published 2026-10-28 (Terraform registry)
terraform {
  required_version = "1.11.4"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.71.0"
    }
  }
}
