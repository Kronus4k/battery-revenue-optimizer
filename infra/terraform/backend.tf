# Remote state in the project's own bucket (created by infra/bootstrap/create_state_bucket.cmd),
# never Slussen's. Native S3 locking (use_lockfile), no DynamoDB table.
# Bucket and profile are supplied at init time, not committed:
#   terraform init -backend-config="bucket=battery-optimizer-tfstate-<suffix>" -backend-config="profile=battery-optimizer"
terraform {
  backend "s3" {
    key          = "battery-optimizer/terraform.tfstate"
    region       = "eu-north-1"
    use_lockfile = true
    encrypt      = true
  }
}
