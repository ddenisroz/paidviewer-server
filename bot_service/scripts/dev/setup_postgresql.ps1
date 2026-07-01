# PostgreSQL setup script for TTS Bot
# Run: .\scripts\setup_postgresql.ps1

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
Write-Host "  PostgreSQL Setup for TTS Bot" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check psql availability
if (-not (Test-Path $PSQL_PATH)) {
    Write-Host "❌ PostgreSQL psql.exe was not found" -ForegroundColor Red
    Write-Host "   Set PSQL_PATH or add psql to PATH" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ PostgreSQL detected" -ForegroundColor Green
Write-Host ""

# Ask for postgres password
$postgresPassword = Read-Host "Enter the password for the 'postgres' user" -AsSecureString
$postgresPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($postgresPassword))

# Ask for database name
$dbName = Read-Host "Database name [default: tts_bot_db]"
if ([string]::IsNullOrWhiteSpace($dbName)) {
    $dbName = "tts_bot_db"
}

# Ask for database user
$dbUser = Read-Host "Database user name [default: tts_user]"
if ([string]::IsNullOrWhiteSpace($dbUser)) {
    $dbUser = "tts_user"
}

# Ask for database user password
Write-Host ""
$dbPassword = Read-Host "Password for user '$dbUser'" -AsSecureString
$dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword))

Write-Host ""
Write-Host "📋 Creating database and user..." -ForegroundColor Cyan

# SQL commands
$sqlCommands = @"
-- Create database
CREATE DATABASE $dbName;

-- Create user
CREATE USER $dbUser WITH PASSWORD '$dbPasswordPlain';

-- Grant database privileges
GRANT ALL PRIVILEGES ON DATABASE $dbName TO $dbUser;

-- Connect to the new database and grant schema privileges
\c $dbName
GRANT ALL ON SCHEMA public TO $dbUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $dbUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $dbUser;
"@

# Save to a temporary file
$tempFile = [System.IO.Path]::GetTempFileName()
$sqlCommands | Out-File -FilePath $tempFile -Encoding UTF8

try {
    # Set password in environment
    $env:PGPASSWORD = $postgresPasswordPlain

    # Execute SQL commands
    $result = & $PSQL_PATH -U postgres -f $tempFile 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database and user created successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "📝 Add this to your .env file:" -ForegroundColor Cyan
        Write-Host "DATABASE_URL=postgresql://$dbUser`:$dbPasswordPlain@localhost:5432/$dbName" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "⚠️  Save this line, you will need it for the application connection" -ForegroundColor Yellow
    } else {
        Write-Host "❌ Database creation failed:" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Error: $_" -ForegroundColor Red
} finally {
    # Remove temporary file
    Remove-Item $tempFile -ErrorAction SilentlyContinue
    # Clear password from environment
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Press Enter to exit..."
Read-Host
