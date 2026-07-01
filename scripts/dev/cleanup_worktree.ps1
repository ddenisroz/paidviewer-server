param(
  [switch]$Apply,
  [switch]$IncludeLocalData
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$dryPrefix = if ($Apply) { 'remove' } else { 'would remove' }
$removed = New-Object System.Collections.Generic.List[string]

function Assert-InRepo {
  param([string]$ResolvedPath)

  $rootWithSlash = $repoRoot.TrimEnd('\') + '\'
  if (
    -not $ResolvedPath.Equals($repoRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $ResolvedPath.StartsWith($rootWithSlash, [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "Refusing to clean outside repo: $ResolvedPath"
  }
}

function Remove-ResolvedTarget {
  param([string]$ResolvedPath)

  Assert-InRepo $ResolvedPath
  $removed.Add($ResolvedPath) | Out-Null
  Write-Output "$dryPrefix $ResolvedPath"
  if ($Apply) {
    try {
      Remove-Item -LiteralPath $ResolvedPath -Recurse -Force -ErrorAction Stop
    }
    catch {
      Write-Warning "Could not remove ${ResolvedPath}: $($_.Exception.Message)"
    }
  }
}

function Remove-RepoTarget {
  param([string]$RelativePath)

  $path = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $path)) {
    return
  }

  $resolved = (Resolve-Path -LiteralPath $path).Path
  Remove-ResolvedTarget $resolved
}

function Remove-NamedDirectories {
  param(
    [string[]]$Roots,
    [string[]]$Names
  )

  foreach ($rootRel in $Roots) {
    $root = Join-Path $repoRoot $rootRel
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
      continue
    }

    foreach ($name in $Names) {
      $matches = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -Directory -Filter $name -ErrorAction SilentlyContinue
      )
      foreach ($match in $matches) {
        Remove-ResolvedTarget $match.FullName
      }
    }
  }
}

function Remove-MatchedFiles {
  param(
    [string[]]$Roots,
    [string[]]$Filters
  )

  foreach ($rootRel in $Roots) {
    $root = Join-Path $repoRoot $rootRel
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
      continue
    }

    foreach ($filter in $Filters) {
      $matches = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -File -Filter $filter -ErrorAction SilentlyContinue
      )
      foreach ($match in $matches) {
        Remove-ResolvedTarget $match.FullName
      }
    }
  }
}

function Remove-TopLevelFiles {
  param([string[]]$Filters)

  foreach ($filter in $Filters) {
    $matches = @(
      Get-ChildItem -LiteralPath $repoRoot -Force -File -Filter $filter -ErrorAction SilentlyContinue
    )
    foreach ($match in $matches) {
      Remove-ResolvedTarget $match.FullName
    }
  }
}

$fixedTargets = @(
  '__pycache__',
  '.benchmarks',
  '.pytest_cache',
  '.pytest_tmp',
  '_pytest_cache',
  '_pytest_tmp',
  '.ruff_cache',
  'coverage',
  'frontend\dist',
  'frontend\build',
  'frontend\.vite',
  'frontend\.pytest_cache',
  'frontend\playwright-report',
  'bot_service\.pytest_cache',
  'bot_service\.pytest_tmp',
  'bot_service\_pytest_cache',
  'bot_service\_pytest_tmp',
  'bot_service\logs',
  'bot_service\temp',
  'bot_service\cache',
  'tts_service\.pytest_cache',
  'tts_service\logs',
  'tts_service\temp',
  'tts_service\cache',
  'tts_service\audio',
  'tts_service\f5_tts_cache',
  'tmp_runtime_logs',
  'logs',
  'temp',
  'tmp',
  'cache',
  'output',
  'artifacts'
)

if ($IncludeLocalData) {
  $fixedTargets += @(
    'bot_service\core\data'
  )
}

foreach ($target in $fixedTargets) {
  Remove-RepoTarget $target
}

Remove-NamedDirectories -Roots @('bot_service', 'scripts', 'tts_service', 'tts_worker_agent') -Names @(
  '__pycache__',
  '.pytest_cache',
  '.pytest_tmp',
  '_pytest_cache',
  '_pytest_tmp'
)

Remove-MatchedFiles -Roots @('bot_service', 'scripts', 'tts_service', 'tts_worker_agent') -Filters @(
  '*.pyc',
  '*.pyo',
  '*.tmp',
  '.coverage',
  '.coverage.*'
)

Remove-TopLevelFiles @(
  '.coverage',
  '.coverage.*',
  'coverage.xml',
  '*.lcov'
)

if (-not $Apply) {
  Write-Output 'Dry run only. Re-run with -Apply to delete these targets.'
  Write-Output 'Local data is protected. Add -IncludeLocalData to include bot_service\core\data.'
}

Write-Output "targets=$($removed.Count)"
