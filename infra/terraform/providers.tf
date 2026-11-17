provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Every taggable resource gets the project tag, without repeating it.
  default_tags {
    tags = {
      project = "battery-optimizer"
    }
  }
}

# The account ID is only ever read at plan time, never written in code.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  lake_bucket = "battery-optimizer-lake-${var.bucket_suffix}"
  lambda_name = "battery-optimizer-ingest"
}

# Identity guard: warns in plan/apply if Terraform runs as anything other
# than the battery-optimizer SSO session in eu-north-1.
check "identity_and_region" {
  assert {
    condition     = strcontains(data.aws_caller_identity.current.arn, "assumed-role/AWSReservedSSO_AdministratorAccess_")
    error_message = "Terraform is not running as the AdministratorAccess SSO session (profile battery-optimizer)."
  }
  assert {
    condition     = data.aws_region.current.region == "eu-north-1"
    error_message = "Provider region is not eu-north-1."
  }
}
