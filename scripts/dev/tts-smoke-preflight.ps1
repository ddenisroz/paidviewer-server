param(
    [ValidateSet('all', 'cloud', 'self_host', 'compatibility')]
    [string]$Scenario = 'all',

    [switch]$SkipComposeChecks
)

$ErrorActionPreference = 'Stop'

function Add-Result {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Level,
        [string]$Area,
        [string]$Message
    )

    $Results.Add([pscustomobject]@{
        Level = $Level
        Area = $Area
        Message = $Message
    })
}

function Read-EnvFile {
    param([string]$Path)

    $map = @{}
    if (-not (Test-Path $Path)) {
        return $map
    }

    foreach ($rawLine in Get-Content $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }

        $index = $line.IndexOf('=')
        if ($index -lt 1) {
            continue
        }

        $key = $line.Substring(0, $index).Trim()
        $value = $line.Substring($index + 1).Trim()

        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        $map[$key] = $value
    }

    return $map
}

function Test-EnvKeys {
    param(
        [hashtable]$Map,
        [string]$Area,
        [string[]]$RequiredKeys,
        [System.Collections.Generic.List[object]]$Results
    )

    foreach ($key in $RequiredKeys) {
        if (-not $Map.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$Map[$key])) {
            Add-Result $Results 'FAIL' $Area "Missing required env key: $key"
        }
        else {
            Add-Result $Results 'OK' $Area "Configured env key: $key"
        }
    }
}

function Test-OptionalEnvKeys {
    param(
        [hashtable]$Map,
        [string]$Area,
        [string[]]$OptionalKeys,
        [System.Collections.Generic.List[object]]$Results
    )

    foreach ($key in $OptionalKeys) {
        if (-not $Map.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$Map[$key])) {
            Add-Result $Results 'WARN' $Area "Optional env key is empty: $key"
        }
        else {
            Add-Result $Results 'OK' $Area "Configured optional env key: $key"
        }
    }
}

function Invoke-ComposeConfigCheck {
    param(
        [string]$ComposeFile,
        [System.Collections.Generic.List[object]]$Results
    )

    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Add-Result $Results 'WARN' 'compose' 'docker is not installed or not available in PATH; compose checks skipped'
        return
    }

    try {
        & docker compose -f $ComposeFile config -q | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Add-Result $Results 'OK' 'compose' "docker compose config passed: $ComposeFile"
        }
        else {
            Add-Result $Results 'FAIL' 'compose' "docker compose config failed: $ComposeFile"
        }
    }
    catch {
        Add-Result $Results 'WARN' 'compose' "docker compose check could not be completed: $ComposeFile"
    }
}

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$botEnvPath = Join-Path $repoRoot 'bot_service\.env'
$webRoot = if ($env:PAIDVIEWER_WEB_ROOT) { $env:PAIDVIEWER_WEB_ROOT } else { Join-Path (Split-Path $repoRoot -Parent) 'paidviewer-web\frontend' }
$frontendEnvPath = Join-Path $webRoot '.env'
$results = [System.Collections.Generic.List[object]]::new()

if (Test-Path $botEnvPath) {
    Add-Result $results 'OK' 'files' "Found bot_service env: $botEnvPath"
}
else {
    Add-Result $results 'FAIL' 'files' "Missing bot_service env: $botEnvPath"
}

if (Test-Path $frontendEnvPath) {
    Add-Result $results 'OK' 'files' "Found frontend env via PAIDVIEWER_WEB_ROOT: $frontendEnvPath"
}
else {
    Add-Result $results 'WARN' 'files' "Frontend env not found; skipped split-web check. Set PAIDVIEWER_WEB_ROOT to enable it."
}

$botEnv = Read-EnvFile $botEnvPath
$frontendEnv = Read-EnvFile $frontendEnvPath

Test-EnvKeys -Map $botEnv -Area 'bot_service' -RequiredKeys @(
    'SECRET_KEY',
    'DATABASE_URL',
    'BACKEND_URL',
    'FRONTEND_URL'
) -Results $results

if ($frontendEnv.Count -gt 0) {
    Test-EnvKeys -Map $frontendEnv -Area 'frontend' -RequiredKeys @(
        'VITE_BOT_SERVICE_URL',
        'VITE_BOT_SERVICE_WS_URL'
    ) -Results $results
}

switch ($Scenario) {
    'all' {
        Test-EnvKeys -Map $botEnv -Area 'cloud' -RequiredKeys @(
            'TTS_GATEWAY_URL',
            'TTS_GATEWAY_API_KEY',
            'F5_TTS_SERVICE_URL',
            'F5_TTS_SERVICE_API_KEY'
        ) -Results $results

        Test-EnvKeys -Map $botEnv -Area 'self_host' -RequiredKeys @(
            'LOCAL_TTS_ALLOWED_HOSTS',
            'LOCAL_TTS_ALLOWED_CIDRS'
        ) -Results $results
    }
    'cloud' {
        Test-EnvKeys -Map $botEnv -Area 'cloud' -RequiredKeys @(
            'TTS_GATEWAY_URL',
            'TTS_GATEWAY_API_KEY',
            'F5_TTS_SERVICE_URL',
            'F5_TTS_SERVICE_API_KEY'
        ) -Results $results
    }
    'self_host' {
        Test-EnvKeys -Map $botEnv -Area 'self_host' -RequiredKeys @(
            'LOCAL_TTS_ALLOWED_HOSTS',
            'LOCAL_TTS_ALLOWED_CIDRS'
        ) -Results $results
    }
    'compatibility' {
        Test-EnvKeys -Map $botEnv -Area 'compatibility' -RequiredKeys @(
            'F5_TTS_SERVICE_URL',
            'F5_TTS_SERVICE_API_KEY'
        ) -Results $results

        Add-Result $results 'WARN' 'compatibility' 'Compatibility mode is not part of the primary presentation or production success path'
    }
}

if ($Scenario -in @('all', 'cloud')) {
    Add-Result $results 'WARN' 'external' 'Redis reachability for tts-gateway is not verified by this script'
    Add-Result $results 'WARN' 'external' 'F5 vendor/assets/weights are not verified by this script'
}

if ($Scenario -in @('all', 'self_host')) {
    Add-Result $results 'WARN' 'self_host' 'Per-user self-host runtime config is stored in DB and is not verified by this script'
    Add-Result $results 'WARN' 'self_host' 'Authenticated + whitelisted user state is not verified by this script'
}

if (-not $SkipComposeChecks) {
    Invoke-ComposeConfigCheck -ComposeFile (Join-Path $repoRoot 'deploy\docker\docker-compose.server.yml') -Results $results
}

foreach ($result in $results) {
    switch ($result.Level) {
        'OK' { Write-Host "[OK]   [$($result.Area)] $($result.Message)" -ForegroundColor Green }
        'WARN' { Write-Host "[WARN] [$($result.Area)] $($result.Message)" -ForegroundColor Yellow }
        'FAIL' { Write-Host "[FAIL] [$($result.Area)] $($result.Message)" -ForegroundColor Red }
    }
}

$failCount = @($results | Where-Object { $_.Level -eq 'FAIL' }).Count
$warnCount = @($results | Where-Object { $_.Level -eq 'WARN' }).Count

Write-Host ''
Write-Host "Summary: fails=$failCount warnings=$warnCount scenario=$Scenario" -ForegroundColor Cyan

if ($failCount -gt 0) {
    exit 1
}

exit 0
