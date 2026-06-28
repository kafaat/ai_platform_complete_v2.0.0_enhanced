# 🔥 التركيز الحاليّ (Hot)

> **آخر تحديث:** 2026-06-28 · رأس `main`: [`63c2f03`](../) (#577 مُدمج) · انظر [`log.md`](log.md) مدخل (ن).
> 🧩 **تفكيك مكتمل:** كلّ خدمات `main.py` الكبيرة/المتوسّطة (≥٦ مسارات) مُفكَّكة الآن إلى `routers/`
> (raster/auth/odoo/video/vegetation/supervisor + soil/tts/actuator/guardrails + sahool-platform).
> ⚠ **درس تشغيليّ سابق:** `main` أُعيد ضبطه بدفع مباشر من المالك (محا #544–#549)؛ أُعيد جوهرها عبر
> #550/#551. **لا تبنِ على `main` أثناء دفع مباشر متزامن؛ وحّد الاسترجاع في فرع واحد سريع الدمج.**

## ⏳ مفتوح الآن (ينتظر سجلّ المشغّل): تشخيص auth «unhealthy»

`v21-sahool-auth-1` **unhealthy** يمنع إقلاع الحزمة (`dependency failed to start`). `/readyz` موصول
صحيحاً (`services/auth/routers/ops.py:31` + `register_routers`) ⇒ **ليست انحدار تفكيك #557**؛ السبب
runtime/config (lifespan يرفع `RuntimeError` fail-closed ⇒ يموت uvicorn ⇒ unhealthy). **الأرجح:** دور
قاعدة يتجاوز RLS (`DATABASE_URL` كـsuperuser/مالك جداول ⇒ `assert_db_role_rls_safe` يرفض الإقلاع،
`services/auth/main.py:229`). الإصلاح: دور مقيّد `sahool_app` أو `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` للتطوير.
بدائل: `JWT_SECRET`<32 (`main.py:201`)، أو فشل `_ensure_admin_user` (migrate ناقص). **الخطوة الحاسمة:**
`docker logs v21-sahool-auth-1 --tail 60` — لم أُصلِح بلا السجلّ (تفادي إصلاح أعمى).

## عمل هذه الجلسة (بوّابة الواجهة + متابعتا D/C من مراجعة النسخة `008c330`)

التفاصيل + الأسباب في [`log.md`](log.md) مدخل (ن) و[`decisions/ledger.md`](decisions/ledger.md):

- **#574 (`b180553`)** — تحديث العقل لـSVC-DECOMP-2 (#570–#573).
- **#575 (`35a4565`) بوّابة الواجهة 3003:** ٥ كتل `location ^~` **قبل** catch-all `/api/` لخدمات
  `api.ts` (vegetation/indicators/weather/agent/guardrails) بلا `auth_request`؛ أهداف مطابقة لـ
  `nginx.v9.conf`. فجوة مُثبَتة (بلاها تسقط للـ catch-all ⇒ 404). حارس `test_frontend_nginx_service_proxy_guard`.
- **مراجعة المستخدم للنسخة:** كلّ الادّعاءات **صحيحة** بالكود؛ أُغلِقت المتابعتان القابلتان للتنفيذ:
  - **#576 (`2244145`) D — عقد TileJSON (واجهة):** طلب TileJSON صار يمرّر `params` مشروطة
    (`date && date!=='latest' ? {index,date} : {index}`) فلا يُسرَّب `date=latest`. تنظيف عقد لا كسر.
  - **#577 (`63c2f03`) C — الموضوع اليتيم (NATS):** `overlay.completed` منشور بلا مشترِك ⇒ قسم
    `published_no_consumer` في عقد الأحداث + `check_nats_subjects` يحترمه (WARN⇒PASS) دون إضعاف CRITICAL/H2.
- **صدق:** D/C تنظيف+توثيق لا تغيير سلوكيّ؛ **B (journal دائم للوكيل) مؤجَّل** كـPR مستقلّ.

## أعلى الفجوات الآن

(السجلّ الكامل + المصادر في [`gaps/registry.md`](gaps/registry.md))

| ID | العنوان | الحالة |
|---|---|---|
| C1/C2 | التوصية تُولَّد بلا تخزين/تدقيق كامل لربط الشرح بـ`rec_id` | open (جزئيّ — v77 موجود) |
| MAP-QA | افتراض MapLibre/WebGL ينتظر بوّابة QA حيّة (Playwright) | open (البوّابة مُنشأة، تنتظر تشغيلاً) |
| H5 · C5 · H2 | الريّ المشروط بالملوحة · دليل NDVI · عقد ناشري الأحداث | **fixed** (#566/#567/#568؛ H5/C5 يحتاجان معايرة ميدانيّة) |
| CDSE-CLIP/SCL/MAPHUB | قصّ المضلّع (poly+rasterio) + قناع SCL + MapHub→cdse-tiles | fixed (#564؛ يحتاج تحقّقاً ميدانيّاً بتشغيل CDSE) |
| AUTH-BOOT | `sahool-auth` unhealthy يمنع إقلاع حزمة v21 (الأرجح دور قاعدة يتجاوز RLS) | **open (ينتظر سجلّ المشغّل)** |
| SUP-JOURNAL (B) | journal الوكيل in-memory (`tool_contracts.py:325`) — يلزم Postgres/outbox للإنتاج | **deferred** (PR مستقلّ) |
| C4-M1 · SAM2 · TERRAIN | موبايل push/FCM · GPU · مسار `/terrain` | **deferred / by-design** (بيئة Flutter/GPU أو P2) |

## ماذا بعد؟

- **عاجل (المشغّل):** الصق `docker logs v21-sahool-auth-1 --tail 60` لحسم سبب الـunhealthy والإصلاح
  (الأرجح دور RLS — راجع القسم أعلاه).
- **تحقّق ميدانيّ (المشغّل):** معايرة EC لسياسة الريّ (H5) + عتبات NDVI (C5) + تشغيل CDSE حقيقيّ
  (قصّ المضلّع + قناع SCL + مؤشّر الملوحة SWIR).
- **تنظيف (واجهة GitHub):** حذف الفروع العالقة `frontend-cdse-hide-date` · `fix-cdse-clip-to-field`
  (الوكيل لا يملك حذف الفروع؛ الوسيط يرفض حذف المرجع).
- **متاح عند الرغبة (لم يُطلَب):** عقود C4/SAM2/TERRAIN الخادميّة (payload/dedupe · capabilities/readiness ·
  `/terrain/tilejson`) — أجزاء Flutter/GPU/عرض 3D تبقى مؤجّلة لبيئاتها.
- إثراء EC من حالة الحقل (`soil_lab_tests` عبر `field_id`) في راوتر توصية الريّ — متابعة موثَّقة.
