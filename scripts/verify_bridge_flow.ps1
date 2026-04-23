$ErrorActionPreference = "Stop"

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw "ASSERT FAILED: $Message" }
}

function Curl-Json {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Url,
    [object]$Body = $null,
    [int]$TimeoutSec = 10,
    [hashtable]$Headers = @{}
  )

  $headerArgs = @()
  foreach ($k in $Headers.Keys) {
    $headerArgs += @("-H", "${k}: $($Headers[$k])")
  }

  if ($null -ne $Body) {
    $json = $Body | ConvertTo-Json -Compress -Depth 10
    $resp = $json | curl.exe -s --max-time $TimeoutSec -X $Method $Url @headerArgs -H "content-type: application/json" --data-binary '@-'
  } else {
    $resp = curl.exe -s --max-time $TimeoutSec -X $Method $Url @headerArgs
  }
  if (-not $resp) { throw "Empty response from $Method $Url" }
  try { return ($resp | ConvertFrom-Json) } catch { throw "Non-JSON response from ${Method} ${Url}: $resp" }
}

function Wait-TimelineSucceeded {
  param([string]$TaskId, [int]$MaxSec = 45)
  $deadline = (Get-Date).AddSeconds($MaxSec)
  while ((Get-Date) -lt $deadline) {
    $tl = Curl-Json -Method GET -Url "$api/tasks/$TaskId/timeline" -TimeoutSec 10
    if ([string]$tl.task.status -eq "succeeded") { return $tl }
    Start-Sleep -Milliseconds 350
  }
  throw "Timeout waiting for task $TaskId status=succeeded after bridge callback"
}

$api = $env:OCTOPUS_API_BASE_URL
if (-not $api) { $api = "http://127.0.0.1:8000" }
$api = $api.TrimEnd("/")

$bridge = $env:OCTOPUS_LOCAL_BRIDGE_URL
if (-not $bridge) { $bridge = "http://127.0.0.1:8010" }
$bridge = $bridge.TrimEnd("/")

$bridgeSecret = $env:OCTOPUS_BRIDGE_SHARED_SECRET
$headers = @{}
if ($bridgeSecret) { $headers["X-Octopus-Bridge-Key"] = $bridgeSecret }

Write-Host "API=$api"
Write-Host "BRIDGE=$bridge"

# 1) Bridge health
$bh = Curl-Json -Method GET -Url "$bridge/health" -TimeoutSec 3
Assert-True ($bh.status -eq "ok") "bridge health should be ok"

# 2) Register an adapter/agent in Octopus API's bridge registry (API persists this)
$reg = Curl-Json -Method POST -Url "$api/local-bridge/register" -TimeoutSec 5 -Body @{
  agent_id = "bridge_verify_agent"
  display_name = "Bridge Verify Agent"
  adapter_id = "cursor_cli"
  status = "idle"
  capabilities = @{ can_chat = $true; can_code = $true; can_use_skills = $true }
} -Headers $headers
Assert-True ($reg.ok -eq $true) "api local-bridge/register should return ok=true"

# 3) Create direct_agent task and assign external-ish agent (if exists); otherwise reuse the registered bridge agent id
$agents = Curl-Json -Method GET -Url "$api/agents" -TimeoutSec 5
$ext = ($agents.items | Where-Object { $_.type -eq "external" } | Select-Object -First 1)
$agentId = if ($ext) { $ext.agent_id } else { "bridge_verify_agent" }

$created = Curl-Json -Method POST -Url "$api/tasks" -TimeoutSec 5 -Body @{
  title = "verify_bridge_flow"
  description = "handoff test"
  execution_mode = "direct_agent"
}
$taskId = $created.data.task_id
Assert-True ([string]::IsNullOrWhiteSpace([string]$taskId) -eq $false) "task_id should exist"

$assign = Curl-Json -Method POST -Url "$api/tasks/$taskId/assign" -TimeoutSec 5 -Body @{ agent_id = $agentId }
Assert-True ($assign.data.task_id -eq $taskId) "assign should keep task_id"

# 4) Run (expected: may become waiting_approval with pending_handoff=true depending on adapter)
$run = Curl-Json -Method POST -Url "$api/tasks/$taskId/run" -TimeoutSec 30
Assert-True ([string]::IsNullOrWhiteSpace([string]$run.run.run_id) -eq $false) "run_id should exist"
$runId = $run.run.run_id

# 5) Complete via integrations callback (always supported by API)
$complete = Curl-Json -Method POST -Url "$api/integrations/bridge/complete" -TimeoutSec 10 -Body @{
  task_id = $taskId
  run_id = $runId
  status = "succeeded"
  integration_path = "manual_handoff"
  output = "verify_bridge_flow: completed manually"
} -Headers $headers
Assert-True ($complete.ok -eq $true) "bridge complete should return ok=true"

# 6) Timeline reflects success (worker / DB visibility can lag one beat behind the callback)
$timeline = Wait-TimelineSucceeded -TaskId $taskId
Assert-True ($timeline.task.status -eq "succeeded") "task should be succeeded after callback"

Write-Host "OK: verify_bridge_flow passed"

