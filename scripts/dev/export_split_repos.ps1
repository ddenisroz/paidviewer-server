param(
  [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path 'paidviewer-split'),
  [switch]$Apply,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$repos = @(
  @{
    Name = 'paidviewer-server'
    Items = @(
      'bot_service',
      'deploy',
      'docs',
      'scripts',
      'README.md',
      '.gitignore',
      'pytest.ini',
      'mypy.ini',
      'AGENTS.md'
    )
  },
  @{
    Name = 'paidviewer-web'
    Items = @(
      'frontend'
    )
  },
  @{
    Name = 'paidviewer-self-host'
    Items = @(
      'tts_worker_agent',
      'docs\DEPLOYMENT_GUIDE.md',
      'README.md'
    )
  }
)

$excludeDirs = @(
  '.git',
  '.venv',
  'node_modules',
  'dist',
  'build',
  'logs',
  'tmp',
  'temp',
  'cache',
  'uploads',
  'backups',
  '__pycache__',
  '.pytest_cache',
  '_pytest_tmp',
  'core\data'
)
$excludeFiles = @(
  '.env',
  '.env.local',
  '.env.production',
  'config.json',
  '*.pyc',
  '*.pyo',
  '*.log'
)

function Copy-RepoItem {
  param(
    [string]$RelativePath,
    [string]$TargetRoot
  )

  $source = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $source)) {
    Write-Warning "Missing source: $RelativePath"
    return
  }

  $target = Join-Path $TargetRoot $RelativePath
  $targetParent = Split-Path -Parent $target
  if ($Apply) {
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
  }

  Write-Output "$(if ($Apply) { 'copy' } else { 'would copy' }) $RelativePath -> $target"
  if (-not $Apply) {
    return
  }

  if ((Get-Item -LiteralPath $source).PSIsContainer) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $args = @($source, $target, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($excludeDirs.Count -gt 0) {
      $args += @('/XD') + $excludeDirs
    }
    if ($excludeFiles.Count -gt 0) {
      $args += @('/XF') + $excludeFiles
    }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) {
      throw "robocopy failed for $RelativePath with exit code $LASTEXITCODE"
    }
    return
  }

  Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
}

foreach ($repo in $repos) {
  $targetRoot = Join-Path $OutputRoot $repo.Name
  if ((Test-Path -LiteralPath $targetRoot) -and -not $Force) {
    throw "Target exists: $targetRoot. Re-run with -Force to replace copied files."
  }

  if ($Apply) {
    New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
  }
  Write-Output "== $($repo.Name) =="
  foreach ($item in $repo.Items) {
    Copy-RepoItem -RelativePath $item -TargetRoot $targetRoot
  }
}

if (-not $Apply) {
  Write-Output "Dry run only. Re-run with -Apply to create split folders under: $OutputRoot"
}
