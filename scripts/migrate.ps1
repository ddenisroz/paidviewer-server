param(
    [string]$EnvFile = "/srv/paidviewer/env/.env",
    [string]$DataDir = "/srv/paidviewer"
)

Write-Host "== Paidviewer server bootstrap ==" -ForegroundColor Cyan
Write-Host "Data dir: $DataDir"
Write-Host "Env file: $EnvFile"
Write-Host ""

$dirs = @("env", "uploads", "logs", "backups", "postgres", "redis", "bot-data")
foreach ($dir in $dirs) {
    $path = Join-Path $DataDir $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

if (-not (Test-Path $EnvFile)) {
    Copy-Item "deploy/docker/.env.example" $EnvFile
    Write-Host "Created $EnvFile from deploy/docker/.env.example" -ForegroundColor Green
    Write-Host "Edit it before starting the server:" -ForegroundColor Yellow
    Write-Host "  nano $EnvFile"
    exit 1
}

Write-Host "Env file already exists." -ForegroundColor Green
Write-Host ""
Write-Host "Next command:" -ForegroundColor Cyan
Write-Host "  bash scripts/vps-deploy-smoke.sh"
Write-Host ""
Write-Host "For IP-only Vercel setup, follow docs/IP_ONLY_VERCEL_GUIDE.md"
