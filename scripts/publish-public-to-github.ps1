# Export a filtered tree for the public GitHub mirror (excludes internal-only paths).
# Usage (from repo root): pwsh -File scripts/publish-public-to-github.ps1
# Requires: git, GitHub CLI (gh) authenticated, robocopy (Windows).

param(
    [string] $RemoteRepo = "alvin20062006-beep/Kane-Agent-Platform",
    [string] $Branch = "main",
    [switch] $ExportOnly
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DestRoot = Join-Path $env:TEMP ("kane-public-export-" + ([Guid]::NewGuid().ToString("N").Substring(0, 8)))

function Test-RobocopySuccess {
    param([int] $ExitCode)
    if ($ExitCode -ge 8) { throw "robocopy failed with exit code $ExitCode" }
}

Write-Host "Source: $SourceRoot"
Write-Host "Export: $DestRoot"

if (Test-Path $DestRoot) { Remove-Item $DestRoot -Recurse -Force }
New-Item -ItemType Directory -Path $DestRoot -Force | Out-Null

# apps/* (omit apps/data; omit local-bridge runtime handoffs)
$commonXd = @("node_modules", ".next", "__pycache__", ".venv", "venv", ".turbo", "dist", "out", ".pytest_cache", ".mypy_cache")
foreach ($app in @("api", "web", "local-bridge")) {
    $from = Join-Path $SourceRoot "apps\$app"
    $to = Join-Path $DestRoot "apps\$app"
    $xd = @($commonXd)
    if ($app -eq "local-bridge") { $xd += "data" }
    $rcArgs = @($from, $to, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS")
    foreach ($d in $xd) { $rcArgs += "/XD"; $rcArgs += $d }
    $code = robocopy @rcArgs
    Test-RobocopySuccess $LASTEXITCODE
}

$code = robocopy (Join-Path $SourceRoot "packages") (Join-Path $DestRoot "packages") /E /XD node_modules dist __pycache__ .venv /NFL /NDL /NJH /NJS /NC /NS
Test-RobocopySuccess $LASTEXITCODE

$code = robocopy (Join-Path $SourceRoot "docs") (Join-Path $DestRoot "docs") /E /NFL /NDL /NJH /NJS /NC /NS
Test-RobocopySuccess $LASTEXITCODE

if (Test-Path (Join-Path $SourceRoot "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $DestRoot "scripts") -Force | Out-Null
    Copy-Item (Join-Path $SourceRoot "scripts\*.ps1") (Join-Path $DestRoot "scripts") -Force -ErrorAction SilentlyContinue
}

$rootFiles = @(
    "package.json",
    "package-lock.json",
    "docker-compose.yml",
    "docker-compose.postgres.yml",
    ".gitignore",
    "LICENSE",
    "USER_GUIDE_LOCAL_AGENTS.md"
)
foreach ($f in $rootFiles) {
    $p = Join-Path $SourceRoot $f
    if (Test-Path $p) { Copy-Item $p (Join-Path $DestRoot $f) -Force }
}

Copy-Item (Join-Path $SourceRoot "PUBLIC_REPO_README.md") (Join-Path $DestRoot "README.md") -Force

# Remove paths that must not appear in the public repo
$strip = @(
    "docs\PRD.md",
    "docs\ROADMAP_UX_AND_THREAD.md",
    "docs\FINAL_BUILD_REPORT.md",
    "apps\web\public\docs\PRD.md",
    "apps\web\public\docs\ROADMAP_UX_AND_THREAD.md"
)
foreach ($rel in $strip) {
    $full = Join-Path $DestRoot $rel
    if (Test-Path $full) { Remove-Item $full -Force }
}

# Ensure runtime data dirs are not shipped
$dataApi = Join-Path $DestRoot "apps\api\data"
if (Test-Path $dataApi) { Remove-Item $dataApi -Recurse -Force }
$lbData = Join-Path $DestRoot "apps\local-bridge\data"
if (Test-Path $lbData) { Remove-Item $lbData -Recurse -Force }

# Optional: keep apps/data/.gitkeep only — create empty placeholder if API expects dir
$keep = Join-Path $DestRoot "apps\data"
New-Item -ItemType Directory -Path $keep -Force | Out-Null
"# Public clone: no runtime JSON here; API creates files per .gitignore.`n" | Set-Content (Join-Path $keep ".gitkeep") -Encoding utf8

Push-Location $DestRoot
try {
    git init
    git checkout -b $Branch
    git config user.email "alvin20062006-beep@users.noreply.github.com"
    git config user.name "alvin20062006-beep"
    git add -A
    git status
    git commit -m "Initial public release: Kāne Agent Platform (Kanaloa built-in agent)"

    if ($ExportOnly) {
        Write-Host "ExportOnly: skipped GitHub create/push. Next:"
        Write-Host "  1) gh auth login"
        Write-Host "  2) gh repo create $RemoteRepo --public --description `"Kāne Agent Platform — local-first control plane; built-in agent Kanaloa`""
        Write-Host "  3) git remote add origin https://github.com/$RemoteRepo.git"
        Write-Host "  4) git push -u origin $Branch"
        return
    }

    $ghExe = $null
    if (Get-Command gh -ErrorAction SilentlyContinue) { $ghExe = (Get-Command gh).Source }
    elseif (Test-Path "C:\Program Files\GitHub CLI\gh.exe") { $ghExe = "C:\Program Files\GitHub CLI\gh.exe" }
    if (-not $ghExe) { throw "GitHub CLI (gh) not found. Re-run with -ExportOnly or install gh." }

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $ghExe auth status 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "gh is not authenticated. Run: gh auth login`nThen re-run this script (or push manually from: $DestRoot)"
        }

        & $ghExe repo view $RemoteRepo 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Creating GitHub repo $RemoteRepo ..."
            & $ghExe repo create $RemoteRepo --public --description "Kane Agent Platform (Kāne): local-first control plane; built-in agent Kanaloa"
        }
    }
    finally {
        $ErrorActionPreference = $prevEap
    }

    git remote remove origin 2>$null
    git remote add origin "https://github.com/$RemoteRepo.git"
    git push -u origin $Branch
}
finally {
    Pop-Location
}

Write-Host "Done. Export left at: $DestRoot (you may delete it)."
