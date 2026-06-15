# دليل المساهمة للوكلاء (Agent / Contributor Guidance)

إرشادات تشغيليّة دائمة لجلسات التطوير المستقبليّة. تُتّبع تلقائيّاً.

## الاختبارات — ابدأ بـ`pytest -m unit`

- **الافتراضيّ للتغذية الراجعة السريعة محليّاً:** `pytest -m unit`. هذه اختبارات منطق صرف بلا خدمات، وعليها تُبنى بوّابة CI (وظيفة *Unit Tests*: `pytest -v -m unit --cov=services` + أرضيّة تغطية `--cov-fail-under=3`).
- **العلامات (markers) في `pytest.ini`:** `unit` / `integration` / `security` / `slow` / `mcp`، و`testpaths = tests_v9`.
- **احتفظ بـ`-m integration` لِما بعد رفع الخدمات/PostGIS** (تتطلّب Postgres+PostGIS وRedis قيد التشغيل). لا تُشغّلها كافتراضيّ.
- **حارس تفكيك الراوترات:** `services/sahool-platform/tests/test_router_decomposition_guard.py` (مُعلَّم `unit`) يمنع انحدار تفكيك `main.py` إلى `api/routers/` — أبقِه أخضر عند تعديل نقاط `/api/v1/*`.

## التبعيّات — افحص الثغرات قبل أيّ إضافة أو ترقية

- **قبل** إضافة أو ترقية أيّ شيء في `requirements*.txt`، شغّل فحص ثغرات/استشارة تبعيّات (`pip-audit -r <file>`) محليّاً. الفشل المتأخّر في CI مكلِف.
- **بوّابة CI (*Security Scan*):**
  - `pip-audit` يحجب الدمج على المسار الحرج: `services/sahool-platform/api/requirements.txt` و`services/auth/requirements.txt` و`services/guardrails-engine/requirements.txt` و`requirements_real.txt`.
  - `bandit -r services/ bots/ agents/ --severity-level high` يحجب على HIGH (الباقي إرشاديّ، لا يحجب).
- **مثال واقعيّ حديث:** `python-multipart` 0.0.27 حمل ثغرة CVE حجبت CI حتى رُفِع إلى `0.0.31` في المسار الحرج. افحص أوّلاً تتجنّب التكرار.
