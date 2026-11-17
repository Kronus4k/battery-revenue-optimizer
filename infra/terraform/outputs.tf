# Names only: no ARNs, so no account ID ends up in terminal output or logs.
output "lake_bucket_name" {
  value = aws_s3_bucket.lake.id
}

output "lambda_function_name" {
  value = aws_lambda_function.ingest.function_name
}

output "lambda_log_group" {
  value = aws_cloudwatch_log_group.ingest.name
}

output "airflow_role_name" {
  value = aws_iam_role.airflow.name
}
