# Fix PostgreSQL Setup Script
# This script checks and creates database/user if needed

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
Write-Host "  PostgreSQL Setup Fix" -ForegroundColor Cyan
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

# Request postgres superuser password
Write-Host "We need postgres superuser password to check/create database and user" -ForegroundColor Cyan
$postgresPassword = Read-Host "Enter postgres superuser password" -AsSecureString
$postgresPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($postgresPassword))

$env:PGPASSWORD = $postgresPasswordPlain

# Check if user exists
Write-Host ""
Write-Host "Checking if user '$dbUser' exists..." -ForegroundColor Cyan
$userCheck = & $PSQL_PATH -U postgres -d postgres -t -c "SELECT 1 FROM pg_roles WHERE rolname='$dbUser';" 2>&1

if ($userCheck -match "1") {
    Write-Host "User '$dbUser' exists" -ForegroundColor Green
} else {
    Write-Host "User '$dbUser' does not exist. Creating..." -ForegroundColor Yellow
    
    # Request password for new user
    Write-Host ""
    $dbPassword = Read-Host "Enter password for new user '$dbUser'" -AsSecureString
    $dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPassword))
    
    $createUserCmd = "CREATE USER $dbUser WITH PASSWORD '$dbPasswordPlain';"
    $result = & $PSQL_PATH -U postgres -d postgres -c $createUserCmd 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "User '$dbUser' created successfully" -ForegroundColor Green
    } else {
        Write-Host "Failed to create user: $result" -ForegroundColor Red
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        exit 1
    }
}

# Check if database exists
Write-Host ""
Write-Host "Checking if database '$dbName' exists..." -ForegroundColor Cyan
$dbCheck = & $PSQL_PATH -U postgres -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname='$dbName';" 2>&1

if ($dbCheck -match "1") {
    Write-Host "Database '$dbName' exists" -ForegroundColor Green
} else {
    Write-Host "Database '$dbName' does not exist. Creating..." -ForegroundColor Yellow
    
    $createDbCmd = "CREATE DATABASE $dbName OWNER $dbUser;"
    $result = & $PSQL_PATH -U postgres -d postgres -c $createDbCmd 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Database '$dbName' created successfully" -ForegroundColor Green
    } else {
        Write-Host "Failed to create database: $result" -ForegroundColor Red
        Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
        exit 1
    }
}

# Grant privileges
Write-Host ""
Write-Host "Granting privileges..." -ForegroundColor Cyan
$grantCmd = "GRANT ALL PRIVILEGES ON DATABASE $dbName TO $dbUser;"
$result = & $PSQL_PATH -U postgres -d postgres -c $grantCmd 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Privileges granted" -ForegroundColor Green
} else {
    Write-Host "Warning: Could not grant privileges: $result" -ForegroundColor Yellow
}

# Test connection
Write-Host ""
Write-Host "Testing connection with user '$dbUser'..." -ForegroundColor Cyan

# Get password for test
$testPassword = Read-Host "Enter password for user '$dbUser'" -AsSecureString
$testPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($testPassword))

$env:PGPASSWORD = $testPasswordPlain
$testResult = & $PSQL_PATH -U $dbUser -d $dbName -c "SELECT version();" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Connection successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "DATABASE_URL for .env file:" -ForegroundColor Cyan
    $databaseUrl = "postgresql://${dbUser}:${testPasswordPlain}@localhost:5432/${dbName}"
    Write-Host "DATABASE_URL=$databaseUrl" -ForegroundColor Yellow
} else {
    Write-Host "Connection failed: $testResult" -ForegroundColor Red
}

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Press Enter to exit..."
Read-Host


