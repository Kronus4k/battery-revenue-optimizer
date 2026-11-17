variable "aws_profile" {
  description = "AWS CLI profile (SSO). An explicit profile also ignores stray AWS_* key env vars."
  type        = string
  default     = "battery-optimizer"
}

variable "region" {
  description = "AWS region for every resource."
  type        = string
  default     = "eu-north-1"
}

variable "bucket_suffix" {
  description = "Suffix that makes the global lake bucket name unique: battery-optimizer-lake-<suffix>. Set in terraform.tfvars (git-ignored)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{1,40}$", var.bucket_suffix))
    error_message = "bucket_suffix: lowercase letters and digits only, max 40."
  }
}

variable "lake_versioning_enabled" {
  description = "S3 versioning on the lake bucket. On: a re-fetch or source revision keeps the previous bytes as an older version."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retention of the Lambda's CloudWatch log group."
  type        = number
  default     = 30

  validation {
    # The values CloudWatch Logs accepts (0 = never expire is deliberately excluded).
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.log_retention_days)
    error_message = "log_retention_days must be a CloudWatch Logs retention value (never-expire is not allowed)."
  }
}

variable "lambda_zip_path" {
  description = "Zip built by infra/lambda/build_lambda.py (relative to infra/terraform)."
  type        = string
  default     = "../../build/lambda/battery-optimizer-ingest.zip"
}
