# Ingestion Lambda: fetches market data and writes it to raw/ in the lake.

# Created before the function, so Terraform (not Lambda) owns the log group and
# its retention, and the role never needs logs:CreateLogGroup.
resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "ingest_trust" {
  statement {
    sid     = "LambdaServiceAssumesRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingest" {
  name               = "battery-optimizer-ingest-lambda-role"
  description        = "Execution role of the battery-optimizer-ingest Lambda"
  assume_role_policy = data.aws_iam_policy_document.ingest_trust.json
}

data "aws_iam_policy_document" "ingest_access" {
  statement {
    sid       = "WriteOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:log-stream:*"]
  }
  statement {
    sid       = "WriteRawZoneOnly"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "battery-optimizer-ingest-access"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest_access.json
}

resource "aws_lambda_function" "ingest" {
  function_name = local.lambda_name
  description   = "Fetches elpris + SvK market data and lands it unchanged in raw/"
  role          = aws_iam_role.ingest.arn

  runtime       = "python3.12"
  architectures = ["x86_64"]
  handler       = "lambda_function.lambda_handler"
  memory_size   = 256
  timeout       = 120

  # Built by infra/lambda/build_lambda.py; the hash makes a code change visible in the plan.
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      LAKE_TARGET = "s3"
      LAKE_BUCKET = aws_s3_bucket.lake.id
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.ingest.name
  }

  # Log group and permissions exist before the first invocation.
  depends_on = [aws_cloudwatch_log_group.ingest, aws_iam_role_policy.ingest]
}
