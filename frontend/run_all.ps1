<#
  SAHOOL v8.0 — سكريبت التشغيل الشامل (PowerShell — مُحوّل من run_all.sh)
  يبني ويشغّل الخلفية + الواجهة الأمامية معاً

  ملاحظة (Windows): إن ظهر "not digitally signed":
    Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   (دائم، آمن)
    أو: powershell -ExecutionPolicy Bypass -File .\run_all.ps1

  الاستخدام:
    .\run_all.ps1                  # تشغيل كامل
    .\run_all.ps1 -BackendOnly     # الخلفية فقط
    .\run_all.ps1 -FrontendOnly    # الواجهة فقط
    .\run_all.ps1 -Stop            # إيقاف كل شيء
    .\run_all.ps1 -Status          # حالة الخدمات
#>
[CmdletBinding()]
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

# ضمان إخراج عربي سليم في الطرفيّة (UTF-8)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

function Log     { param($m) Write-Host "[SAHOOL] $m" -ForegroundColor Green }
function Warn    { param($m) Write-Host "[!] $m"      -ForegroundColor Yellow }
function Fail    { param($m) Write-Host "[X] $m"      -ForegroundColor Red; exit 1 }
function Section {
    param($m)
    Write-Host "`n======================================" -ForegroundColor Blue
    Write-Host "  $m" -ForegroundColor Cyan
    Write-Host "======================================" -ForegroundColor Blue
}

$ScriptDir   = $PSScriptRoot
$BackendDir  = $ScriptDir
$FrontendDir = Join-Path $ScriptDir 'frontend'
$EnvFile     = Join-Path $ScriptDir '.env'

# تحديد الوضع
$Mode = 'all'
if ($BackendOnly)  { $Mode = 'backend' }
if ($FrontendOnly) { $Mode = 'frontend' }
if ($Stop)         { $Mode = 'stop' }
if ($Status)       { $Mode = 'status' }

function Check-Deps {
    Section 'فحص الأدوات المطلوبة'
    $missing = @()
    foreach ($cmd in @('docker', 'docker-compose', 'node', 'npm', 'curl')) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) { Log "+ $cmd متاح" }
        else { $missing += $cmd }
    }
    if ($missing.Count -gt 0) {
        Fail "أدوات ناقصة: $($missing -join ', ')`nثبّت Docker وNode.js أولاً."
    }
}

function Setup-Env {
    Section 'اعداد متغيرات البيئة'
    if (-not (Test-Path $EnvFile)) {
        Warn 'ملف .env غير موجود — انشاء نسخة افتراضية...'
        $tpl = @'
# SAHOOL v8.0 — Environment Variables
# عدّل هذه القيم قبل النشر!

POSTGRES_PASSWORD=sahool_secure_pass_2026
REDIS_PASSWORD=redis_secure_pass_2026
MINIO_ROOT_USER=sahool
MINIO_ROOT_PASSWORD=minio_secure_pass_2026
GRAFANA_PASSWORD=grafana_pass_2026

# JWT (أنشئ بـ: openssl rand -hex 32)
JWT_SECRET=change_this_to_a_256bit_random_string_before_deployment

# Copernicus (اختياري - للصور الحقيقية)
COPERNICUS_USER=
COPERNICUS_PASSWORD=

# Claude API (للشات بوت)
VITE_CLAUDE_API_KEY=
'@
        Set-Content -Path $EnvFile -Value $tpl -Encoding UTF8
        Warn 'عدّل .env قبل النشر — خاصةً JWT_SECRET وكلمات المرور!'
    } else {
        Log '+ ملف .env موجود'
    }
}

function Wait-ForService {
    param([string]$Url, [string]$Name, [int]$Max = 60)
    Write-Host "  انتظار $Name" -NoNewline
    for ($i = 1; $i -le $Max; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host ' OK' -ForegroundColor Green
            return $true
        } catch {
            Write-Host '.' -NoNewline
            Start-Sleep -Seconds 2
        }
    }
    Write-Host ' timeout' -ForegroundColor Red
    return $false
}

function Start-Backend {
    Section 'تشغيل الخدمات الخلفية (Docker Compose)'
    Push-Location $BackendDir

    if (Test-Path 'migrations\init_v8.sql') {
        Log 'سيتم تطبيق init_v8.sql تلقائياً عند أول تشغيل'
    }

    Log 'بناء وتشغيل الحاويات...'
    try { docker-compose pull --quiet 2>$null } catch {}
    docker-compose up -d --build

    Section 'انتظار جاهزية الخدمات'
    $services = @(
        @{ Url = 'http://localhost:8091/health'; Name = 'indicators-service' },
        @{ Url = 'http://localhost:8090/health'; Name = 'vegetation-service' },
        @{ Url = 'http://localhost:8092/health'; Name = 'weather-service' },
        @{ Url = 'http://localhost:8094/health'; Name = 'soil-service' },
        @{ Url = 'http://localhost:8000/health'; Name = 'kong-gateway' }
    )
    Start-Sleep -Seconds 10
    foreach ($svc in $services) {
        if (-not (Wait-ForService $svc.Url $svc.Name 30)) {
            Warn "الخدمة $($svc.Name) لم تبدأ — تحقق من logs"
        }
    }
    Pop-Location

    Log 'الخدمات الخلفية تعمل'
    Write-Host ''
    Write-Host '  Kong Gateway:   http://localhost:8000'  -ForegroundColor Cyan
    Write-Host '  Indicators:     http://localhost:8091/docs' -ForegroundColor Cyan
    Write-Host '  Weather:        http://localhost:8092/docs' -ForegroundColor Cyan
    Write-Host '  Soil:           http://localhost:8094/docs' -ForegroundColor Cyan
    Write-Host '  Prometheus:     http://localhost:9090' -ForegroundColor Cyan
    Write-Host '  Grafana:        http://localhost:3001' -ForegroundColor Cyan
    Write-Host '  NATS Monitor:   http://localhost:8222' -ForegroundColor Cyan
}

function Start-FrontendDev {
    Section 'تشغيل الواجهة الأمامية (Development)'
    Push-Location $FrontendDir

    if (-not (Test-Path 'node_modules')) {
        Log 'تثبيت الاعتماديات...'
        npm install --legacy-peer-deps
    }

    $fe = @'
VITE_API_URL=http://localhost:8000
VITE_INDICATORS_URL=http://localhost:8091
VITE_VEGETATION_URL=http://localhost:8090
VITE_WEATHER_URL=http://localhost:8092
VITE_SOIL_URL=http://localhost:8094
VITE_AUTH_URL=http://localhost:8120
VITE_MOCK_MODE=false
'@
    Set-Content -Path (Join-Path $FrontendDir '.env.local') -Value $fe -Encoding UTF8

    Log 'تشغيل Vite Dev Server...'
    # npm على Windows ملفّ .cmd لا .exe — يُشغّل عبر cmd.exe
    $proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', 'npm', 'run', 'dev' -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content -Path (Join-Path $env:TEMP 'sahool_frontend.pid')

    Start-Sleep -Seconds 3
    Log 'الواجهة الأمامية تعمل على:'
    Write-Host '  http://localhost:5173' -ForegroundColor Cyan
    Pop-Location
}

function Show-Status {
    Section 'حالة الخدمات'
    Write-Host ''
    $services = @(
        @{ Port = 8091; Path = '/health';     Name = 'indicators-service (33 مؤشر)' },
        @{ Port = 8090; Path = '/health';     Name = 'vegetation-service (Sentinel-2)' },
        @{ Port = 8092; Path = '/health';     Name = 'weather-service (WOFOST)' },
        @{ Port = 8094; Path = '/health';     Name = 'soil-service (FAO)' },
        @{ Port = 8000; Path = '/';           Name = 'kong-gateway' },
        @{ Port = 8222; Path = '/healthz';    Name = 'nats-jetstream' },
        @{ Port = 9090; Path = '/-/healthy';  Name = 'prometheus' },
        @{ Port = 3001; Path = '/api/health'; Name = 'grafana' },
        @{ Port = 5173; Path = '/index.html'; Name = 'frontend-dev' },
        @{ Port = 3000; Path = '/index.html'; Name = 'frontend-prod' }
    )
    foreach ($svc in $services) {
        $url = "http://localhost:$($svc.Port)$($svc.Path)"
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host "  [OK] $($svc.Name) (localhost:$($svc.Port))" -ForegroundColor Green
        } catch {
            Write-Host "  [X] $($svc.Name) (localhost:$($svc.Port)) — غير متاح" -ForegroundColor Red
        }
    }
    Write-Host ''
    Write-Host 'Docker containers:'
    try { docker-compose ps 2>$null } catch { Write-Host '(docker-compose غير متاح)' }
}

function Stop-All {
    Section 'ايقاف جميع الخدمات'
    $pidFile = Join-Path $env:TEMP 'sahool_frontend.pid'
    if (Test-Path $pidFile) {
        try { Stop-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue } catch {}
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        Log '+ Frontend dev server stopped'
    }
    Push-Location $BackendDir
    docker-compose down
    Pop-Location
    Log 'جميع الخدمات متوقفة'
}

function Run-HealthCheck {
    Section 'فحص صحة النظام'
    $failed = 0
    $urls = @(
        'http://localhost:8091/readyz',
        'http://localhost:8090/readyz',
        'http://localhost:8092/readyz',
        'http://localhost:8094/readyz'
    )
    foreach ($url in $urls) {
        $name = $url -replace 'http://localhost:', '' -replace '/readyz', ''
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($resp.Content -match '"status"\s*:\s*"ready"') {
                Write-Host "  [OK] :$name — جاهز" -ForegroundColor Green
            } else {
                Write-Host "  [X] :$name — degraded" -ForegroundColor Yellow
                $failed++
            }
        } catch {
            Write-Host "  [X] :$name — degraded" -ForegroundColor Yellow
            $failed++
        }
    }
    Write-Host ''
    if ($failed -eq 0) { Log 'جميع الخدمات صحية' }
    else { Warn "$failed خدمة غير جاهزة — تحقق من logs" }
}

function Show-Summary {
    Section 'ملخص النظام'
    Write-Host '  SAHOOL v8.0 — الزراعة الذكية اليمنية' -ForegroundColor White
    Write-Host ''
    Write-Host '  الواجهة:' -ForegroundColor Cyan
    Write-Host '    http://localhost:3000  (Production)'
    Write-Host '    http://localhost:5173  (Development)'
    Write-Host ''
    Write-Host '  APIs:' -ForegroundColor Cyan
    Write-Host '    http://localhost:8000       Kong Gateway'
    Write-Host '    http://localhost:8091/docs  Indicators (33 مؤشر)'
    Write-Host '    http://localhost:8090/docs  Vegetation'
    Write-Host '    http://localhost:8092/docs  Weather + WOFOST'
    Write-Host '    http://localhost:8094/docs  Soil + FAO'
    Write-Host ''
    Write-Host '  المراقبة:' -ForegroundColor Cyan
    Write-Host '    http://localhost:9090  Prometheus'
    Write-Host '    http://localhost:3001  Grafana (admin/grafana_pass)'
    Write-Host '    http://localhost:8222  NATS Monitor'
    Write-Host ''
}

# ─── شعار ───
Write-Host @"

  ███████╗ █████╗ ██╗  ██╗ ██████╗  ██████╗ ██╗
  ██╔════╝██╔══██╗██║  ██║██╔═══██╗██╔═══██╗██║
  ███████╗███████║███████║██║   ██║██║   ██║██║
  ╚════██║██╔══██║██╔══██║██║   ██║██║   ██║██║
  ███████║██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████╗
  ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝
  v8.0 — منصة الزراعة الذكية اليمنية

"@ -ForegroundColor Green

# ─── التنفيذ (مكافئ case) ───
switch ($Mode) {
    'all' {
        Check-Deps
        Setup-Env
        Start-Backend
        Start-FrontendDev
        Run-HealthCheck
        Show-Summary
    }
    'backend' {
        Check-Deps
        Setup-Env
        Start-Backend
        Run-HealthCheck
    }
    'frontend' {
        Check-Deps
        Start-FrontendDev
    }
    'stop'   { Stop-All }
    'status' { Show-Status }
}
