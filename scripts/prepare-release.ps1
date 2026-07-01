<#
.SYNOPSIS
Prepare workspace for release: show or delete generated artifacts.

.DESCRIPTION
By default runs in dry-run mode and prints exactly what would be removed.
Use -ApplyCleanup to actually delete.

.EXAMPLE
.\scripts\prepare-release.ps1
# Dry-run only.

.EXAMPLE
.\scripts\prepare-release.ps1 -ApplyCleanup
# Delete generated artifacts and caches.

.EXAMPLE
.\scripts\prepare-release.ps1 -ApplyCleanup -RunChecks
# Delete artifacts, then run pytest/lint/type-check.

.EXAMPLE
.\scripts\prepare-release.ps1 -ApplyCleanup -IncludeVenvCaches
# Also remove __pycache__ inside .venv.
#>
param(
    [switch]$ApplyCleanup,
    [switch]$IncludeNodeModules,
    [switch]$IncludeVenvCaches,
    [switch]$IncludeLogs,
    [switch]$RunChecks,
    [switch]$RunFrontendBuild,
    [int]$MaxListItems = 200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-FileSizeSafe {
    param([string]$Path)
    try {
        if (-not (Test-Path $Path)) { return 0 }
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer) {
            return [int64]$item.Length
        }
        $sum = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum
        $value = $sum.Sum
        if ($null -eq $value) { $value = 0 }
        return [int64]$value
    }
    catch {
        return 0
    }
}

function Format-Bytes {
    param([int64]$Bytes)
    if ($Bytes -ge 1GB) { return ("{0:N2} GB" -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ("{0:N2} MB" -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ("{0:N2} KB" -f ($Bytes / 1KB)) }
    return ("{0} B" -f $Bytes)
}

function Normalize-Path {
    param([string]$Path, [string]$RepoRoot)
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $resolved.Substring($RepoRoot.Length).TrimStart('\')
    }
    return $resolved
}

function Add-Target {
    param(
        [System.Collections.Generic.Dictionary[string, object]]$Map,
        [string]$Path,
        [string]$Reason,
        [string]$RepoRoot
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if ($resolved -like "*\.git\*") { return }
    if ($Map.ContainsKey($resolved)) { return }

    $item = Get-Item -LiteralPath $resolved -Force
    $Map[$resolved] = [PSCustomObject]@{
        Path      = $resolved
        Relative  = (Normalize-Path -Path $resolved -RepoRoot $RepoRoot)
        Type      = $(if ($item.PSIsContainer) { "dir" } else { "file" })
        Reason    = $Reason
        SizeBytes = (Get-FileSizeSafe -Path $resolved)
    }
}

function Add-ByPattern {
    param(
        [System.Collections.Generic.Dictionary[string, object]]$Map,
        [string[]]$Roots,
        [string]$DirectoryName,
        [string]$Reason,
        [string]$RepoRoot
    )
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Recurse -Directory -Force -Filter $DirectoryName -ErrorAction SilentlyContinue |
            ForEach-Object {
                Add-Target -Map $Map -Path $_.FullName -Reason $Reason -RepoRoot $RepoRoot
            }
    }
}

function Add-FilesByExtension {
    param(
        [System.Collections.Generic.Dictionary[string, object]]$Map,
        [string[]]$Roots,
        [string[]]$Extensions,
        [string]$Reason,
        [string]$RepoRoot
    )
    foreach ($root in $Roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $Extensions -contains $_.Extension.ToLowerInvariant() } |
            ForEach-Object {
                Add-Target -Map $Map -Path $_.FullName -Reason $Reason -RepoRoot $RepoRoot
            }
    }
}

function Add-HarFiles {
    param(
        [System.Collections.Generic.Dictionary[string, object]]$Map,
        [string]$RepoRoot
    )
    Get-ChildItem -LiteralPath $RepoRoot -Recurse -File -Filter "*.har" -Force -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notlike "*\.git\*" -and
            $_.FullName -notlike "*\node_modules\*" -and
            $_.FullName -notlike "*\.venv\*"
        } |
        ForEach-Object {
            Add-Target -Map $Map -Path $_.FullName -Reason "HAR captures" -RepoRoot $RepoRoot
        }
}

function Compress-Targets {
    param([PSCustomObject[]]$Targets)

    $ordered = $Targets | Sort-Object { $_.Path.Length }
    $keep = New-Object System.Collections.Generic.List[object]
    $keptDirs = New-Object System.Collections.Generic.List[string]

    foreach ($t in $ordered) {
        $isNested = $false
        foreach ($d in $keptDirs) {
            if ($t.Path.StartsWith($d + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
                $isNested = $true
                break
            }
        }
        if ($isNested) { continue }
        $keep.Add($t)
        if ($t.Type -eq "dir") { $keptDirs.Add($t.Path) }
    }
    return $keep
}

function Clear-ReadOnlyRecursive {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try {
        attrib -R $Path 2>$null | Out-Null
    }
    catch { }
    try {
        Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                if ($_.Attributes -band [IO.FileAttributes]::ReadOnly) {
                    $_.Attributes = $_.Attributes -bxor [IO.FileAttributes]::ReadOnly
                }
            }
            catch { }
        }
    }
    catch { }
}

function Invoke-CommandChecked {
    param(
        [string]$Name,
        [string]$WorkDir,
        [string[]]$Command
    )
    Write-Host ""
    Write-Host ("[prepare-release] {0}" -f $Name)
    Push-Location $WorkDir
    try {
        & $Command[0] @($Command[1..($Command.Count - 1)])
        if ($LASTEXITCODE -ne 0) {
            throw ("Command failed with exit code {0}" -f $LASTEXITCODE)
        }
    }
    finally {
        Pop-Location
    }
}

$repoRoot = Resolve-RepoRoot
Set-Location $repoRoot

Write-Host "[prepare-release] Repo root: $repoRoot"
Write-Host ("[prepare-release] Mode: {0}" -f $(if ($ApplyCleanup) { "APPLY (delete)" } else { "DRY-RUN (preview)" }))

$targetMap = New-Object 'System.Collections.Generic.Dictionary[string, object]'

$fixedRelativePaths = @(
    "artifacts",
    ".benchmarks",
    ".pytest_tmp",
    ".coverage",
    "tmp",
    "playwright-report",
    ".playwright",
    ".playwright-cli",
    "coverage",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".cache",
    "frontend/dist",
    "frontend/coverage",
    "frontend/.vite",
    "frontend/.vitest",
    "bot_service/.pytest_cache",
    "bot_service/.ruff_cache",
    "bot_service/.mypy_cache",
    "bot_service/htmlcov",
    "bot_service/.benchmarks",
    "bot_service/tmp",
    "tts_worker_agent/.venv",
    "tts_worker_agent/tmp_agent_stdout.log",
    "tts_worker_agent/tmp_agent_stderr.log"
)

if ($IncludeNodeModules) {
    $fixedRelativePaths += "frontend/node_modules"
}
if ($IncludeLogs) {
    $fixedRelativePaths += "logs"
}

foreach ($relativePath in $fixedRelativePaths) {
    $abs = Join-Path $repoRoot $relativePath
    Add-Target -Map $targetMap -Path $abs -Reason "Fixed artifact directory/file" -RepoRoot $repoRoot
}

$roots = @(
    (Join-Path $repoRoot "bot_service"),
    (Join-Path $repoRoot "frontend"),
    (Join-Path $repoRoot "deploy"),
    (Join-Path $repoRoot "docs"),
    (Join-Path $repoRoot "scripts")
)

$f5Root = Join-Path $repoRoot "F5_tts"
if (Test-Path -LiteralPath $f5Root) { $roots += $f5Root }
if ($IncludeVenvCaches) { $roots += (Join-Path $repoRoot ".venv") }

Add-ByPattern -Map $targetMap -Roots $roots -DirectoryName "__pycache__" -Reason "Python bytecode cache (__pycache__)" -RepoRoot $repoRoot
Add-ByPattern -Map $targetMap -Roots $roots -DirectoryName "pytest-cache-files-*" -Reason "Pytest temporary cache directories" -RepoRoot $repoRoot
Add-FilesByExtension -Map $targetMap -Roots $roots -Extensions @(".pyc", ".pyo") -Reason "Python bytecode files (.pyc/.pyo)" -RepoRoot $repoRoot
Add-FilesByExtension -Map $targetMap -Roots $roots -Extensions @(".tmp", ".fixed") -Reason "Temporary editor/debug files (.tmp/.fixed)" -RepoRoot $repoRoot
Add-HarFiles -Map $targetMap -RepoRoot $repoRoot

$targets = $targetMap.Values | Sort-Object Path
$targets = Compress-Targets -Targets $targets
$targets = @($targets)

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host ""
    Write-Host "[prepare-release] Nothing to clean."
    exit 0
}

$totalBytesRaw = ($targets | Measure-Object -Property SizeBytes -Sum).Sum
if ($null -eq $totalBytesRaw) { $totalBytesRaw = 0 }
$totalBytes = [int64]$totalBytesRaw
Write-Host ""
Write-Host ("[prepare-release] Planned targets: {0} items, {1}" -f $targets.Count, (Format-Bytes -Bytes $totalBytes))

$grouped = $targets | Group-Object Reason | Sort-Object Name
foreach ($g in $grouped) {
    $gBytesRaw = ($g.Group | Measure-Object -Property SizeBytes -Sum).Sum
    if ($null -eq $gBytesRaw) { $gBytesRaw = 0 }
    $gBytes = [int64]$gBytesRaw
    Write-Host (" - {0}: {1} items, {2}" -f $g.Name, $g.Count, (Format-Bytes -Bytes $gBytes))
}

Write-Host ""
Write-Host "[prepare-release] Paths:"
$sortedTargets = $targets | Sort-Object Relative
$visibleTargets = $sortedTargets | Select-Object -First $MaxListItems
foreach ($t in $visibleTargets) {
    Write-Host (" - {0} [{1}] ({2})" -f $t.Relative, $t.Type, (Format-Bytes -Bytes $t.SizeBytes))
}
if ($sortedTargets.Count -gt $visibleTargets.Count) {
    $hiddenCount = $sortedTargets.Count - $visibleTargets.Count
    Write-Host (" - ... and {0} more items (increase -MaxListItems to show more)" -f $hiddenCount)
}

if (-not $ApplyCleanup) {
    Write-Host ""
    Write-Host "[prepare-release] Dry-run complete. Re-run with -ApplyCleanup to delete."
    exit 0
}

Write-Host ""
Write-Host "[prepare-release] Deleting..."
$removed = 0
$failed = 0

foreach ($t in ($targets | Sort-Object { $_.Path.Length } -Descending)) {
    try {
        Clear-ReadOnlyRecursive -Path $t.Path
        Remove-Item -LiteralPath $t.Path -Recurse -Force -ErrorAction Stop
        Write-Host (" [ok] {0}" -f $t.Relative)
        $removed++
    }
    catch {
        Write-Warning (" [failed] {0} :: {1}" -f $t.Relative, $_.Exception.Message)
        $failed++
    }
}

Write-Host ""
Write-Host ("[prepare-release] Removed: {0}, Failed: {1}" -f $removed, $failed)

if ($RunChecks) {
    Invoke-CommandChecked -Name "Backend tests (pytest -q)" -WorkDir (Join-Path $repoRoot "bot_service") -Command @("python", "-m", "pytest", "-q")
    Invoke-CommandChecked -Name "Frontend lint" -WorkDir (Join-Path $repoRoot "frontend") -Command @("npm", "run", "lint")
    Invoke-CommandChecked -Name "Frontend type-check" -WorkDir (Join-Path $repoRoot "frontend") -Command @("npm", "run", "type-check")
    if ($RunFrontendBuild) {
        Invoke-CommandChecked -Name "Frontend build" -WorkDir (Join-Path $repoRoot "frontend") -Command @("npm", "run", "build")
    }
}

Write-Host ""
Write-Host "[prepare-release] Done."
