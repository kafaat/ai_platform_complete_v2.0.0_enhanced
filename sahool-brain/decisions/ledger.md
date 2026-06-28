# ⚖️ سجلّ القرارات (Decisions Ledger)

> ثلاثة مستويات: ADRs الرسميّة + آليّة القرار الحيّة + قرارات الجلسة. كلّ قرار يحوي **سبباً** و
> **PR/SHA**.

## 1) ADRs الرسميّة

من [`../../docs/adr/`](../../docs/adr/) (فهرس: [`README.md`](../../docs/adr/README.md)):

- **ADR-0001** تجريد مزوّد ERP — [`0001-erp-provider-abstraction.md`](../../docs/adr/0001-erp-provider-abstraction.md)
- **ADR-0002** قاطع دائرة MCP — [`0002-circuit-breaker-mcp.md`](../../docs/adr/0002-circuit-breaker-mcp.md)
- **ADR-0003** سلسلة تفسير القرار — [`0003-explainability-lineage.md`](../../docs/adr/0003-explainability-lineage.md)

## 2) آليّة القرار الحيّة (في القاعدة)

- **API:** [`../../services/sahool-platform/api/routers/decision_record.py`](../../services/sahool-platform/api/routers/decision_record.py)
  — يُدِيم رأس القرار ونتيجته (`POST …/decision/record`، `POST …/outcome/record`،
  `GET …/decision/{id}/lineage`) ضمن معاملة + RLS + outbox. الصدق: لا يستبدل المنطق النقيّ؛
  `success`/`confidence` الناقصان ⇒ NULL لا تلفيق (`decision_record.py:17-19`).
- **الجداول:** `v78_decision_record.sql` (رأس القرار) + `v79_outcome_record.sql` (النتيجة) —
  انظر [`../schema/migrations.md`](../schema/migrations.md).

## 3) قرارات هذه الجلسة (#431 → #447)

SHAs من `git log --oneline origin/main`.

| PR | SHA | القرار + السبب (rationale) |
|---|---|---|
| #431 | `c7f4b4d` | تقوية سلامة الهندسة المكانيّة (v96): سجلّ مراجعات + إبطال كاش — يمنع كاشاً قديماً بعد تعديل الهندسة. |
| #432–#434 | `48b6ef6`/`e30c555`/`efe9c31` | طبقة GIS نحو FieldView + توافق React 19 (react-leaflet 5/zustand 5) + انتقال WebGL تدريجيّ — تحديث المنظومة المكانيّة بأقلّ كسر. |
| #435 | `980daf6` | إزالة volume filestore المتداخل في Odoo — كان يكسر تثبيت base بـ`PermissionError`. |
| #436 | `f011775` | مراجعة P0/P1 + إصلاحات إقلاع docker (وسيط MQTT، RLS التسجيل، healthchecks) — جعل `up` ذاتيّ التهيئة. |
| **#437** | `6714bc0` | **auth:** سياق admin على كلّ اكتساب اتّصال (`_acquire`) — العلاج الجذريّ لفشل RLS في التسجيل/الدخول (يكمّله v97). |
| #438/#439 | `aaa28b6`/`16ef19a` | تفعيل صور Sentinel الحقيقيّة تلقائيّاً عند إنشاء الحقل (بلا محاكاة) + خادم SAM2 GPU opt-in — صدق البيانات + GPU اختياريّ. |
| #440/#442 | `de40881`/`45fbbc6` | توحيد وكيل تطوير Vite مع بوّابة nginx — يُصلح `npm run dev` + رؤية تشخيصيّة (offline/معالجة الصور). |
| #441 | `d23eb6b` | سويت Playwright لبوّابة QA لـMapLibre/WebGL (9 خطوات) + وظيفة CI — تأكيد عرض الخرائط قبل الدمج. |
| #443 | `2456d2b` | دمج/انقسام الحقول **ذرّيّاً** عبر نقطتَي backend — سدّ خطر «البيانات الثلاثيّة» (حالة غير متّسقة عند الفشل الجزئيّ). |
| #444 | `9e00d0a` | تصحيح مسار سلسلة NDVI (404) في الموبايل + تقرير مراجعة عميقة. |
| #445 | `a7909e6` | مصدر المؤشّرات الصحيح + زرّ تحديث الأقمار + إدارة المزارع — تكافؤ ويب/موبايل. |
| #446 | `edfc19c` | ربط أقسام مساحة العمل (موسم/أنشطة/طقس/خطّ زمنيّ) بالخلفيّة القائمة — لا واجهات وهميّة. |
| #447 | `0023f57` | سمة داكنة رسميّة متّسقة (`AppTheme.dark`) — توحيد تجربة الموبايل. |
| **#550** | `2359cea` | **استرجاع تحصينات raster** على `main` الحاليّ بعد محو ٦ PRs بدفع مباشر: قناع `cog_writer` (إصلاح **جذر** الشرائط من المصدر) + تعقيم `str(e)` + `cloud_pct`/SCL + سقالة `register_routers` — **فرع واحد مدمج**، حفظ تامّ لمساري CDSE. السبب: استعادة العمل دون فقد ودون إرجاع مسارات cdse الجديدة. |
| **#551** | `51d650c` | **تفكيك مسارات raster** (٤٥ `@app` → ١٠ `routers/`، محفوظ السلوك، ٤٩ مساراً، CDSE محفوظة). `register_routers` يُلحِق `APIRoute` مباشرةً (Starlette 1.3.1 `include_router` كسول لا يُسطّح). السبب: تقليص `main.py` (٣٠٠٥→١٦٢٥) دون كسر العدّ/الحارس/الـcdse. حُرّاس `tests_v9` صارت تمسح `routers/` (لا إضعاف). |
| #552/#553/#554 | `a3b29ff`/`df02c06`/`efea4c6` | واجهة CDSE (حذف `date=latest`) · nginx `/api/raster/` لبوّابة الواجهة 3003 (**بلا** `auth_request` — بوّابة تطوير، لا تكرار منطق الإنتاج) · وثيقة مقارنة `v9↔fixed` مُتحقَّقة. |
| #555/#556 | `f2d5f0b`/`852fb5b` | تحديث العقل (#550/#551) · **إعادة مرآة `mirror.gcr.io`** في *Integration Tests* — يُصلح رفرفة Docker Hub (CI-MIRROR ⇒ fixed). |
| **#557** | `f92c994` | **تفكيك `auth/main.py`** (٢٧ `@app` → ٩ `routers/`، محفوظ السلوك، حسّاس أمنيّاً، N=31 ثابت). السبب: تقليص المتجانس بنفس نمط raster دون كسر التفويض/الحُرّاس. |
| **#558** | `522a47e` | **قصّ CDSE على مضلّع الحقل** لا الـbbox (إزالة الصحراء الحمراء): تمرير `geom=GeoJSON` ⇒ Sentinel Hub يقصّ على المضلّع. السبب: bbox وحده يصبغ الصحراء بـNDVI منخفض. **علم تحقّق ميدانيّ** (يلزم CDSE حيّ). |
| **#559** | `1bef0cf` | **تطبيع تاريخ CDSE:** `date=""` الفارغ كان ينتج `date_from` فاسداً ⇒ يُعامَل كـ`latest`؛ وإسقاط `date` من رابط `cdse-tilejson` حين لا يُطلَب محدَّداً. السبب: مراجعة النسخة المرفقة (الملاحظة #2). اختبار وحدة (٨). |
| **#560–#563** | `77123b3`/`d40f1a9`/`0abe6de`/`7a36511` | **تفكيك ٤ خدمات متجانسة** (odoo-bridge 14 · video-processor 12 · vegetation 12 · supervisor 14) بنفس نمط raster/auth، محفوظ السلوك، عدد المسارات ثابت. #563 احتاج مساعِد `supervisor_route_source.py` (حارس مصدر يمسح main+routers بعد انتقال `/agent/*`). السبب: تقليص المتجانسات دون كسر الحُرّاس. |
| #564 (مفتوح) | — | **MapHub→CDSE + nginx + WebSocket:** `HubMap.tsx` يستخدم `cdse-tiles` (لا `tiles` المفقود ⇒ 404) + bbox/geom/tenant + `fill:false`؛ nginx `^~ /api/raster/` (يمنع اعتراض regex `.png`) + `X-Tenant-Id` من `$arg_tenant_id`؛ توصيف `ws_notifications(ws: WebSocket)` + `python-jose` المفقود + `websockets<14`؛ احتياط جلب الهندسة من DB. السبب: مراجعة كشفت أنّ إصلاحات CDSE السابقة استهدفت `FieldIndicatorMap` لا `HubMap`. |
| — | (تنبيه) | **دفع مباشر متزامن على `main`** من المالك محا PRs مدموجة (#544–#549). الدرس: لا بناء على `main` أثناء ذلك؛ الاسترجاع في فرع واحد سريع. وفقدُ `mirror.gcr.io` من `ci.yml` (فجوة CI-MIRROR) سبب رفرفة Docker Hub. |

> ملاحظة: PRs #422–#430 (مراحل الواجهة، دبابيس الاستطلاع v94، الوصفات v95، تفعيل edge/soil) سبقت
> نطاق هذه الجلسة المركّز (#431→#447) لكنّها في نفس السلسلة — راجع `git log` للتفاصيل.
