$ErrorActionPreference = "Stop"

$ApiBase = if ($env:E2E_API_BASE_URL) { $env:E2E_API_BASE_URL } else { "http://127.0.0.1:8000" }
$BridgeBase = if ($env:E2E_BRIDGE_BASE_URL) { $env:E2E_BRIDGE_BASE_URL } else { "http://127.0.0.1:8010" }
$WebBase = if ($env:E2E_WEB_BASE_URL) { $env:E2E_WEB_BASE_URL } else { "http://localhost:3000" }
$TimeoutSeconds = if ($env:E2E_WAIT_TIMEOUT_SECONDS) { [int]$env:E2E_WAIT_TIMEOUT_SECONDS } else { 90 }

$Targets = @(
  @{ Name = "api"; Url = "$ApiBase/health" },
  @{ Name = "bridge"; Url = "$BridgeBase/health" },
  @{ Name = "web"; Url = "$WebBase/conversations" }
)

function Test-EndpointReady {
  param([string]$Url)
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$pending = @($Targets)

while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline) {
  $next = @()
  foreach ($target in $pending) {
    if (Test-EndpointReady -Url $target.Url) {
      Write-Host "[wait:stack] ready: $($target.Name) $($target.Url)"
    } else {
      $next += $target
    }
  }
  $pending = $next
  if ($pending.Count -gt 0) {
    Start-Sleep -Seconds 1
  }
}

if ($pending.Count -gt 0) {
  foreach ($target in $pending) {
    Write-Error "[wait:stack] timeout waiting for $($target.Name) $($target.Url)"
  }
  exit 1
}

Write-Host "[wait:stack] all services ready"
