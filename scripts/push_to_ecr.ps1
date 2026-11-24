param(
    [Parameter(Mandatory = $true)]
    [string]$Region,
    [string]$Repository = "fantasyiq-api",
    [string]$Profile
)

$ErrorActionPreference = "Stop"
# PowerShell 7 can promote native stderr text to a terminating error even when
# a CLI command's non-zero exit is an expected branch (for example, repo absent).
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$profileArgs = @()
if (-not [string]::IsNullOrWhiteSpace($Profile)) { $profileArgs = @("--profile", $Profile) }

$identityJson = aws @profileArgs sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) { throw "AWS CLI is not authenticated. Run aws configure or aws sso login first." }
$identity = $identityJson | ConvertFrom-Json
$accountId = $identity.Account
$registry = "$accountId.dkr.ecr.$Region.amazonaws.com"
$repositoryUri = "$registry/$Repository"

$stdoutFile = Join-Path $env:TEMP "fantasyiq-ecr-out.txt"
$stderrFile = Join-Path $env:TEMP "fantasyiq-ecr-err.txt"
$awsExe = (Get-Command aws -ErrorAction Stop).Source
$describeArgs = $profileArgs + @("ecr", "describe-repositories", "--repository-names", $Repository, "--region", $Region, "--output", "json")
$describe = Start-Process -FilePath $awsExe -ArgumentList $describeArgs -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
$repositoryExists = $describe.ExitCode -eq 0
Remove-Item $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
if (-not $repositoryExists) {
    aws @profileArgs ecr create-repository --repository-name $Repository --image-scanning-configuration scanOnPush=true --region $Region
    if ($LASTEXITCODE -ne 0) { throw "Could not create the ECR repository." }
}

aws @profileArgs ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE -ne 0) { throw "Could not authenticate Docker to ECR." }

docker build -t "${Repository}:latest" .
if ($LASTEXITCODE -ne 0) { throw "Docker build failed." }
docker tag "${Repository}:latest" "${repositoryUri}:latest"
docker push "${repositoryUri}:latest"
if ($LASTEXITCODE -ne 0) { throw "Could not push image to ECR." }

Write-Host "Image pushed successfully: ${repositoryUri}:latest"
Write-Host "In AWS App Runner, choose Container registry > Amazon ECR, select this image, and use port 8000."
