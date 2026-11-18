# Role that local Airflow (and the laptop scripts) assume from the SSO session
# (decision A1). In production the same policy would sit on the compute running
# Airflow (workload identity); only the trust policy would change.

data "aws_iam_policy_document" "airflow_trust" {
  statement {
    sid     = "AdministratorAccessSsoSessionOnly"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account_id}:root"]
    }
    # Only the AdministratorAccess permission set's role in THIS account.
    # Its real path is /aws-reserved/sso.amazonaws.com/<region>/ (checked read-only).
    # Becomes the scoped permission set once that exists (Day 4 security item).
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = ["arn:aws:iam::${local.account_id}:role/aws-reserved/sso.amazonaws.com/*/AWSReservedSSO_AdministratorAccess_*"]
    }
  }
}

resource "aws_iam_role" "airflow" {
  name                 = "battery-optimizer-airflow"
  description          = "Airflow tasks, assumed from the AdministratorAccess SSO session"
  assume_role_policy   = data.aws_iam_policy_document.airflow_trust.json
  max_session_duration = 3600 # role chaining from SSO caps sessions at 1 h anyway
}

data "aws_iam_policy_document" "airflow_access" {
  statement {
    sid       = "InvokeIngestLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    # Built from known pieces, not aws_lambda_function.ingest.arn: a reference to
    # the function defers this document to apply time whenever the code changes,
    # and the plan then shows a false update of the policy.
    resources = ["arn:aws:lambda:${data.aws_region.current.region}:${local.account_id}:function:${local.lambda_name}"]
  }
  statement {
    sid       = "ListRawZoneOnly"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*"] # also matches "raw/" itself (* = zero or more characters)
    }
  }
  statement {
    sid       = "ReadRawZoneOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*"]
  }
}

resource "aws_iam_role_policy" "airflow" {
  name   = "battery-optimizer-airflow-access"
  role   = aws_iam_role.airflow.id
  policy = data.aws_iam_policy_document.airflow_access.json
}
