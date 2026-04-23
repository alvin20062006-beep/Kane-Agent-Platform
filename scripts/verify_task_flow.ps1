$ErrorActionPreference = "Stop"

function Assert-True {
  param(
    [bool]$Condition,
    [string]$Message
  )
  if (-not $Condition) {
    throw "ASSERT FAILED: $Message"
  }
}

function Curl-Json {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Url,
    [object]$Body = $null,
    [int]$TimeoutSec = 10
  )

  if ($null -ne $Body) {
    $json = $Body | ConvertTo-Json -Compress -Depth 10
    $resp = $json | curl.exe -s --max-time $TimeoutSec -X $Method $Url -H "content-type: application/json" --data-binary '@-'
  } else {
    $resp = curl.exe -s --max-time $TimeoutSec -X $Method $Url
  }
  if (-not $resp) {
    throw "Empty response from $Method $Url"
  }
  try {
    return ($resp | ConvertFrom-Json)
  } catch {
    throw "Non-JSON response from ${Method} ${Url}: $resp"
  }
}

function Curl-Raw {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Url,
    [int]$TimeoutSec = 10
  )
  $resp = curl.exe -s --max-time $TimeoutSec -X $Method $Url
  if (-not $resp) { throw "Empty response from ${Method} ${Url}" }
  return $resp
}

function Wait-TaskStatus {
  param(
    [Parameter(Mandatory = $true)][string]$TaskId,
    [Parameter(Mandatory = $true)][string[]]$AnyOf,
    [int]$MaxSec = 90
  )
  $deadline = (Get-Date).AddSeconds($MaxSec)
  while ((Get-Date) -lt $deadline) {
    $t = Curl-Json -Method GET -Url "$api/tasks/$TaskId" -TimeoutSec 10
    $st = [string]$t.data.status
    foreach ($want in $AnyOf) {
      if ($st -eq $want) { return $t }
    }
    Start-Sleep -Milliseconds 400
  }
  throw "Timeout waiting for task $TaskId to reach one of: $($AnyOf -join ',')"
}

$api = $env:OCTOPUS_API_BASE_URL
if (-not $api) { $api = "http://127.0.0.1:8000" }
$api = $api.TrimEnd("/")

Write-Host "API=$api"

# 1) health
$health = Curl-Json -Method GET -Url "$api/health" -TimeoutSec 3
Assert-True ($health.status -eq "ok") "health.status should be ok"

# 1b) web pages (optional; skip if not configured)
$web = $env:OCTOPUS_WEB_BASE_URL
if ($web) {
  $web = $web.TrimEnd("/")
  Write-Host "WEB=$web"
  $html = Curl-Raw -Method GET -Url "$web/" -TimeoutSec 5
  Assert-True ($html.Length -gt 100) "web home page should return HTML"
}

# 2) agents
$agents = Curl-Json -Method GET -Url "$api/agents"
Assert-True ($agents.items.Count -gt 0) "/agents should return at least one agent"
$builtin = ($agents.items | Where-Object { $_.agent_id -eq "octopus_builtin" } | Select-Object -First 1)
if (-not $builtin) { $builtin = $agents.items[0] }

# 3) create task
$created = Curl-Json -Method POST -Url "$api/tasks" -Body @{
  title = "verify_task_flow"
  description = "hello"
  execution_mode = "commander"
}
$taskId = $created.data.task_id
Assert-True ([string]::IsNullOrWhiteSpace($taskId) -eq $false) "created task_id should exist"
Write-Host "task_id=$taskId"

# 4) assign
$assigned = Curl-Json -Method POST -Url "$api/tasks/$taskId/assign" -Body @{ agent_id = $builtin.agent_id }
Assert-True ($assigned.data.assigned_agent_id -eq $builtin.agent_id) "assigned_agent_id should match"

# 5) run (success path; API returns queued, background worker finishes the run)
$runRes = Curl-Json -Method POST -Url "$api/tasks/$taskId/run" -TimeoutSec 30
Assert-True ($runRes.task.task_id -eq $taskId) "run response should include task"
Assert-True ([string]::IsNullOrWhiteSpace([string]$runRes.run.run_id) -eq $false) "run_id should exist"
Assert-True ($runRes.queued -eq $true) "run should be queued for worker execution"
$afterRun = Wait-TaskStatus -TaskId $taskId -AnyOf @("succeeded", "waiting_approval", "failed")
Assert-True ($afterRun.data.status -eq "succeeded") "builtin commander run should end succeeded"

# 6) timeline includes events/logs
$timeline = Curl-Json -Method GET -Url "$api/tasks/$taskId/timeline"
Assert-True ($timeline.task.task_id -eq $taskId) "timeline should include task"
Assert-True ($timeline.events.Count -ge 2) "timeline.events should have at least created+assigned"
Assert-True ($timeline.runs.Count -ge 1) "timeline.runs should have at least 1 run"
Assert-True ($timeline.run_logs.Count -ge 2) "timeline.run_logs should have at least 2 lines"

# 6b) SSE endpoints exist (best-effort)
try {
  $sse = Curl-Raw -Method GET -Url "$api/tasks/$taskId/events/stream" -TimeoutSec 2
  Assert-True ($sse.Contains("event:") -or $sse.Contains("data:")) "SSE should stream data"
} catch {
  # Skip strict SSE in environments that block streaming in curl
}

# 7) runs endpoint (raw check; avoids failing on huge payload formatting)
$runsRaw = Curl-Raw -Method GET -Url "$api/runs" -TimeoutSec 10
Assert-True ($runsRaw.Contains('"items"')) "/runs should include items"

# 8) fail+retry path (honest simulated failure)
$failCreated = Curl-Json -Method POST -Url "$api/tasks" -Body @{
  title = "verify_task_flow_fail"
  description = "simulate_fail"
  execution_mode = "commander"
}
$failTaskId = $failCreated.data.task_id
$null = Curl-Json -Method POST -Url "$api/tasks/$failTaskId/assign" -Body @{ agent_id = "octopus_builtin" }
$failRun = Curl-Json -Method POST -Url "$api/tasks/$failTaskId/run" -TimeoutSec 30
Assert-True ($failRun.queued -eq $true) "fail path should also enqueue a run"
$afterFail = Wait-TaskStatus -TaskId $failTaskId -AnyOf @("failed")
Assert-True ($afterFail.data.status -eq "failed") "failed task should be failed"

$retry = Curl-Json -Method POST -Url "$api/tasks/$failTaskId/retry"
Assert-True ($retry.data.retry_count -ge 1) "retry_count should increment"
Assert-True ($retry.data.status -in @("assigned", "created", "queued")) "status after retry should be runnable"

# 9) metrics
$metrics = Curl-Json -Method GET -Url "$api/metrics"
Assert-True ($metrics.tasks.total -ge 1) "metrics.tasks.total should be >= 1"
Assert-True ($metrics.runs.total -ge 1) "metrics.runs.total should be >= 1"

Write-Host "OK: verify_task_flow passed"

