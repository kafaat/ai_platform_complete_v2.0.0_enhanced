<#
  SAHOOL v9.0 — run_all.ps1 (PowerShell — مُحوّل من run_all.sh)
  الاستخدام:
    .\run_all.ps1            # تشغيل كامل (افتراضي)
    .\run_all.ps1 -Setup     # إعداد البيئة فقط
    .\run_all.ps1 -Status    # حالة الخدمات
    .\run_all.ps1 -Stop      # إيقاف كل شيء

  ملاحظة (Windows): إن ظهر خطأ "not digitally signed"، شغّل مرّة واحدة:
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  أو لهذه الجلسة فقط:
    Set-ExecutionPolicy -Scope Process Bypass
  أو دون تغيير أيّ سياسة:
    powershell -ExecutionPolicy Bypass -File .\run_all.ps1
  وإن بقي المنع (الملفّ مُنزَّل من الإنترنت):
    Get-ChildItem -Recurse *.ps1 | Unblock-File
#>
[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$Status,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'

# ضمان إخراج عربي سليم في الطرفيّة (UTF-8)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

function Log  { param($m) Write-Host "[OK] $m"   -ForegroundColor Green }
function Warn { param($m) Write-Host "[!] $m"    -ForegroundColor Yellow }
function Err  { param($m) Write-Host "[X] $m"    -ForegroundColor Red; exit 1 }
function Hdr  { param($m) Write-Host "`n-- $m --" -ForegroundColor Cyan }

$ScriptDir   = $PSScriptRoot
$ProdDir     = $ScriptDir
$FrontendDir = Join-Path $ProdDir 'frontend'
$EnvFile     = Join-Path $ProdDir '.env'
$ComposeFile = Join-Path $ProdDir 'docker-compose.v9.yml'

# بناء وسيطات docker-compose (مع env-file إن وُجد)
function Get-ComposeArgs {
    $a = @('-f', $ComposeFile)
    if (Test-Path $EnvFile) { $a += @('--env-file', $EnvFile) }
    return $a
}

Write-Host @"
  +===================================================+
  |  SAHOOL v9.0 — الزراعة الذكية اليمنية v9          |
  |  10 اصلاحات حرجة + Supervisor + Guardrails + Edge |
  +===================================================+
"@ -ForegroundColor Green

function Invoke-Setup {
    Hdr 'اعداد البيئة'
    foreach ($cmd in @('docker', 'docker-compose')) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Err "$cmd مطلوب" }
    }
    if (-not (Test-Path $EnvFile)) {
        Copy-Item (Join-Path $ProdDir '.env.example') $EnvFile
        Warn 'تم انشاء .env — عدّل JWT_SECRET: openssl rand -hex 32'
    } else {
        Log '.env موجود'
    }
    if (Test-Path (Join-Path $ProdDir 'frontend\src')) { Log 'frontend مدمج' }

    foreach ($d in @('certs', 'models\rl', 'grafana\provisioning\dashboards', 'grafana\provisioning\datasources')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $ProdDir $d) | Out-Null
    }
    $gfds = @'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://sahool-prometheus:9090
    isDefault: true
'@
    Set-Content -Path (Join-Path $ProdDir 'grafana\provisioning\datasources\prometheus.yml') -Value $gfds -Encoding UTF8
    Log 'اعداد مكتمل — شغّل: .\run_all.ps1'
}

function Test-Jwt {
    # قراءة JWT_SECRET من .env
    $jwt = $null
    if (Test-Path $EnvFile) {
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match '^\s*JWT_SECRET\s*=\s*(.+)$') { $jwt = $Matches[1].Trim() }
        }
    }
    if ([string]::IsNullOrEmpty($jwt) -or $jwt -like '*CHANGE_THIS*') {
        Err "JWT_SECRET غير محدد!`nشغّل: openssl rand -hex 32"
    }
    if ($jwt.Length -lt 32) { Warn 'JWT_SECRET قصير — يُنصح بـ 64 حرف' }
    Log 'JWT_SECRET موجود'
}

function Wait-For {
    param([string]$Url, [string]$Name, [int]$Max = 80)
    Write-Host "  انتظار $Name" -NoNewline
    for ($i = 1; $i -le $Max; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host ' OK' -ForegroundColor Green
            return $true
        } catch {
            Write-Host '.' -NoNewline
            Start-Sleep -Seconds 3
        }
    }
    Write-Host ' timeout' -ForegroundColor Yellow
    return $false
}

function Start-Backend {
    Hdr 'تشغيل Docker Compose (v9)'
    Push-Location $ProdDir
    $ca = Get-ComposeArgs
    try { docker-compose @ca pull --quiet 2>$null } catch {}
    docker-compose @ca up -d --build
    Start-Sleep -Seconds 20
    Hdr 'فحص الجاهزية'
    Wait-For 'http://localhost:8120/readyz' 'auth (:8120)'        40 | Out-Null
    Wait-For 'http://localhost:8091/readyz' 'indicators (:8091)'  40 | Out-Null
    Wait-For 'http://localhost:8092/readyz' 'weather (:8092)'     30 | Out-Null
    Wait-For 'http://localhost:8094/readyz' 'soil (:8094)'        30 | Out-Null
    Wait-For 'http://localhost:8090/readyz' 'vegetation (:8090)'  30 | Out-Null
    Wait-For 'http://localhost:8123/health' 'notification (:8123)' 30 | Out-Null
    Wait-For 'http://localhost:8096/readyz' 'supervisor (:8096)'  40 | Out-Null
    Pop-Location
    Log 'الخدمات جاهزة'
}

function Start-FrontendDev {
    Hdr 'الواجهة الأمامية'
    $running = $false
    try {
        $names = docker ps --format '{{.Names}}' 2>$null
        if ($names -match 'sahool-frontend') { $running = $true }
    } catch {}
    if ($running) { Log 'Frontend يعمل على http://localhost:3000 (Docker)'; return }

    if ((Test-Path $FrontendDir) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
        Push-Location $FrontendDir
        if (-not (Test-Path 'node_modules')) { npm install --legacy-peer-deps }
        $fe = @'
VITE_API_URL=http://localhost:8000
VITE_INDICATORS_URL=http://localhost:8091
VITE_VEGETATION_URL=http://localhost:8090
VITE_WEATHER_URL=http://localhost:8092
VITE_SOIL_URL=http://localhost:8094
VITE_AUTH_URL=http://localhost:8120
VITE_WS_URL=ws://localhost:8123/ws/notifications
VITE_MOCK_MODE=false
'@
        Set-Content -Path '.env.local' -Value $fe -Encoding UTF8
        # npm على Windows ملفّ .cmd لا .exe — يُشغّل عبر cmd.exe
        $proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', 'npm', 'run', 'dev' -PassThru -WindowStyle Hidden
        $proc.Id | Set-Content -Path (Join-Path $env:TEMP 'sahool_fe.pid')
        Start-Sleep -Seconds 3
        Log 'Frontend Dev: http://localhost:5173'
        Pop-Location
    }
}

function Show-Status {
    Hdr 'حالة SAHOOL v9'
    Push-Location $ProdDir
    $ca = Get-ComposeArgs
    try { docker-compose @ca ps 2>$null } catch {}
    Pop-Location
    Write-Host ''
    $checks = @(
        @{ Port = 8120; Path = '/readyz'; Name = 'auth' },
        @{ Port = 8091; Path = '/readyz'; Name = 'indicators' },
        @{ Port = 8090; Path = '/readyz'; Name = 'vegetation' },
        @{ Port = 8092; Path = '/readyz'; Name = 'weather' },
        @{ Port = 8094; Path = '/readyz'; Name = 'soil' },
        @{ Port = 8096; Path = '/health'; Name = 'supervisor-agent' },
        @{ Port = 8097; Path = '/health'; Name = 'guardrails-engine' },
        @{ Port = 8123; Path = '/health'; Name = 'notification' },
        @{ Port = 3003; Path = '/index.html'; Name = 'frontend' },
        @{ Port = 9090; Path = '/-/healthy'; Name = 'prometheus' }
    )
    foreach ($c in $checks) {
        $url = "http://localhost:$($c.Port)$($c.Path)"
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host "  [OK] $($c.Name) (:$($c.Port))" -ForegroundColor Green
        } catch {
            Write-Host "  [X] $($c.Name) (:$($c.Port))" -ForegroundColor Red
        }
    }
}

function Stop-All {
    Hdr 'ايقاف'
    $pidFile = Join-Path $env:TEMP 'sahool_fe.pid'
    if (Test-Path $pidFile) {
        try { Stop-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue } catch {}
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
    Push-Location $ProdDir
    $ca = Get-ComposeArgs
    docker-compose @ca down
    Pop-Location
    Log 'متوقف'
}

function Show-Summary {
    Hdr 'SAHOOL v9 جاهز'
    Write-Host ''
    Write-Host '  الواجهة:   http://localhost:3003 | http://localhost:5173' -ForegroundColor Cyan
    Write-Host '  الدخول:    admin@sahool.ye / Admin@2026!' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  APIs:      :8120 auth | :8091 indicators | :8090 vegetation' -ForegroundColor Cyan
    Write-Host '             :8092 weather | :8094 soil'
    Write-Host '             :8096 supervisor-agent | :8097 guardrails' -ForegroundColor Cyan
    Write-Host '             :8123 notifications (WebSocket)'
    Write-Host '  Monitor:   :9090 prometheus | :3001 grafana | :8222 nats' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '  أوامر:' -ForegroundColor Cyan
    Write-Host '    .\run_all.ps1 -Status'
    Write-Host '    .\run_all.ps1 -Stop'
    Write-Host ''
}

# ─── التوجيه (مكافئ case في bash) ───
if ($Setup) {
    Invoke-Setup
} elseif ($Stop) {
    Stop-All
} elseif ($Status) {
    Show-Status
} else {
    if (-not (Test-Path $EnvFile)) { Warn '.env غير موجود'; Invoke-Setup }
    Test-Jwt
    Start-Backend
    Start-FrontendDev
    Show-Summary
}
