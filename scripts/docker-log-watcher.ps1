param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [Parameter(Mandatory = $true)]
    [string]$ServiceName,

    [Parameter(Mandatory = $true)]
    [string]$LogFilePath,

    [string]$ComposeArgsJson,

    [string]$ComposeArgsBase64,

    [int64]$MaxLogBytes = 5242880,

    [int]$MaxLogFiles = 5,

    [int]$TailLines = 300,

    [int]$RetentionDays = 7
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$composeArgs = @()
if (-not [string]::IsNullOrWhiteSpace($ComposeArgsBase64)) {
    $decodedComposeArgsJson = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($ComposeArgsBase64))
    $composeArgs = @((ConvertFrom-Json -InputObject $decodedComposeArgsJson))
} elseif (-not [string]::IsNullOrWhiteSpace($ComposeArgsJson)) {
    $composeArgs = @((ConvertFrom-Json -InputObject $ComposeArgsJson))
}

$logDirectory = Split-Path -Parent $LogFilePath
if (-not (Test-Path -LiteralPath $logDirectory)) {
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
}

function Remove-ExpiredLogFiles {
    if ($RetentionDays -le 0) {
        return
    }

    $cutoff = (Get-Date).AddDays(-1 * $RetentionDays)
    $baseName = Split-Path -Leaf $LogFilePath

    Get-ChildItem -LiteralPath $logDirectory -File -ErrorAction SilentlyContinue |
        Where-Object {
            ($_.Name -eq $baseName -or $_.Name -like "$baseName.*") -and
            $_.LastWriteTime -lt $cutoff
        } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        }
}

function Rotate-LogFile {
    if ($MaxLogBytes -le 0 -or -not (Test-Path -LiteralPath $LogFilePath)) {
        return
    }

    $current = Get-Item -LiteralPath $LogFilePath -ErrorAction SilentlyContinue
    if ($null -eq $current -or $current.Length -lt $MaxLogBytes) {
        return
    }

    if ($MaxLogFiles -le 0) {
        Clear-Content -LiteralPath $LogFilePath -ErrorAction SilentlyContinue
        return
    }

    $oldest = "$LogFilePath.$MaxLogFiles"
    if (Test-Path -LiteralPath $oldest) {
        Remove-Item -LiteralPath $oldest -Force -ErrorAction SilentlyContinue
    }

    for ($index = $MaxLogFiles - 1; $index -ge 1; $index--) {
        $source = "$LogFilePath.$index"
        $target = "$LogFilePath.$($index + 1)"
        if (Test-Path -LiteralPath $source) {
            Move-Item -LiteralPath $source -Destination $target -Force -ErrorAction SilentlyContinue
        }
    }

    Move-Item -LiteralPath $LogFilePath -Destination "$LogFilePath.1" -Force -ErrorAction SilentlyContinue
}

function Write-LogLine {
    param([Parameter(Mandatory = $true)][string]$Line)

    Rotate-LogFile
    Add-Content -LiteralPath $LogFilePath -Value $Line -Encoding utf8
}

Set-Location $RepoRoot

Remove-ExpiredLogFiles
Rotate-LogFile

docker compose @composeArgs logs -f --tail $TailLines --timestamps --no-color $ServiceName |
    ForEach-Object {
        Write-LogLine -Line $_
    }
