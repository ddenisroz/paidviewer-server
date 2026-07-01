# Reset PostgreSQL user password
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
Write-Host "  PostgreSQL Password Reset" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $PSQL_PATH)) {
    Write-Host "PostgreSQL psql.exe not found." -ForegroundColor Red
    Write-Host "Set PSQL_PATH environment variable or add psql to PATH." -ForegroundColor Yellow
    exit 1
}

$dbUser = "payedviewer_user"

Write-Host "User: $dbUser" -ForegroundColor Yellow
Write-Host ""

# Request postgres superuser password
$postgresPassword = Read-Host "Enter postgres superuser password" -AsSecureString
$postgresPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($postgresPassword))

$env:PGPASSWORD = $postgresPasswordPlain

# Request new password for payedviewer_user
Write-Host ""
Write-Host "Setting new password for '$dbUser'..." -ForegroundColor Cyan
$newPassword = Read-Host "Enter NEW password for user '$dbUser'" -AsSecureString
$newPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($newPassword))

# Escape single quotes in password for SQL
$escapedPassword = $newPasswordPlain -replace "'", "''"

# Change password
$changePasswordCmd = "ALTER USER $dbUser WITH PASSWORD '$escapedPassword';"
Write-Host ""
Write-Host "Changing password..." -ForegroundColor Yellow

$result = & $PSQL_PATH -U postgres -d postgres -c $changePasswordCmd 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Password changed successfully!" -ForegroundColor Green
    Write-Host ""
    
    # Test connection with new password
    Write-Host "Testing connection with new password..." -ForegroundColor Cyan
    $env:PGPASSWORD = $newPasswordPlain
    $dbName = "payedviewerbot"
    
    $testResult = & $PSQL_PATH -h 127.0.0.1 -U $dbUser -d $dbName -c "SELECT version();" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Connection test successful!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Updating .env file..." -ForegroundColor Cyan
        
        $databaseUrl = "postgresql://${dbUser}:${newPasswordPlain}@127.0.0.1:5432/${dbName}"
        
        $envPath = Join-Path (Get-Location) ".env"
        if (Test-Path $envPath) {
            $envContent = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
            if ($null -eq $envContent) {
                $envContent = ""
            }
            
            if ($envContent -match "DATABASE_URL=.*") {
                $envContent = $envContent -replace "DATABASE_URL=.*", "DATABASE_URL=$databaseUrl"
            } else {
                if ($envContent.Length -gt 0 -and -not $envContent.EndsWith("`n")) {
                    $envContent += "`n"
                }
                $envContent += "# === DATABASE ===`nDATABASE_URL=$databaseUrl`n"
            }
            
            Set-Content -Path $envPath -Value $envContent -NoNewline
            Write-Host ".env file updated!" -ForegroundColor Green
            Write-Host ""
            Write-Host "New DATABASE_URL:" -ForegroundColor Yellow
            Write-Host "DATABASE_URL=$databaseUrl" -ForegroundColor Cyan
        } else {
            Write-Host ".env file not found at: $envPath" -ForegroundColor Yellow
            Write-Host "Add manually:" -ForegroundColor Yellow
            Write-Host "DATABASE_URL=$databaseUrl" -ForegroundColor Cyan
        }
    } else {
        Write-Host "Connection test failed: $testResult" -ForegroundColor Red
        Write-Host ""
        Write-Host "But password was changed. Try connecting manually." -ForegroundColor Yellow
    }
} else {
    Write-Host "Failed to change password: $result" -ForegroundColor Red
}

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Press Enter to exit..."
Read-Host


