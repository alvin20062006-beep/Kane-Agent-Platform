<#
.SYNOPSIS
  Docker Postgres → alembic upgrade → 启动 API(Postgres) + Bridge → verify_task_flow + verify_bridge_flow。

  用法（仓库根目录）:
    .\scripts\run-postgres-verify.ps1

  要求：Docker Desktop 可用；apps/api 已 pip install / venv。
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReportsDir = Join-Path $RepoRoot "reports"
if (-not (Test-Path $ReportsDir)) { New-Item -ItemType Directory -Path $ReportsDir | Out-Null }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$EvidenceFile = Join-Path $ReportsDir "postgres-verify-$stamp.log"

function Write-Evidence {
  param([string]$Line)
  Add-Content -Path $EvidenceFile -Value $Line -Encoding utf8
  Write-Host $Line
}

& (Join-Path $RepoRoot "scripts\stop-octopus-ports.ps1")

function Write-NativeLines {
  param([object[]]$Lines)
  foreach ($line in $Lines) {
    if ($null -eq $line) { continue }
    if ($line -is [System.Management.Automation.ErrorRecord]) {
      Write-Evidence ($line.Exception.Message)
    } else {
      Write-Evidence ($line.ToString())
    }
  }
}

Push-Location $RepoRoot
try {
  Write-Evidence "=== docker compose -f docker-compose.postgres.yml up -d ==="
  $oldEap = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $out = docker compose -f docker-compose.postgres.yml up -d 2>&1
    Write-NativeLines $out
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit code $LASTEXITCODE" }
  } finally {
    $ErrorActionPreference = $oldEap
  }

  Write-Evidence "=== wait postgres (pg_isready) ==="
  $deadline = (Get-Date).AddSeconds(120)
  $ready = $false
  while ((Get-Date) -lt $deadline) {
    $ErrorActionPreference = "Continue"
    $null = docker compose -f docker-compose.postgres.yml exec -T postgres pg_isready -U octopus -d octopus 2>&1
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
  }
  if (-not $ready) {
    throw "Postgres did not become ready in time (docker compose exec pg_isready failed)."
  }

  $ApiRoot = Join-Path $RepoRoot "apps\api"
  $Py = Join-Path $ApiRoot ".venv\Scripts\python.exe"
  $BridgeRoot = Join-Path $RepoRoot "apps\local-bridge"
  $BridgePy = Join-Path $BridgeRoot ".venv\Scripts\python.exe"

  $env:OCTOPUS_PERSISTENCE = "postgres"
  $env:DATABASE_URL = "postgresql+psycopg://octopus:octopus@127.0.0.1:5432/octopus"
  $env:OCTOPUS_API_PUBLIC_URL = "http://127.0.0.1:8000"
  $env:OCTOPUS_LOCAL_BRIDGE_URL = "http://127.0.0.1:8010"

  Push-Location $ApiRoot
  try {
    Write-Evidence "=== alembic upgrade head ==="
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      $ale = & $Py -m alembic -c alembic.ini upgrade head 2>&1
      Write-NativeLines @($ale)
      if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed with exit code $LASTEXITCODE" }
    } finally {
      $ErrorActionPreference = $oldEap
    }
  } finally {
    Pop-Location
  }

  $procApi = Start-Process -FilePath $Py -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
  ) -WorkingDirectory $ApiRoot -PassThru -WindowStyle Hidden

  $procBridge = Start-Process -FilePath $BridgePy -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"
  ) -WorkingDirectory $BridgeRoot -PassThru -WindowStyle Hidden

  function Wait-HttpOk {
    param([string]$Url, [int]$MaxSec = 90)
    $d = (Get-Date).AddSeconds($MaxSec)
    while ((Get-Date) -lt $d) {
      try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { return }
      } catch {}
      Start-Sleep -Seconds 1
    }
    throw "Timeout waiting for $Url"
  }

  try {
    Wait-HttpOk "http://127.0.0.1:8000/health"
    Wait-HttpOk "http://127.0.0.1:8010/health"

    $env:OCTOPUS_API_BASE_URL = "http://127.0.0.1:8000"
    Write-Evidence "=== verify_task_flow.ps1 ==="
    $v1 = & (Join-Path $RepoRoot "scripts\verify_task_flow.ps1") 2>&1
    Write-NativeLines @($v1)
    $t1 = $LASTEXITCODE

    Write-Evidence "=== verify_bridge_flow.ps1 ==="
    $v2 = & (Join-Path $RepoRoot "scripts\verify_bridge_flow.ps1") 2>&1
    Write-NativeLines @($v2)
    $t2 = $LASTEXITCODE
  } finally {
    foreach ($p in @($procBridge, $procApi)) {
      if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    & (Join-Path $RepoRoot "scripts\stop-octopus-ports.ps1")
  }

  Write-Evidence "=== verify_task_flow exit=$t1 verify_bridge_flow exit=$t2 ==="
  if ($t1 -ne 0) { exit $t1 }
  if ($t2 -ne 0) { exit $t2 }
} finally {
  Pop-Location
}

Write-Host "Evidence written to $EvidenceFile"
