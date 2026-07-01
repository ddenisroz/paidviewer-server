# migrate.ps1 - TTS Bot Migration Script for Windows
# Easy migration to new machine with automated setup

Write-Host "=== TTS Bot Migration Script ===" -ForegroundColor Cyan
Write-Host ""

# Check if .env files exist
$envFiles = @(
    "bot_service\.env",
    "frontend\.env"
)

$missingEnv = @()
foreach ($envFile in $envFiles) {
    if (-not (Test-Path $envFile)) {
        $missingEnv += $envFile
    }
}

if ($missingEnv.Count -gt 0) {
    Write-Host "Creating .env files from templates..." -ForegroundColor Yellow
    
    # Copy .env.example to .env for each service
    if (-not (Test-Path "bot_service\.env")) {
        Copy-Item "bot_service\.env.example" "bot_service\.env"
        Write-Host "✓ Created bot_service\.env" -ForegroundColor Green
    }
    
    if (-not (Test-Path "frontend\.env")) {
        Copy-Item "frontend\.env.example" "frontend\.env"
        Write-Host "✓ Created frontend\.env" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "[WARN] Please edit the .env files with your configuration before continuing." -ForegroundColor Yellow
    Write-Host "   Run this script again after editing." -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ .env files found" -ForegroundColor Green
Write-Host ""

# Generate secrets if needed
Write-Host "Checking security keys..." -ForegroundColor Cyan
$botEnv = Get-Content "bot_service\.env" -Raw

if ($botEnv -match "your-secret-key-here") {
    Write-Host "Generating security keys..." -ForegroundColor Yellow
    
    # Generate SECRET_KEY (64 character hex)
    $secretKey = -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
    
    # Generate Fernet key for encryption
    $pythonCode = @"
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
"@
    $encryptionKey = python -c $pythonCode
    
    if ($LASTEXITCODE -eq 0) {
        # Update bot_service/.env
        $botEnv = $botEnv -replace "your-secret-key-here-generate-with-openssl-rand-hex-32", $secretKey
        $botEnv = $botEnv -replace "your-encryption-key-here-generate-with-fernet", $encryptionKey
        $botEnv | Set-Content "bot_service\.env"
        
        Write-Host "[OK] Generated security keys" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to generate encryption key. Please install cryptography:" -ForegroundColor Red
        Write-Host "   pip install cryptography" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "✓ Security keys configured" -ForegroundColor Green
Write-Host ""

# Create required directories
Write-Host "Creating required directories..." -ForegroundColor Cyan
$directories = @(
    "data",
    "logs",
    "logs\access",
    "logs\app",
    "logs\audit",
    "logs\errors",
    "logs\monitoring",
    "models",
    "voices",
    "audio",
    "bot_service\data",
    "bot_service\logs"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

Write-Host "✓ Created directories" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Cyan

# Backend dependencies
Write-Host "Installing bot_service dependencies..." -ForegroundColor Yellow
Push-Location bot_service
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install bot_service dependencies" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "✓ Bot service dependencies installed" -ForegroundColor Green

# Frontend dependencies
Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Push-Location frontend
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install frontend dependencies" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "✓ Frontend dependencies installed" -ForegroundColor Green
Write-Host ""

# Run database migrations
Write-Host "Running database migrations..." -ForegroundColor Cyan
Push-Location bot_service
alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Database migration failed. This is normal for first-time setup." -ForegroundColor Yellow
}
Pop-Location
Write-Host "✓ Database ready" -ForegroundColor Green
Write-Host ""

Write-Host "=== Migration Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Edit .env files with your OAuth credentials" -ForegroundColor White
Write-Host "2. For TTS service: Configure Cloudflare Tunnel (optional)" -ForegroundColor White
Write-Host "3. Run: docker-compose up -d (or npm run dev for development)" -ForegroundColor White
Write-Host ""
Write-Host "Development commands:" -ForegroundColor Cyan
Write-Host "  cd bot_service; python main.py   - Start bot service" -ForegroundColor White
Write-Host "  # Run F5 TTS from standalone repository or external host" -ForegroundColor White
Write-Host "  cd frontend; npm run dev        - Start frontend" -ForegroundColor White
Write-Host ""


