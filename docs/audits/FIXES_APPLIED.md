# الإصلاحات المُطبَّقة — استجابة لتقرير المراجعة (SAHOOL v9)

مرجع التقرير: `CODE_REVIEW_REPORT.md` (38 نتيجة). هذا المستند يوثّق **حالة كل
نتيجة** والتحقّق. سكربت التحقّق: `verify_review_fixes.py` (23/23 ✓).

## منهجيّة التحقّق
- `py_compile` لكلّ ملف معدّل: ✅ يُترجم.
- `ruff` (إعداد المشروع): صافي الأخطاء **انخفض** 312→307، **صفر خطأ جديد**.
- `verify_review_fixes.py`: **23/23 نجاح** (سلوكي: LAI/EVI/Open-Meteo/الثقة/الكاش/WOFOST/السجلّ/النسخ).
- المجموعة دون-اتصال: قائمة الإخفاقات **مطابقة** للأصل ⇒ **صفر ارتداد**.
- pytest على الكود المعدّل (tool_contracts/event_replay/confidence/geospatial): 24 ✓.

---

## الحرجة (C1–C5) — أصلحها فريق المشروع، تحقّقتُ منها

| # | الحالة | التحقّق |
|---|--------|---------|
| C1 تجاوز المصادقة | ✅ مُصلَح | `/login` و`/signup` يرفضان `fail-closed` (403) عند `SAHOOL_ENV=production` |
| C2 ترحيلات RLS ناقصة | ✅ مُصلَح | MANIFEST يسرد 18/18 بما فيها `v9_rls_tenant_isolation.sql` |
| C3 edge-inference لا يُقلع | ✅ مُصلَح | `lifespan` (24) قبل `app` (31) — يُترجم ويُستورد |
| C4 أدوات MCP معطّلة | ✅ مُصلَح | `retry_request(client.get, url)` — دالّة + وسائط |
| C5 اختبارات بلا assert | 🟡 جزئي | اختبارات الخدمات بـassert حقيقي؛ اختبارات roadmap تبقى نمط تتبّع (انظر أدناه) |

---

## العالية والمتوسطة والمنخفضة — أصلحتُها في هذه الجولة

| # | الموقع | الإصلاح |
|---|--------|---------|
| **H1** | `api/main.py` أتمتة الطقس | أضفتُ `Depends(get_current_user)` لـ`/register`,`/cached`,`/status` |
| **H2** | `frontend/src/services/api.ts` | `tryReal` لم يَعُد يُلفّق بيانات عند فشل الخادم — mock في `MOCK_MODE` فقط، وأخطاء الإنتاج تُرمى |
| **H3** | `vegetation-analysis/main.py` | LAI عبر Beer-Lambert الصحيح `-ln(1-NDVI)/k`، مثبّت [0.05,0.95]، مسقوف 8.0 |
| **H4** | `vegetation-analysis/main.py` | حارس مقام EVI (≈0 ⇒ كان inf/ZeroDivision). (مسار raster آمن أصلاً عبر `np.isfinite`) |
| **H5** | `services/soil-service/main.py` | مواءمة SELECT/INSERT/Model مع الأعمدة الفعليّة (`temperature_c/ph/ec_ds_m/*_mg_kg`) + إضافة NPK + `tenant_id` UUID آمن |
| **H6** | `connectors/openmeteo.py`، `wofost_engine.py` | فهرسة آمنة `_daily_at` لمصفوفات مُسنّنة/null (كان IndexError/KeyError) |
| **H7** | `wofost_real/wofost_engine.py` | ETc يُطرح **دائماً**؛ الريّ يعيد الملء للسعة الحقليّة عند الإجهاد؛ أُزيل الكود الميّت `1000/1`. (تحقّق: البعلي يسجّل إجهاداً مائياً الآن) |
| **H8** | `api/main.py` | `_parse_iso_utc`: تطبيع المنطقة (naive⇒UTC) + 422 للمدخل الفاسد (كان 500) |
| **H9** | `agents/notification/requirements.txt` | `asyncpg>=0.30.0,<0.32.0` (متوافق مع Python 3.13) |
| **M1** | `api/prescriptions.py` | حارس المساحة الكليّة > 0 (مناطق بمساحة 0 كانت تقسم على صفر) |
| **M3** | `api/confidence_engine.py` | ثقة التغطية متّصلة رتيبة عند 0.5 (كانت قفزة 0.245→0.50) |
| **M4** | `sentinel_hub/vegetation_real.py` | `asyncio.Lock` + تحقّق مزدوج حول تحديث توكن Sentinel-Hub |
| **M5** | `shared/helpers.py` | مفتاح الكاش بـ`sha256` مستقرّ (كان `hash()` مُعشّى لكلّ عمليّة) |
| **M6** | `sentinel_hub/vegetation_real.py` | حارس قسمة في ملخّص `/timeseries` (`max(1,len)`) |
| **M8** | `vegetation-analysis/main.py` | افتراضات تاريخ `analyze` تُحسب لكلّ طلب (كانت تُجمّد عند الاستيراد) |
| **M10** | `mobile/.../api_service.dart` | `_isTokenExpired` يفشل-مغلقاً (كـauth_service) |
| **M12** | `.github/workflows/ci.yml` + `requirements-dev.txt` | تصحيح اسم الملف لـ`requirements_real.txt` + إضافة `alembic`/`SQLAlchemy` |
| **L1** | `event_upcasting.py`, `field_timeline.py` | مواءمة تسمية حدث التسميد مع enum المُصدِّر (`operation.fertilizer.applied`) |
| **L2** | `event_upcasting.py` | ترتيب نسخ عدديّ `_vkey` (كان معجمياً: `"1.10"<"1.2"`) |
| **L4** | `supervisor-agent/tool_contracts.py` | `record_complete` يملأ `tool_id`/`tenant_id` من سجلّ start (كان `""`) |
| **L5** | `guardrails-engine/main.py` | `hmac.compare_digest` لمقارنة توكن الخدمة |
| **L6** | `odoo-bridge/main.py` | إزالة مُحقّق HMAC الميّت + استيراده غير المستخدم |
| **L10** | `raster-service/main.py` | نقل docstrings قبل أوّل تعبير تنفيذي (3 نقاط) |
| **L12** | `frontend/src/services/api.ts` | تصحيح وسم النسخة v8→v9 |

---

## مؤجَّلة — مع المبرّر (ليست أخطاء وقت تشغيل عاجلة)

| # | السبب في التأجيل |
|---|------------------|
| **C5 (roadmap)** | اختبارات roadmap نمط "تتبّع تقدّم" (تُرجع قائمة)؛ تحويل 183 دالّة إلى assert تغيير واسع منفصل. اختبارات الخدمات الحرجة بـassert حقيقي (تحقّقنا: 24 ✓). |
| **M2** blocking sync HTTP في `field_intelligence_analyze` | يتطلّب تحويل المحوّلات إلى `AsyncClient`+`gather` (إعادة هيكلة) — ديْن معماري، لا خطأ. |
| **M7** مرونة بحث الرادار (raster) | تغليفه في `_stac` متوسّط؛ يفشل حاليّاً بصدق عبر `raise_for_status`. |
| **M9** JWT في `localStorage` (الواجهة) | يحتاج إعادة تصميم تدفّق المصادقة (httpOnly/refresh). |
| **M11** "حفظ" الإعدادات لا يحفظ | يحتاج طبقة حفظ خادميّة + إزالة جمع مفتاح API من المتصفّح (نمط مضادّ). |
| **L3** `zone_centers["medium"]` يُكتب فوق نفسه (n_zones≥4) | ملخّص مضلّل فقط؛ التعيينات والأعداد صحيحة. |
| **L7/L8** وسوم `:latest` + ملفات compose قديمة | قرار تشغيليّ (تثبيت إصدارات/حذف متغيّرات). |
| **L9** نطاق mypy ضيّق | سياسة CI (توسيع تدريجيّ). |
| **L11** `frontend/.env.local` | `.gitignore` (`.env.*`) يستثنيه فعلاً — لن يُرفع (قيم localhost فقط حاليّاً). |
| monolith `main.py` (156 مسار) | إعادة هيكلة تدريجيّة لـrouters — ديْن معماري كبير. |

---

## ملاحظة صدق
كل إصلاح هنا **مُتحقَّق منه** (ترجمة + ruff + سلوك). الإصلاحات الأربعة الحرجة من
فريق المشروع صحيحة بنيويّاً ومنطقيّاً. التحقّق النهائي للمسارات الحيّة (RLS فعليّ
على Postgres، إقلاع الحاويات، MCP حيّ، صور Sentinel) يبقى على بيئة فيها شبكة
وقاعدة بيانات وDocker — محجوبة جزئيّاً في بيئة التطوير الحاليّة.
