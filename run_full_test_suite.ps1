# ═══════════════════════════════════════════════════════════════════
# run_full_test_suite.ps1 — حزمة اختبار SAHOOL (ويندوز PowerShell)
# الاستخدام (من جذر المشروع):
#   .\run_full_test_suite.ps1 *> test_report.txt
# ثمّ ارفع لي test_report.txt + coverage_report.txt
# ═══════════════════════════════════════════════════════════════════
Write-Host "═══ SAHOOL — حزمة الفحص الكاملة ═══"
Write-Host "التاريخ: $(Get-Date)"

Write-Host "`n━━━ [0/6] تثبيت أدوات الفحص ━━━"
pip install -q pytest pytest-asyncio pytest-cov ruff bandit mypy `
    python-jose[cryptography] fastapi pydantic httpx asyncpg redis numpy

Write-Host "`n━━━ [1/6] Ruff (جودة الكود) ━━━"
ruff check services/ tests_v9/ --statistics

Write-Host "`n━━━ [2/6] Bandit (فحص أمني) ━━━"
bandit -r services/ -ll -q

Write-Host "`n━━━ [3/6] اختبارات الوحدة الجديدة (offline) ━━━"
Push-Location services/supervisor-agent; python test_circuit_breaker.py; Pop-Location
Push-Location services/vegetation-analysis-service; python test_vegetation_logic.py; Pop-Location
Push-Location services/supervisor-agent; python test_router.py; Pop-Location
Push-Location services/supervisor-agent; python test_chaos_resilience.py; Pop-Location
pytest services/soil-service/test_soil_validation.py -q

Write-Host "`n━━━ [4/6] pytest الكامل + التغطية ━━━"
pytest services/ tests_v9/ --cov=services --cov-report=term-missing `
    --cov-report=html:htmlcov -m "unit or not integration" --tb=short -q `
    | Tee-Object -FilePath coverage_report.txt

Write-Host "`n━━━ [5/6] التغطية حسب الخدمة ━━━"
Select-String -Path coverage_report.txt -Pattern "services/(soil|weather|vegetation|supervisor|raster|edge|guardrails|actuator)"

Write-Host "`n━━━ [6/6] mypy (الخدمات الحرجة) ━━━"
mypy services/auth/ --ignore-missing-imports

Write-Host "`n═══ انتهى. ارفع لي: test_report.txt + coverage_report.txt ═══"
