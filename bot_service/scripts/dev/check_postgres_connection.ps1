# PostgreSQL Connection Check Script
# Usage: .\scripts\check_postgres_connection.ps1

function Resolve-PsqlPath {
    if ($env:PSQL_PATH -and (Test-Path $env:PSQL_PATH)) {
        return $env:PSQL_PATH
    }

    $psqlCommand = Get-Command psql -ErrorAction SilentlyContinue
    if ($psqlCommand) {
        return $psqlCommand.Source
    }

    $versions = @("18", "17", "16", "15", "14")
    $programFilesX86 = ${env:ProgramFiles(x86)}
    $candidates = @()

    foreach ($version in $versions) {
        if ($env:ProgramFiles) {
            $candidates += (Join-Path $env:ProgramFiles "PostgreSQL\$version\bin\psql.exe")
        }
        if ($programFilesX86) {
            $candidates += (Join-Path $programFilesX86 "PostgreSQL\$version\bin\psql.exe")
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$PSQL_PATH = Resolve-PsqlPath

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PostgreSQL Connection Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PSQL_PATH)) {
    Write-Host "PostgreSQL psql.exe not found." -ForegroundColor Red
    Write-Host "Set PSQL_PATH environment variable or add psql to PATH." -ForegroundColor Yellow
    exit 1
}

$dbName = "payedviewerbot"
$dbUser = "payedviewer_user"

Write-Host "Database: $dbName" -ForegroundColor Yellow
Write-Host "User: $dbUser" -ForegroundColor Yellow
Write-Host ""

# Request password
$dbPassword = Read-Host "Enter password for user '$dbUser'" -AsSecureString
$dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword))

# Build DATABASE_URL
$databaseUrl = "postgresql://${dbUser}:${dbPasswordPlain}@localhost:5432/${dbName}"

Write-Host ""
Write-Host "Testing connection..." -ForegroundColor Cyan

$env:PGPASSWORD = $dbPasswordPlain

try {
    $result = & $PSQL_PATH -U $dbUser -d $dbName -c "SELECT version();" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Connection successful!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Add to your .env file (bot_service/.env):" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "DATABASE_URL=$databaseUrl" -ForegroundColor Yellow
        Write-Host ""
        
        # Try to automatically update .env
        $envPath = Join-Path (Get-Location) ".env"
        if (Test-Path $envPath) {
            Write-Host "Updating .env file..." -ForegroundColor Cyan
            
            $envContent = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
            if ($null -eq $envContent) {
                $envContent = ""
            }
            
            # Find existing DATABASE_URL or add new one
            if ($envContent -match "DATABASE_URL=.*") {
                $envContent = $envContent -replace "DATABASE_URL=.*", "DATABASE_URL=$databaseUrl"
                Write-Host "   Updated existing DATABASE_URL" -ForegroundColor Green
            } else {
                if ($envContent.Length -gt 0 -and -not $envContent.EndsWith("`n")) {
                    $envContent += "`n"
                }
                $envContent += "# === DATABASE ===`nDATABASE_URL=$databaseUrl`n"
                Write-Host "   Added new DATABASE_URL" -ForegroundColor Green
            }
            
            Set-Content -Path $envPath -Value $envContent -NoNewline
            Write-Host ""
            Write-Host ".env file updated!" -ForegroundColor Green
        } else {
            Write-Host "File .env not found at: $envPath" -ForegroundColor Yellow
            Write-Host "Create it manually and add: DATABASE_URL=$databaseUrl" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Connection error:" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
        Write-Host ""
        Write-Host "Check:" -ForegroundColor Yellow
        Write-Host "  1. Password is correct" -ForegroundColor Yellow
        Write-Host "  2. Database '$dbName' exists" -ForegroundColor Yellow
        Write-Host "  3. User '$dbUser' has access rights" -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
} finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Press Enter to exit..."
Read-Host

