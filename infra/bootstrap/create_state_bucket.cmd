@echo off
rem =============================================================================
rem create_state_bucket.cmd - ONE-TIME bootstrap of the Terraform state bucket
rem (run once per account, before the first terraform init)
rem
rem Why a script and not Terraform: Terraform cannot create the bucket that
rem stores its own state. Everything else is managed in infra/terraform/.
rem
rem Creates s3://battery-optimizer-tfstate-<suffix> in eu-north-1 with:
rem   - object ownership BucketOwnerEnforced (ACLs disabled)
rem   - all four public-access-block settings on
rem   - default encryption SSE-S3 (AES256)
rem   - versioning enabled (every state write is recoverable)
rem   - tag project=battery-optimizer
rem   - bucket policy: deny every s3:* request that is not over TLS
rem     (policy in state_bucket_policy.json next to this script; its
rem     __BUCKET__ placeholder is filled in at runtime)
rem
rem Nothing account-specific is in this file: the account ID is looked up at
rem runtime, used only for --expected-bucket-owner, and never printed.
rem
rem Safe to re-run: a bucket that already exists IN THIS ACCOUNT is reused and
rem its settings are re-applied. A name owned by another account stops the run.
rem
rem Usage (cmd, repo root, after: aws sso login --profile battery-optimizer):
rem   infra\bootstrap\create_state_bucket.cmd <suffix>
rem   suffix = lowercase letters and digits only, max 37 characters
rem =============================================================================
setlocal

set "PROFILE=battery-optimizer"
set "REGION=eu-north-1"
rem Explicit --profile on every call: it disables the environment credential
rem provider, so stray access keys in this window can never redirect these calls.
set "AWS=aws --profile %PROFILE% --region %REGION%"

rem ---- 1. Validate the suffix ------------------------------------------------
if "%~1"=="" (
  echo usage: %~nx0 ^<suffix^>   lowercase letters and digits only
  exit /b 2
)
rem findstr's [a-z] also matches most UPPERCASE letters (collation quirk),
rem so the allowed characters are listed explicitly.
echo %~1| findstr /r /x "[abcdefghijklmnopqrstuvwxyz0123456789]*" >nul
if errorlevel 1 (
  echo suffix must contain only lowercase letters and digits
  exit /b 2
)
set "BUCKET=battery-optimizer-tfstate-%~1"

rem ---- 2. Identity: who am I, and which account? -----------------------------
set "ACCOUNT_ID="
for /f "delims=" %%a in ('%AWS% sts get-caller-identity --query Account --output text 2^>nul') do set "ACCOUNT_ID=%%a"
if not defined ACCOUNT_ID (
  echo could not read the account id. Run: aws sso login --profile %PROFILE%
  exit /b 1
)
echo %ACCOUNT_ID%| findstr /r /x "[0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789][0123456789]" >nul
if errorlevel 1 (
  echo account id lookup returned something unexpected; stopping
  exit /b 1
)
echo identity OK (profile %PROFILE%, account id looked up, not shown)
set "OWNER=--expected-bucket-owner %ACCOUNT_ID%"

rem ---- 3. Create the bucket, or reuse it if it is already ours ---------------
%AWS% s3api head-bucket --bucket %BUCKET% %OWNER% >nul 2>&1
if errorlevel 1 goto :create
echo %BUCKET% already exists in this account: re-applying settings
goto :settings

:create
echo creating %BUCKET% in %REGION% ...
%AWS% s3api create-bucket --bucket %BUCKET% --create-bucket-configuration LocationConstraint=%REGION% --object-ownership BucketOwnerEnforced --output text >nul
if errorlevel 1 (
  echo create-bucket failed: name taken by another account, invalid name, or no permission
  exit /b 1
)

rem ---- 4. Settings (each step stops the script on failure) -------------------
:settings
set "STEP=public-access-block"
%AWS% s3api put-public-access-block --bucket %BUCKET% %OWNER% --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true || goto :fail

set "STEP=encryption SSE-S3"
%AWS% s3api put-bucket-encryption --bucket %BUCKET% %OWNER% --server-side-encryption-configuration "Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]" || goto :fail

set "STEP=versioning"
%AWS% s3api put-bucket-versioning --bucket %BUCKET% %OWNER% --versioning-configuration Status=Enabled || goto :fail

set "STEP=tags"
%AWS% s3api put-bucket-tagging --bucket %BUCKET% %OWNER% --tagging "TagSet=[{Key=project,Value=battery-optimizer}]" || goto :fail

set "STEP=bucket policy (deny non-TLS)"
rem Fill the bucket name into a TEMP copy of the committed policy; the
rem committed file never contains the name. Stop if any placeholder is left.
set "POLICY_TMP=%TEMP%\%BUCKET%-policy.json"
if exist "%POLICY_TMP%" del "%POLICY_TMP%"
powershell -NoProfile -Command "(Get-Content -Raw '%~dp0state_bucket_policy.json').Replace('__BUCKET__','%BUCKET%') | Set-Content -NoNewline -Encoding ascii '%POLICY_TMP%'" || goto :fail
if not exist "%POLICY_TMP%" goto :fail
findstr /c:"__BUCKET__" "%POLICY_TMP%" >nul && goto :fail
%AWS% s3api put-bucket-policy --bucket %BUCKET% %OWNER% --policy "file://%POLICY_TMP%" || goto :fail
del "%POLICY_TMP%"

rem ---- 5. Evidence: read every setting back from S3 --------------------------
echo.
echo === read back from S3 (expected value in brackets) ===
echo location   [eu-north-1]:
%AWS% s3api get-bucket-location --bucket %BUCKET% %OWNER% --query LocationConstraint --output text
echo ownership  [BucketOwnerEnforced]:
%AWS% s3api get-bucket-ownership-controls --bucket %BUCKET% %OWNER% --query "OwnershipControls.Rules[0].ObjectOwnership" --output text
echo public-access-block  [True True True True]:
%AWS% s3api get-public-access-block --bucket %BUCKET% %OWNER% --query "PublicAccessBlockConfiguration.[BlockPublicAcls,IgnorePublicAcls,BlockPublicPolicy,RestrictPublicBuckets]" --output text
echo encryption [AES256]:
%AWS% s3api get-bucket-encryption --bucket %BUCKET% %OWNER% --query "ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm" --output text
echo versioning [Enabled]:
%AWS% s3api get-bucket-versioning --bucket %BUCKET% %OWNER% --query Status --output text
echo tags       [project battery-optimizer]:
%AWS% s3api get-bucket-tagging --bucket %BUCKET% %OWNER% --query "TagSet[].[Key,Value]" --output text
echo policy     [Deny s3:* on bucket and bucket/* when aws:SecureTransport=false]:
%AWS% s3api get-bucket-policy --bucket %BUCKET% %OWNER% --query Policy --output text
echo.
echo done: %BUCKET%
echo next: terraform init -backend-config="bucket=%BUCKET%"   (from infra\terraform)
endlocal
exit /b 0

:fail
echo FAILED at step: %STEP%
if defined POLICY_TMP if exist "%POLICY_TMP%" del "%POLICY_TMP%"
exit /b 1
