<#
.SYNOPSIS
  生产模式 Web + API(File) + Bridge，健康检查后跑 Playwright E2E，并写入 reports 证据文件。

  流程：先 stop-octopus-ports → NEXT_PUBLIC 在 build 前设置 → build → 后台启动三服务 → test:e2e → 清理进程。

  用法（仓库根目录）:
    .\scripts\run-web-prod-e2e.ps1
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReportsDir = Join-Path $RepoRoot "reports"
if (-not (Test-Path $ReportsDir)) { New-Item -ItemType Directory -Path $ReportsDir | Out-Null }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$EvidenceFile = Join-Path $ReportsDir "web-prod-e2e-$stamp.log"
$e2eDataDir = $null

function Write-Evidence {
  param([string]$Line)
  Add-Content -Path $EvidenceFile -Value $Line -Encoding utf8
  Write-Host $Line
}

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

& (Join-Path $RepoRoot "scripts\stop-octopus-ports.ps1")

$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
$WebDir = Join-Path $RepoRoot "apps\web"
Push-Location $WebDir
try {
  npm run build
} finally {
  Pop-Location
}

$ApiPy = Join-Path $RepoRoot "apps\api\.venv\Scripts\python.exe"
$BridgePy = Join-Path $RepoRoot "apps\local-bridge\.venv\Scripts\python.exe"
$ApiRoot = Join-Path $RepoRoot "apps\api"
$BridgeRoot = Join-Path $RepoRoot "apps\local-bridge"

$e2eDataDir = Join-Path ([System.IO.Path]::GetTempPath()) ("octopus-e2e-data-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $e2eDataDir -Force | Out-Null
Write-Evidence "=== OCTOPUS_API_DATA_DIR (isolated) = $e2eDataDir ==="

$env:OCTOPUS_API_PUBLIC_URL = "http://127.0.0.1:8000"
$env:OCTOPUS_LOCAL_BRIDGE_URL = "http://127.0.0.1:8010"

# ProcessStartInfo 整条实参塞给 python.exe 时，在部分环境下会导致 uvicorn 解析端口异常；用 cmd 注入 env。
# 必须强制 file 存储并清空 DATABASE_URL：否则会继承当前 shell（例如刚跑过 Postgres 验证）里的 postgres 模式与共享库。
$apiCmdLine = @(
  "set `"OCTOPUS_PERSISTENCE=file`"",
  "set `"DATABASE_URL=`"",
  "set `"OCTOPUS_DATABASE_URL=`"",
  "set `"OCTOPUS_API_DATA_DIR=$e2eDataDir`"",
  "set `"OCTOPUS_API_PUBLIC_URL=http://127.0.0.1:8000`"",
  "set `"OCTOPUS_LOCAL_BRIDGE_URL=http://127.0.0.1:8010`"",
  "`"$ApiPy`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
) -join "&& "
$procApi = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $apiCmdLine) -WorkingDirectory $ApiRoot -PassThru -WindowStyle Hidden

$procBridge = Start-Process -FilePath $BridgePy -ArgumentList @(
  "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"
) -WorkingDirectory $BridgeRoot -PassThru -WindowStyle Hidden

$npmCmd = (Get-Command npm.cmd -ErrorAction Stop).Source
$procWeb = Start-Process -FilePath $npmCmd -ArgumentList @(
  "run", "start", "--", "--hostname", "127.0.0.1", "--port", "3000"
) -WorkingDirectory $WebDir -PassThru -WindowStyle Hidden

function Wait-HttpOk {
  param([string]$Url, [int]$MaxSec = 120)
  $deadline = (Get-Date).AddSeconds($MaxSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return }
    } catch {}
    Start-Sleep -Seconds 1
  }
  throw "Timeout waiting for $Url"
}

$e2eExit = 1
try {
  Wait-HttpOk "http://127.0.0.1:8000/health"
  Wait-HttpOk "http://127.0.0.1:8010/health"
  Wait-HttpOk "http://127.0.0.1:3000/tasks"

  $h = curl.exe -s "http://127.0.0.1:8000/health"
  Write-Evidence "=== curl http://127.0.0.1:8000/health ==="
  Write-Evidence $h
  Write-Evidence "=== curl http://127.0.0.1:3000/tasks (first 200 chars) ==="
  $page = Invoke-WebRequest -Uri "http://127.0.0.1:3000/tasks" -UseBasicParsing -TimeoutSec 10
  Write-Evidence ($page.Content.Substring(0, [Math]::Min(200, $page.Content.Length)))

  Push-Location $WebDir
  $env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:3000"
  $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
  $env:PLAYWRIGHT_BRIDGE_URL = "http://127.0.0.1:8010"
  Write-Evidence "=== npm run test:e2e ==="
  $eapSave = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $e2eOut = npm run test:e2e 2>&1
    Write-NativeLines @($e2eOut)
    $e2eExit = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $eapSave
  }
  if ($null -eq $e2eExit) { $e2eExit = 1 }
} finally {
  foreach ($p in @($procWeb, $procBridge, $procApi)) {
    if ($p -and -not $p.HasExited) {
      Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
  }
  & (Join-Path $RepoRoot "scripts\stop-octopus-ports.ps1")
}

if ($e2eDataDir) {
  Remove-Item -LiteralPath $e2eDataDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Evidence "=== exit code (npm test:e2e) = $e2eExit ==="
Write-Host "Evidence written to $EvidenceFile"
if ($e2eExit -ne 0) { exit $e2eExit }
