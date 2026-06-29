# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-06-29 · رأس `main`: [`96003bf`](../) (توحيد main + Phase 1–22) · [`log.md`](log.md) مدخل (س).
> 🧩 **توحيد مكتمل:** `main` صار superset كاملاً (عمل الجلسات + فرع الاعتماد Phase 1–22). كلّ الـ11 خدمة
> مُفكَّكة. الفرع المخصّص `claude/code-review-34hO3` (`c0174e6`) **مطابق لـmain**. 0 PR مفتوح · 0 تعارض.
> ⚠ **درس تشغيليّ سابق:** `main` أُعيد ضبطه بدفع مباشر من المالك (محا #544–#549)؛ أُعيد جوهرها عبر
> #550/#551. **لا تبنِ على `main` أثناء دفع مباشر متزامن؛ وحّد الاسترجاع في فرع واحد سريع الدمج.**

## ✅ السبب الجذريّ لـauth «unhealthy» — حُسِم (لم يكن RLS)

سجلّ المشغّل كشف الحقيقة: `from router_registry import register_routers` في `main.py:889` ⇒
`ModuleNotFoundError: 'router_registry'`. **الجذر:** Dockerfile auth (وvegetation) ينسخ ملفّات مفردة
(`COPY main.py`/`otp.py`) لا المجلّد ⇒ وحدات التفكيك (`router_registry.py`+`routers/`) غير منسوخة في
الصورة ⇒ uvicorn يفشل ⇒ unhealthy. **فرضيّاتي السابقة (دور RLS/JWT) كانت خاطئة** — لم يكن لديّ السجلّ.
**الإصلاح:** Dockerfile ينسخ الوحدتين + حارس CI `test_decomposed_service_dockerfile_guard` (11/11) يمنع
التكرار. التطبيق عند المشغّل: `docker compose -f docker-compose.v9.yml up -d --build sahool-auth sahool-vegetation-analysis`.

## عمل هذه الجلسة (توحيد main + cert + إصلاح auth الجذريّ)

التفاصيل + الأسباب في [`log.md`](log.md) مدخل (س) و[`decisions/ledger.md`](decisions/ledger.md):

- **التوحيد:** دمج `certification/final-readiness-evidence` (Phase 1–22 · v99–v123 · production-gates ·
  470 ملفّاً) مع عمل main (تفكيك/CDSE/H5/C5/H2/بوّابة) في superset واحد (`main` = `96003bf`). 22 تعارضاً مُحلّاً.
- **Stage B/C:** CDSE poly فوق raster الخاصّ بـcert (`apply_polygon_mask`/`fetch_field_geometry`/`fieldCdseTileUrl`)
  + إعادة تفكيك video/odoo/raster مع حفظ تصليب cert + استعادة الحُرّاس الثلاثة.
- **إصلاح auth الجذريّ** (أعلاه) + **إصلاحات CI:** compose `DATABASE_URL` مكرّر · frontend TS · PyYAML للمفتّش ·
  ruff format · تجديد بصمات الإصدار (`build_release_bundle` — فحص Phase 14).
- **توحيد الفروع:** main → `claude/code-review-34hO3` (مطابق) + إغلاق PR #579 (مُتجاوَز، كان يتعارض في cdse_tiles).
- **صدق:** الدمج fast-forward/توفيقيّ بلا فقد؛ تحقّق محليّ شامل (compileall · inspector PASS · 1931 اختبار · الحُرّاس).

## أعلى الفجوات الآن

(السجلّ الكامل + المصادر في [`gaps/registry.md`](gaps/registry.md))

| ID | العنوان | الحالة |
|---|---|---|
| C1/C2 | التوصية تُولَّد بلا تخزين/تدقيق كامل لربط الشرح بـ`rec_id` | open (جزئيّ — v77 موجود) |
| MAP-QA | افتراض MapLibre/WebGL ينتظر بوّابة QA حيّة (Playwright) | open (البوّابة مُنشأة، تنتظر تشغيلاً) |
| H5 · C5 · H2 | الريّ المشروط بالملوحة · دليل NDVI · عقد ناشري الأحداث | **fixed** (#566/#567/#568؛ H5/C5 يحتاجان معايرة ميدانيّة) |
| CDSE-CLIP/SCL/MAPHUB | قصّ المضلّع (poly+rasterio) + قناع SCL + MapHub→cdse-tiles | fixed (#564؛ يحتاج تحقّقاً ميدانيّاً بتشغيل CDSE) |
| AUTH-BOOT | `sahool-auth` unhealthy — الجذر: Dockerfile لا ينسخ `router_registry`/`routers/` | **fixed** (Dockerfile + حارس CI؛ يلزم `--build`) |
| UNIFY | توحيد main + فرع الاعتماد Phase 1–22 في superset واحد + توحيد الفرع المخصّص | **done** (`96003bf`/`c0174e6`) |
| SUP-JOURNAL (B) | journal الوكيل in-memory (`tool_contracts.py:325`) — يلزم Postgres/outbox للإنتاج | **deferred** (PR مستقلّ) |
| C4-M1 · SAM2 · TERRAIN | موبايل push/FCM · GPU · مسار `/terrain` | **deferred / by-design** (بيئة Flutter/GPU أو P2) |

## ماذا بعد؟

- **عاجل (المشغّل):** أعِد بناء صورتَي auth/vegetation لتطبيق إصلاح الجذر:
  `docker compose -f docker-compose.v9.yml up -d --build sahool-auth sahool-vegetation-analysis`.
- **CI:** راقِب تشغيل `96003bf` — كلّ الإخفاقات السابقة (release-checksum/lint/compose/TS) أُصلِحت؛ ما زال
  هناك runtime محتمل لم يُتحقَّق في بيئتي (nats-py/asyncpg محليّاً غائبان — تنجح في CI).
- **تحقّق ميدانيّ (المشغّل):** معايرة EC لسياسة الريّ (H5) + عتبات NDVI (C5) + تشغيل CDSE حقيقيّ
  (قصّ المضلّع + قناع SCL + مؤشّر الملوحة SWIR).
- **تنظيف (واجهة GitHub):** حذف الفروع العالقة `frontend-cdse-hide-date` · `fix-cdse-clip-to-field`
  (الوكيل لا يملك حذف الفروع؛ الوسيط يرفض حذف المرجع).
- **متاح عند الرغبة (لم يُطلَب):** عقود C4/SAM2/TERRAIN الخادميّة (payload/dedupe · capabilities/readiness ·
  `/terrain/tilejson`) — أجزاء Flutter/GPU/عرض 3D تبقى مؤجّلة لبيئاتها.
- إثراء EC من حالة الحقل (`soil_lab_tests` عبر `field_id`) في راوتر توصية الريّ — متابعة موثَّقة.
