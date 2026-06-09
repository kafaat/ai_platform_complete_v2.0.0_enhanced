# إعداد مرآة pip صينيّة على ويندوز (PowerShell)
# تشغيل: .\config\setup_pip_mirror.ps1
$pipDir = "$env:APPDATA\pip"
New-Item -ItemType Directory -Force -Path $pipDir | Out-Null
@"
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
"@ | Out-File -FilePath "$pipDir\pip.ini" -Encoding UTF8
Write-Host "✓ مرآة pip مضبوطة في $pipDir\pip.ini" -ForegroundColor Green
