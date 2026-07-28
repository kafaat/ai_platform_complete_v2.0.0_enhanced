# دليل المساهمة للوكلاء (Agent / Contributor Guidance)

إرشادات تشغيليّة دائمة لجلسات التطوير المستقبليّة. تُتّبع تلقائيّاً.

## الاختبارات — ابدأ بـ`pytest -m unit`

- **الافتراضيّ للتغذية الراجعة السريعة محليّاً:** `pytest -m unit`. هذه اختبارات منطق صرف بلا خدمات، وعليها تُبنى بوّابة CI (وظيفة *Unit Tests*: `pytest -v -m unit --cov=services` + أرضيّة تغطية `--cov-fail-under=20`).
- **العلامات (markers) في `pytest.ini`:** `unit` / `integration` / `security` / `slow` / `mcp`، و`testpaths = tests_v9`.
- **احتفظ بـ`-m integration` لِما بعد رفع الخدمات/PostGIS** (تتطلّب Postgres+PostGIS وRedis قيد التشغيل). لا تُشغّلها كافتراضيّ.
- **حارس تفكيك الراوترات:** `services/sahool-platform/tests/test_router_decomposition_guard.py` (مُعلَّم `unit`) يمنع انحدار تفكيك `main.py` إلى `api/routers/` — أبقِه أخضر عند تعديل نقاط `/api/v1/*`.

## التبعيّات — افحص الثغرات قبل أيّ إضافة أو ترقية

- **قبل** إضافة أو ترقية أيّ شيء في `requirements*.txt`، شغّل فحص ثغرات/استشارة تبعيّات (`pip-audit -r <file>`) محليّاً. الفشل المتأخّر في CI مكلِف.
- **بوّابة CI (*Security Scan*):**
  - `pip-audit` يحجب الدمج على المسار الحرج: `services/sahool-platform/api/requirements.txt` و`services/auth/requirements.txt` و`services/guardrails-engine/requirements.txt` و`requirements_real.txt`.
  - `bandit -r services/ bots/ agents/ --severity-level high` يحجب على HIGH (الباقي إرشاديّ، لا يحجب).
- **مثال واقعيّ حديث:** `python-multipart` 0.0.27 حمل ثغرة CVE حجبت CI حتى رُفِع إلى `0.0.31` في المسار الحرج. افحص أوّلاً تتجنّب التكرار.

## مسارات المنصّة — الموضع القانونيّ وميزانية النطاق

- **`services/sahool-platform/api/main.py` خالٍ من المسارات بالعقد.** `scripts/ci/p1_main_decomposition_guard.py` يرفض **أيّ** مُزخرِف مسار فيه ويحدّ عدد أسطره. كلّ مسار جديد يذهب إلى `api/routers/`.
- **مسارات البنية/الـprovenance** (`/healthz` · `/readyz` · `/metrics` · `/runtime-identity`) موضعها القانونيّ **`api/routers/platform_health.py`**، مُعلَنة كبيانات في `docs/architecture/platform_route_placement_contract.json` (`required_source` + `forbidden_sources` + `required_function` + `uniqueness`) ومفروضة بـ`scripts/ci/platform_route_placement_guard.py` — حارس مستقلّ يعمل بلا pytest داخل وظيفة `platform-route-budget`، ويفشل برسالة تسمّي الملفّ الصحيح.
- **الميزانية:** الراتشِت يحدّ **مسارات النطاق فقط** (`domain ≤ 629`). مسارات البنية تُستثنى عبر allowlist صريحة (method + مسار مُطبَّع، لا substring) بينما يبقى **الجرد الخام ظاهراً** (630). التصنيف يقول ما هو المسار؛ خريطة الموضع تقول أين ينتمي — والاستثناء من الميزانية **لا** يرخّص إعلانه في `main.py`.
- **لا ترفع السقف ولا تحذف نقطة provenance** لحلّ تعارض ميزانية؛ صنّفها بصدق أو ضعها في خدمتها.

## الدماغ المعرفيّ (Knowledge Brain)

قاعدة معرفة Markdown يصونها الوكيل ذاتيّاً في `sahool-brain/` — هُب **رابط لا مكرّر** يربط المصادر
القائمة (docs/adr · MANIFEST · compose · تقرير الفجوات · decision_record) ويضيف الناقص (كتالوج خدمات،
سجلّ فجوات حيّ، لقطة تركيز، سجلّ جلسات، بروتوكول صيانة).

- **بداية الجلسة:** اقرأ `sahool-brain/hot.md` + `sahool-brain/index.md` + الفجوات الحرجة المفتوحة في `sahool-brain/gaps/registry.md`.
- **نهاية الجلسة:** حدّث `hot.md`؛ ألحِق `log.md`؛ حدّث حالات `gaps/registry.md`؛ أضف قرارات الجلسة (SHA + سبب) إلى `decisions/ledger.md`.
- **القواعد الصارمة:** لا معلومة بلا مصدر (`path:line`/`#PR`) · لا فجوة بلا مصدر + حالة · لا قرار بلا سبب + PR/SHA · لا تحديث بلا سطر في `log.md`.

نقطة الدخول: [`sahool-brain/index.md`](sahool-brain/index.md) · المقدّمة والقواعد: [`sahool-brain/README.md`](sahool-brain/README.md).
