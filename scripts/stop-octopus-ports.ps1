<#
.SYNOPSIS
  释放 Octopus 本地联调常用端口上的监听进程（先停旧再启新）。

.DESCRIPTION
  默认处理 3000(Web)、8000(API)、8010(Local Bridge)。仅终止 LISTEN 状态的 OwningProcess。
#>
param(
  [int[]]$Ports = @(3000, 8000, 8010)
)
$ErrorActionPreference = "Stop"

foreach ($port in $Ports) {
  $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  if (-not $conns) {
    Write-Host "Port $port : no listener"
    continue
  }
  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $pids) {
    if (-not $procId -or $procId -lt 100) { continue }
    try {
      $p = Get-Process -Id $procId -ErrorAction Stop
      Write-Host "Stopping PID $procId ($($p.ProcessName)) on port $port"
      Stop-Process -Id $procId -Force -ErrorAction Stop
    } catch {
      Write-Warning "Could not stop PID $procId on port $port : $_"
    }
  }
}

Write-Host "OK: stop-octopus-ports finished"
