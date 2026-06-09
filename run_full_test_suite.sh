#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# run_full_test_suite.sh — حزمة اختبار SAHOOL الكاملة (لبيئتك الحيّة)
#
# يشغّل كلّ أدوات الفحص التي أوصت بها المراجعة، ويولّد تقريراً موحّداً
# لترفعه لي مع التوصيات.
#
# الاستخدام (من جذر المشروع):
#   chmod +x run_full_test_suite.sh
#   ./run_full_test_suite.sh 2>&1 | tee test_report.txt
#
# ثمّ ارفع لي test_report.txt + coverage_report.txt
# ═══════════════════════════════════════════════════════════════════
set +e  # لا تتوقّف عند أوّل فشل — نريد كلّ النتائج

echo "═══════════════════════════════════════════════"
echo "  SAHOOL — حزمة الفحص الكاملة"
echo "  التاريخ: $(date)"
echo "═══════════════════════════════════════════════"

# ── ٠. تثبيت أدوات الفحص (بيئة معزولة موصى بها) ──
echo ""
echo "━━━ [0/6] تثبيت أدوات الفحص ━━━"
pip install -q pytest pytest-asyncio pytest-cov ruff bandit mypy \
    python-jose[cryptography] fastapi pydantic httpx asyncpg redis \
    numpy 2>/dev/null
echo "  ✓ الأدوات مثبّتة"

# ── ١. Ruff — جودة الكود ──
echo ""
echo "━━━ [1/6] Ruff (جودة الكود) ━━━"
echo "  عدد المشاكل (بلا إصلاح):"
ruff check services/ tests_v9/ 2>&1 | tail -5
echo ""
echo "  أكثر الأنواع تكراراً:"
ruff check services/ tests_v9/ --statistics 2>/dev/null | head -15

# ── ٢. Bandit — الأمن ──
echo ""
echo "━━━ [2/6] Bandit (فحص أمني) ━━━"
bandit -r services/ -ll -q 2>&1 | tail -20

# ── ٣. اختبارات الوحدة الجديدة (offline، بلا خدمات حيّة) ──
echo ""
echo "━━━ [3/6] اختبارات الوحدة الجديدة (offline) ━━━"
echo "  • قاطع الدائرة (supervisor-agent):"
(cd services/supervisor-agent && python3 test_circuit_breaker.py 2>&1 | tail -3)
echo "  • تحليل الغطاء النباتي:"
(cd services/vegetation-analysis-service && python3 test_vegetation_logic.py 2>&1 | tail -3)
  echo "  • موجّه النوايا (supervisor-agent):"
  (cd services/supervisor-agent && python3 test_router.py 2>&1 | tail -3)
  echo "  • مرونة تحت الفشل (chaos):"
  (cd services/supervisor-agent && python3 test_chaos_resilience.py 2>&1 | tail -3)
echo "  • تحقّق التربة (يحتاج pytest):"
pytest services/soil-service/test_soil_validation.py -q 2>&1 | tail -3

# ── ٤. pytest الكامل + التغطية ──
echo ""
echo "━━━ [4/6] pytest الكامل + التغطية ━━━"
pytest \
    services/ tests_v9/ \
    --cov=services \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    -m "unit or not integration" \
    --tb=short \
    -q 2>&1 | tee coverage_report.txt | tail -40

# ── ٥. التغطية حسب الخدمة (لتحديد الفجوات) ──
echo ""
echo "━━━ [5/6] التغطية حسب الخدمة (الأهمّ للتوصيات) ━━━"
echo "  راجع coverage_report.txt للتفاصيل. الخدمات < 50% تحتاج اختبارات."
grep -E "services/(soil|weather|vegetation|supervisor|raster|edge|guardrails|actuator)" coverage_report.txt 2>/dev/null | head -20

# ── ٦. mypy — فحص الأنواع (الخدمات الحرجة) ──
echo ""
echo "━━━ [6/6] mypy (الخدمات الحرجة) ━━━"
mypy services/auth/ services/sahool-platform/core/agronomic_state_engine.py \
    --ignore-missing-imports 2>&1 | tail -10

echo ""
echo "═══════════════════════════════════════════════"
echo "  انتهى الفحص. ارفع لي:"
echo "    • test_report.txt (مخرج هذا السكربت)"
echo "    • coverage_report.txt"
echo "    • htmlcov/ (تقرير التغطية المرئي — اختياري)"
echo "═══════════════════════════════════════════════"
