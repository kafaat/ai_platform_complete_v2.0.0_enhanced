<#
  SAHOOL v9.0 — Unified Orchestration Script (PowerShell — مُحوّل من run_all.sh)
  Usage: .\run_all.ps1 [up|down|logs|test|build|reset|health]  [<service> for logs]

  ملاحظة (Windows): إن ظهر "not digitally signed":
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   (دائم، آمن)
    أو: powershell -ExecutionPolicy Bypass -File .\run_all.ps1
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('up', 'down', 'logs', 'test', 'build', 'health', 'reset')]
    [string]$Command = 'up',

    [Parameter(Position = 1)]
    [string]$Service
)

$ErrorActionPreference = 'Stop'

# ضمان إخراج عربي سليم في الطرفيّة (UTF-8)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir   = $PSScriptRoot
$ProjectDir  = Split-Path -Parent $ScriptDir
$ComposeFile = Join-Path $ProjectDir 'docker-compose.v9.yml'
$EnvFile     = Join-Path $ProjectDir '.env'

function Log-Info { param($m) Write-Host "[INFO] $m"  -ForegroundColor Blue }
function Log-Ok   { param($m) Write-Host "[OK] $m"    -ForegroundColor Green }
function Log-Warn { param($m) Write-Host "[WARN] $m"  -ForegroundColor Yellow }
function Log-Err  { param($m) Write-Host "[ERROR] $m" -ForegroundColor Red }

# ─── Check Dependencies ───
function Check-Deps {
    Log-Info 'Checking dependencies...'
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Log-Err 'Docker not installed'; exit 1 }
    # docker compose (v2) plugin
    try { docker compose version | Out-Null } catch { Log-Err 'docker compose not installed'; exit 1 }
    Log-Ok 'Docker + docker compose found'
}

# ─── Generate .env if missing ───
function Generate-Env {
    if (Test-Path $EnvFile) { Log-Ok '.env exists'; return }
    Log-Warn '.env not found -- generating from template'
    $tpl = @'
# SAHOOL v9.0 -- Environment Configuration
# !! CHANGE ALL SECRETS BEFORE PRODUCTION

# Database (compose يستخدم DB_PASSWORD — وُحّد الاسمان)
POSTGRES_PASSWORD=<set-in-secret-manager>
DB_PASSWORD=sahool_secure_db_2026_change_me

# JWT
JWT_SECRET=<set-in-secret-manager>

# MinIO
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=<set-in-secret-manager>

# Sentinel Hub (Copernicus Data Space)
SH_CLIENT_ID=your_sentinel_hub_client_id
SH_CLIENT_SECRET=<set-in-secret-manager>
SH_INSTANCE_ID=your_instance_id

# SAHOOL Agent
SAHOOL_AGENT_TOKEN=<set-in-secret-manager>
EDGE_SYNC_TOKEN=edge_sync_token_change_me_64chars

# Telegram Bot
TELEGRAM_BOT_TOKEN=<set-in-secret-manager>

# Grafana
GRAFANA_PASSWORD=<set-in-secret-manager>

# Mapbox (optional, for fallback maps)
MAPBOX_TOKEN=your_mapbox_token

# Edge Device
EDGE_DEVICE=rpi5
OFFLINE_MODE=false
'@
    Set-Content -Path $EnvFile -Value $tpl -Encoding UTF8
    Log-Warn 'Generated .env -- EDIT SECRETS BEFORE RUNNING!'
}

# ─── Health Check ───
function Health-Check {
    Log-Info 'Running health checks...'
    $services = @(
        @{ Name = 'sahool-auth';             Port = 8120 },
        @{ Name = 'sahool-sentinel-hub-mcp'; Port = 8091 },
        @{ Name = 'sahool-weather-mcp';      Port = 8092 },
        @{ Name = 'sahool-wofost-mcp';       Port = 8093 },
        @{ Name = 'sahool-market-mcp';       Port = 8094 },
        @{ Name = 'sahool-supervisor';       Port = 8096 },
        @{ Name = 'sahool-guardrails';       Port = 8097 },
        @{ Name = 'sahool-edge';             Port = 8100 },
        @{ Name = 'sahool-postgis';          Port = 5432 },
        @{ Name = 'sahool-redis';            Port = 6379 },
        @{ Name = 'sahool-nats';             Port = 8222 },
        @{ Name = 'sahool-minio';            Port = 9000 },
        @{ Name = 'sahool-qdrant';           Port = 6333 }
    )
    $passed = 0; $failed = 0
    foreach ($svc in $services) {
        $ok = $false
        foreach ($path in @('/healthz', '/readyz')) {
            try {
                Invoke-WebRequest -Uri "http://localhost:$($svc.Port)$path" -UseBasicParsing -TimeoutSec 3 | Out-Null
                $ok = $true; break
            } catch {}
        }
        # فحص المنافذ الخام (postgres/redis) عبر اتصال TCP
        if (-not $ok -and ($svc.Port -in 5432, 6379)) {
            try {
                $tcp = New-Object System.Net.Sockets.TcpClient
                $tcp.Connect('localhost', $svc.Port); $ok = $tcp.Connected; $tcp.Close()
            } catch {}
        }
        if ($ok) { Log-Ok "  + $($svc.Name) (port $($svc.Port))"; $passed++ }
        else     { Log-Err "  - $($svc.Name) (port $($svc.Port)) -- NOT READY"; $failed++ }
    }
    Write-Host ''
    Log-Info "Health Check Results: $passed passed, $failed failed"
    if ($failed -gt 0) {
        Log-Warn 'Some services are not ready. Check logs with: .\run_all.ps1 logs'
        return $false
    }
    Log-Ok 'All systems operational!'
    return $true
}

# ─── Start Services ───
function Cmd-Up {
    Check-Deps
    Generate-Env
    Log-Info 'Starting SAHOOL v9.0...'
    Push-Location $ProjectDir
    docker compose -f $ComposeFile --env-file $EnvFile up -d --build
    Pop-Location
    Log-Info 'Waiting for services to initialize (30s)...'
    Start-Sleep -Seconds 30
    try { Health-Check | Out-Null } catch {}
    Log-Ok 'SAHOOL v9.0 is running!'
    Write-Host ''
    Write-Host '  Dashboard:    http://localhost:3001 (Grafana)'
    Write-Host '  API Gateway:  http://localhost:80'
    Write-Host '  Supervisor:   http://localhost:8096'
    Write-Host '  MCP Sentinel: http://localhost:8091'
    Write-Host '  MCP Weather:  http://localhost:8092'
    Write-Host '  MCP WOFOST:   http://localhost:8093'
    Write-Host '  MCP Market:   http://localhost:8094'
    Write-Host '  Guardrails:   http://localhost:8097'
    Write-Host '  Edge AI:      http://localhost:8100'
    Write-Host '  Prometheus:   http://localhost:9090'
    Write-Host '  MinIO:        http://localhost:9001'
}

# ─── Stop Services ───
function Cmd-Down {
    Log-Info 'Stopping SAHOOL v9.0...'
    Push-Location $ProjectDir
    docker compose -f $ComposeFile down --remove-orphans
    Pop-Location
    Log-Ok 'All services stopped'
}

# ─── View Logs ───
function Cmd-Logs {
    Push-Location $ProjectDir
    if ($Service) {
        docker compose -f $ComposeFile logs -f $Service
    } else {
        docker compose -f $ComposeFile logs -f --tail=100
    }
    Pop-Location
}

# ─── Run Tests ───
function Cmd-Test {
    Log-Info 'Running integration tests...'
    Push-Location $ProjectDir
    if (-not (Test-Path 'tests\requirements-test.txt')) {
        Log-Err 'Test dependencies not found. Run: pip install -r tests/requirements-test.txt'
        Pop-Location; exit 1
    }
    try { python -m pytest tests/ -v --tb=short -m "not slow" } catch {}
    Pop-Location
    Log-Ok 'Tests complete'
}

# ─── Build Images ───
function Cmd-Build {
    Log-Info 'Building all Docker images...'
    Push-Location $ProjectDir
    docker compose -f $ComposeFile build --parallel
    Pop-Location
    Log-Ok 'Build complete'
}

# ─── Reset (DANGER: destroys data) ───
function Cmd-Reset {
    Log-Warn 'This will DESTROY all data volumes!'
    $confirm = Read-Host "Are you sure? Type 'RESET' to confirm"
    if ($confirm -ne 'RESET') { Log-Info 'Reset cancelled'; exit 0 }
    Push-Location $ProjectDir
    docker compose -f $ComposeFile down -v --remove-orphans
    docker volume prune -f
    Pop-Location
    Log-Ok "All data reset. Run '.\run_all.ps1 up' to restart."
}

# ─── Main ───
switch ($Command) {
    'up'     { Cmd-Up }
    'down'   { Cmd-Down }
    'logs'   { Cmd-Logs }
    'test'   { Cmd-Test }
    'build'  { Cmd-Build }
    'health' { Health-Check | Out-Null }
    'reset'  { Cmd-Reset }
}
