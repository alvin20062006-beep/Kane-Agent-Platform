param(
  [int[]]$Ports = @(3000, 8000, 8010, 8011),
  [int]$MaxPasses = 3,
  [int]$GraceMs = 500,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRootLower = $RepoRoot.ToLowerInvariant()
$ManifestPath = Join-Path $RepoRoot ".runtime-logs\dev-stack-manifest.json"

function Get-ProcessInfo {
  param([int]$ProcessId)
  try {
    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    if ($info) {
      return $info
    }
  } catch {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc) {
      return [pscustomobject]@{
        ProcessId = $proc.Id
        Name = $proc.ProcessName
        CommandLine = $null
      }
    }
  }
  return $null
}

function Get-ChildProcessInfos {
  param([int]$ParentProcessId)
  try {
    return @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction Stop)
  } catch {
    return @()
  }
}

function Get-DescendantProcessInfos {
  param([int]$ParentProcessId)
  $out = @()
  $children = @(Get-ChildProcessInfos -ParentProcessId $ParentProcessId)
  foreach ($child in $children) {
    $out += $child
    $out += @(Get-DescendantProcessInfos -ParentProcessId ([int]$child.ProcessId))
  }
  return $out
}

function Get-ListeningPidsForPort {
  param([int]$Port)
  $rows = @(netstat -ano)
  $pids = @()
  foreach ($row in $rows) {
    if ($row -notmatch "LISTENING") {
      continue
    }
    if ($row -notmatch "[:.]$Port\s") {
      continue
    }
    $parts = @($row -split "\s+" | Where-Object { $_ })
    if ($parts.Count -ge 5) {
      $pids += [int]$parts[-1]
    }
  }
  $pids | Sort-Object -Unique
}

function Get-StackManifest {
  if (-not (Test-Path $ManifestPath)) {
    return $null
  }
  try {
    $manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
    if (-not $manifest.repoRoot) {
      return $null
    }
    if ([string]$manifest.repoRoot -ne $RepoRoot) {
      Write-Warning "[stop:stack] ignoring manifest for another repo: $($manifest.repoRoot)"
      return $null
    }
    return $manifest
  } catch {
    Write-Warning "[stop:stack] could not read manifest: $($_.Exception.Message)"
    return $null
  }
}

function Get-ManifestPidMap {
  $map = @{}
  $manifest = Get-StackManifest
  if (-not $manifest) {
    return $map
  }
  if ($manifest.launcherPid) {
    $map[[int]$manifest.launcherPid] = "launcher"
  }
  foreach ($service in @($manifest.services)) {
    if ($service.pid) {
      $label = if ($service.name) { [string]$service.name } else { "service" }
      $map[[int]$service.pid] = $label
      foreach ($child in @(Get-DescendantProcessInfos -ParentProcessId ([int]$service.pid))) {
        $map[[int]$child.ProcessId] = "$label-child"
      }
    }
  }
  return $map
}

function Test-KaneDevProcess {
  param(
    [object]$Info,
    [int]$Port
  )
  if (-not $Info -or -not $Info.CommandLine) {
    return $false
  }
  $lower = ([string]$Info.CommandLine).ToLowerInvariant()
  if ($lower.Contains($RepoRootLower)) {
    return $true
  }
  if ($Port -in @(8000, 8010, 8011)) {
    return ($lower.Contains("uvicorn") -and $lower.Contains("app.main:app") -and $lower.Contains([string]$Port))
  }
  if ($Port -eq 3000) {
    return ($lower.Contains("next") -and ($lower.Contains("@octopus/web") -or $lower.Contains("apps\web")))
  }
  return $false
}

function Test-HttpUp {
  param([int]$Port)
  $url = switch ($Port) {
    8000 { "http://127.0.0.1:8000/health" }
    8010 { "http://127.0.0.1:8010/health" }
    8011 { "http://127.0.0.1:8011/health" }
    default { "http://127.0.0.1:$Port/" }
  }
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -Method Get -TimeoutSec 2 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Stop-KanePid {
  param(
    [int]$ProcessId,
    [int]$Port,
    [bool]$ManifestVerified
  )
  $info = Get-ProcessInfo -ProcessId $ProcessId
  if (-not $info) {
    Write-Host "[stop:stack] safe-skip pid ${ProcessId}: process is no longer available"
    return
  }
  $name = if ($info.Name) { $info.Name } else { "unknown" }
  $cmd = if ($info.CommandLine) { $info.CommandLine } else { "" }
  $verified = $ManifestVerified -or (Test-KaneDevProcess -Info $info -Port $Port)
  if (-not $verified) {
    Write-Warning "[stop:stack] skip port $Port pid $ProcessId ($name): not manifest-owned or command-line verified for this repo"
    if ($cmd) {
      Write-Host "[stop:stack] command: $cmd"
    }
    return
  }

  $children = @(Get-DescendantProcessInfos -ParentProcessId $ProcessId)
  if ($DryRun) {
    $mode = if ($ManifestVerified) { "manifest" } else { "command-line verified" }
    Write-Host "[stop:stack] dry-run would stop port $Port pid $ProcessId ($name) [$mode]"
    foreach ($child in $children) {
      $childName = if ($child.Name) { $child.Name } else { "unknown" }
      Write-Host "[stop:stack] dry-run would stop descendant pid $($child.ProcessId) ($childName)"
    }
    return
  }

  foreach ($child in ($children | Sort-Object ProcessId -Descending)) {
    $childId = [int]$child.ProcessId
    $childName = if ($child.Name) { $child.Name } else { "unknown" }
    Write-Host "[stop:stack] stopping descendant pid $childId ($childName)"
    try {
      Stop-Process -Id $childId -ErrorAction Stop
    } catch {
      Write-Warning "[stop:stack] could not stop descendant pid ${childId}: $($_.Exception.Message)"
    }
  }

  $mode = if ($ManifestVerified) { "manifest" } else { "command-line verified" }
  Write-Host "[stop:stack] stopping port $Port pid $ProcessId ($name) [$mode]"
  try {
    Stop-Process -Id $ProcessId -ErrorAction Stop
  } catch {
    Write-Warning "[stop:stack] could not stop pid ${ProcessId}: $($_.Exception.Message)"
  }
}

for ($pass = 1; $pass -le [Math]::Max(1, $MaxPasses); $pass++) {
  $manifestPids = Get-ManifestPidMap
  $targets = @{}
  foreach ($pidValue in $manifestPids.Keys) {
    $targets[[int]$pidValue] = @{ Port = 0; Manifest = $true }
  }
  foreach ($port in $Ports) {
    foreach ($pidValue in @(Get-ListeningPidsForPort -Port $port)) {
      $manifestVerified = $manifestPids.ContainsKey([int]$pidValue)
      $targets[[int]$pidValue] = @{ Port = $port; Manifest = $manifestVerified }
    }
  }

  if ($targets.Count -eq 0) {
    if ($pass -eq 1) {
      Write-Host "[stop:stack] no manifest-owned or listening dev stack processes found"
    }
    break
  }

  foreach ($pidText in $targets.Keys) {
    $target = $targets[$pidText]
    Stop-KanePid -ProcessId ([int]$pidText) -Port ([int]$target.Port) -ManifestVerified ([bool]$target.Manifest)
  }

  if ($DryRun) {
    break
  }
  Start-Sleep -Milliseconds ([Math]::Max(100, $GraceMs))
}

if ($DryRun) {
  exit 0
}

Start-Sleep -Milliseconds ([Math]::Max(300, $GraceMs))
$failed = $false
foreach ($port in $Ports) {
  $remaining = @(Get-ListeningPidsForPort -Port $port)
  $httpUp = Test-HttpUp -Port $port
  if ($remaining.Count -eq 0 -and -not $httpUp) {
    Write-Host "[stop:stack] confirmed DOWN: $port"
    continue
  }

  $failed = $true
  $pidText = if ($remaining.Count) { ($remaining | Sort-Object -Unique) -join ", " } else { "none" }
  Write-Warning "[stop:stack] still up on $port (listener pid: $pidText, http_up: $httpUp)"
  foreach ($pidValue in $remaining) {
    $info = Get-ProcessInfo -ProcessId ([int]$pidValue)
    $name = if ($info -and $info.Name) { $info.Name } else { "unknown" }
    $cmd = if ($info -and $info.CommandLine) { $info.CommandLine } else { "<command line unavailable>" }
    Write-Warning "[stop:stack] remaining pid $pidValue ($name): $cmd"
  }
}

if ($failed) {
  Write-Error "[stop:stack] stack is not fully down; data restore is unsafe until every listed port is down"
  exit 1
}

if (Test-Path $ManifestPath) {
  Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
}
