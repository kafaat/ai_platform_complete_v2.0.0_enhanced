# دليل تشغيل حزمة الاختبار — لبيئتك الحيّة

كتبتُ لك حزمة اختبار كاملة بالأدوات التي أوصت بها المراجعة. شغّلها في بيئتك
(حيث pip/الخدمات تعمل) وارفع لي النتائج، وسأحلّلها وأعطيك التوصيات الدقيقة.

## ما الذي كتبتُه لك
| الملفّ | ماذا يختبر | يعمل offline؟ |
|--------|-----------|---------------|
| `services/supervisor-agent/test_circuit_breaker.py` | قاطع الدائرة (8 اختبارات) | ✅ نعم (بلا pytest) |
| `services/vegetation-analysis-service/test_vegetation_logic.py` | المؤشّرات/الصحّة/التوصيات (18 اختبار) | ✅ نعم (بلا pytest) |
| `services/soil-service/test_soil_validation.py` | تحقّق SoilReading (15 اختبار) | يحتاج pytest |
| `run_full_test_suite.sh` | السكربت الموحّد (Linux/Mac/WSL) | — |
| `run_full_test_suite.ps1` | السكربت الموحّد (ويندوز) | — |

## الأدوات المستخدمة (كما أوصت المراجعة)
- **pytest + pytest-cov**: تشغيل الاختبارات + قياس التغطية
- **ruff**: جودة الكود (الـ3259 مشكلة)
- **bandit**: الفحص الأمني
- **mypy**: فحص الأنواع

## كيف تشغّل (اختر حسب نظامك)

### ويندوز (PowerShell) — أنت على ويندوز غالباً
```powershell
cd C:\path\to\sahool_v9_production
.\run_full_test_suite.ps1 *> test_report.txt
```

### Linux / Mac / WSL
```bash
cd /path/to/sahool_v9_production
chmod +x run_full_test_suite.sh
./run_full_test_suite.sh 2>&1 | tee test_report.txt
```

### أو داخل حاوية (الأنظف — بيئة معزولة)
```bash
docker run --rm -v "${PWD}:/app" -w /app python:3.11-slim bash -c "
  pip install -q pytest pytest-cov ruff bandit python-jose fastapi pydantic httpx numpy &&
  bash run_full_test_suite.sh
" 2>&1 | tee test_report.txt
```

## تشغيل سريع لاختبار واحد (للتجربة الأوّليّة)
```powershell
# قاطع الدائرة (offline، فوري)
cd services\supervisor-agent
python test_circuit_breaker.py

# تحليل الغطاء النباتي (offline)
cd ..\vegetation-analysis-service
python test_vegetation_logic.py
```
يُفترض أن ترى `8/8 نجاح` و`18/18 نجاح`.

## ما الذي ترفعه لي بعد التشغيل
١. **`test_report.txt`** — المخرج الكامل (الأهمّ)
٢. **`coverage_report.txt`** — تقرير التغطية
٣. (اختياري) **`htmlcov/index.html`** — التغطية المرئيّة

## ماذا سأفعل بنتائجك
- أحلّل التغطية الفعليّة لكلّ خدمة → أحدّد الفجوات الدقيقة
- أقرأ أخطاء pytest الحقيقيّة → أصلح الاختبارات/الكود
- أراجع نتائج Ruff/Bandit → أعطيك أولويّات الإصلاح
- أكتب اختبارات إضافيّة للخدمات الأقلّ تغطيةً (weather/raster/edge...)

## ملاحظات صدق
- **الاختبارات الجديدة مُتحقَّق منها بنيويّاً** (py_compile + تحقّق المنطق
  مقابل الكود الفعلي). لم أشغّلها بـpytest في بيئتي (بلا pytest) — لكنّ
  فرضيّاتها صحيحة مقابل المنطق الفعلي (تحقّقتُ يدويّاً).
- **قد تكشف نتائجك أخطاءً** في اختباراتي (سلوك وقت تشغيل لم أتوقّعه) — هذا
  متوقّع وصحّي. ارفعها لي وأصلحها فوراً.
- اختبارات soil تحتاج **pydantic** (متوفّر في بيئتك). إن فشل الاستيراد، فالمشكلة
  في تثبيت الحزم لا في الاختبار.
- لم أكتب اختبارات تكامل (تحتاج خدمات حيّة + DB) — ركّزتُ على **منطق صرف
  قابل للاختبار offline** أوّلاً (أعلى قيمة، أقلّ هشاشة).
