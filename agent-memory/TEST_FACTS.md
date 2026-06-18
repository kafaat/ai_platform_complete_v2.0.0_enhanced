# معايير الاختبار وبوّابات CI (TEST_FACTS.md)

> كيف تتحقّق محليّاً قبل الدفع، وما الذي يحجب الدمج في CI.

## التشغيل المحليّ السريع (الافتراضيّ)
- **`pytest -m unit`** — منطق صرف بلا خدمات. هذا أساس بوّابة CI.
- `pytest.ini`: `testpaths = tests_v9`، `asyncio_mode = auto`، العلامات: `unit` / `integration` / `security` / `slow` / `mcp`.
- **التغطية لا تُفرَض في `addopts`** (كانت تُفشِل كلّ تشغيل)؛ تُطلب صراحةً في وظيفة الوحدات بـ`--cov`.

## اختبارات نواة المنصّة (مهمّ — خارج `testpaths` الافتراضيّ)
- نواة `services/sahool-platform/core/` تُختبَر من `services/sahool-platform/tests/`.
- التشغيل: `cd services/sahool-platform && PYTHONPATH=. python -m pytest tests -q`.
- هذه اختبارات منطق صرف (~١٢٨٢+) لا يجمعها `pytest -m unit` الجذريّ (لأنّ `testpaths=tests_v9`). وظيفة CI **«Platform Unit Tests»** تشغّلها.

## وظائف CI (بوّابات الدمج) — `.github/workflows/ci.yml`
1. **Repository Structural Lint** — حارس بِنية المستودع.
2. **Validate Docker Compose** — صحّة `docker-compose.v9.yml`.
3. **Lint & Format** — `ruff==0.15.8` (مثبّت! لا تفكّ التثبيت — كان يسبّب فشل تنسيق غير حتميّ) + mypy.
4. **Frontend Typecheck**.
5. **Unit Tests** — `pytest -v -m unit --cov=services` بأرضيّة تغطية.
6. **Platform Unit Tests** — `services/sahool-platform/tests` (انظر أعلاه).
7. **Integration Tests** — Postgres+PostGIS+Redis حقيقيّة، تطبّق كلّ الهجرات عبر MANIFEST. يلتقط فشل حارس RLS مثل `test_tenant_policy_uses_current_setting` (كلّ سياسة `%tenant%` يجب أن تحتوي حرفيّاً `current_setting`).
8. **Security Scan** — `pip-audit` (يحجب على المسار الحرج) + `bandit ... --severity-level high` (يحجب على HIGH). الأبطأ (~٣-٤ دقائق).

## قبل الدفع — تحقّق ذاتيّ
- شغّل ملفّاتك الجديدة + `pytest -m unit` + `ruff check`/`ruff format --check`.
- **شغّل ruff بالنسخة المثبّتة `0.15.8`** بالضبط (`pip install ruff==0.15.8`) — نسخة أخرى قد تعيد تنسيق ملفّ في CI فقط.
- نمط البوّابات الثابتة: حوّل كلّ ثابت معماريّ إلى **حارس CI ثابت** (مثل `test_router_decomposition_guard.py`، حرّاس weather-polygon-worker).
