# SAHOOL_PRODUCTION_GAP_REPORT_v1

> تقرير فجوات الجاهزية للإنتاج — تحليل ساكن عميق (READ-ONLY) لشجرة المصدر على `main`
> (HEAD بعد #347). أُنتِج بأربعة وكلاء تدقيق متوازية + أداة `tools/sahool_inspector.py`.
>
> **حدّ الصدق (مبدأ: مؤشّر ≠ إثبات):** هذا التقرير **تحليل ساكن للكود** — لا تنفيذ حيّ.
> لا توجد هنا بيئة docker/Kong/NATS/Postgres حيّة، فالتدفّقات الحيّة لم تُنفَّذ. كلّ بند
> موسوم: **[ساكن]** = مُتحقَّق من الكود بأدلّة `file:line`؛ **[حيّ]** = يتطلّب تشغيل
> الخدمات لتأكيده. لا نزعم PASS لما لم يُشغَّل.

---

## 0. الحُكم التنفيذيّ

**SAHOOL نظامٌ مترابط في طبقته الأساسيّة، لكنّه «خدمات متجاورة» في ثلاث طبقات حرجة.**

- ✅ **قويّ ومُثبَت:** عزل المستأجِر (RLS ثلاثيّ الطبقات على كلّ جدول)، نمط Outbox الذرّيّ،
  حتميّة الإعادة (`(occurred_at, seq)`)، توجيه nginx، **إسقاط `field_state` كمصدر حقيقة
  واحد للحالة التأهيليّة** (مُستهلَك فعليّاً لا شعاراً).
- 🔴 **مكسور في التكامل:** (1) التوصية تُولَّد بلا تخزين/تدقيق/تتبّع شرح؛ (2) الإشعار لا
  يصل تطبيق الموبايل (لا عميل WebSocket ولا push)؛ (3) NDVI «يُحسَب ويُخزَّن ولا يُقرِّر»،
  والابتلاع المجدول غالباً يكتب NULL.
- 🟠 **هشّ ومتضارب:** التفويض فاشل-مفتوح (لا غطاء مصادقة عالميّ)، والحسابات الكمّيّة
  (ET0/الريّ/العتبات) مُكرَّرة بقيم متعارضة عبر وحدات لا تستورد من بعضها.

**SSOT verdict:** *Hybrid* — الحالة موحّدة، الفيزياء الزراعيّة silos.

---

## 1. مصفوفة الجاهزية للإنتاج (Production Readiness Matrix)

| المكوّن | الحالة | الخلاصة | أبرز خطر |
|---|---|---|---|
| **Backend (platform API)** | 🟠 جزئيّ | يعمل، RLS قويّ، لكن التفويض فاشل-مفتوح والتوصيات بلا أثر | ~96 نقطة بلا مصادقة |
| **PostgreSQL/PostGIS** | ✅ قويّ | RLS+FORCE على كلّ جدول مستأجِر (3 طبقات)، مفروض باختبارات | سياسة `audit_log` واسعة [LOW] |
| **API Gateway (nginx)** | ✅ سليم | لا Kong؛ كلّ upstream يطابق خدمة قابلة للبناء | — |
| **NATS / الأحداث** | 🟠 جزئيّ | Outbox+Replay سليمان بنيويّاً | بادئة `SAHOOL.` خاطئة + 7 اشتراكات يتيمة |
| **Mobile (Flutter)** | 🔴 مكسور (الحدود) | REST فقط؛ لا عميل WS ولا push | الإشعار لا يصل الجهاز |
| **Web (frontend)** | ⚪ خارج النطاق | Typecheck أخضر في CI؛ لم يُدقَّق عميقاً هنا | — |
| **Weather Service** | 🔴 معطّل المسار | لا ناشر NATS لـ`forecast.updated` ⇒ polygon-worker خامل | تراكب الطقس لا يُحسب |
| **Raster Service** | 🟠 جزئيّ | COG مشروط بـrasterio؛ `ndvi_timeseries`/`zonal_stats` بلا كاتب | NDVI لكلّ تاريخ غائب |
| **AI Services** | 🟠 جزئيّ | vegetation تحسب نطاقات صناعيّة ولا تكتب قاعدة | بكسل حقيقيّ عبر pass-through فقط |
| **AuthZ layer** | 🔴 فاشل-مفتوح | لا middleware/غطاء عالميّ؛ مصادقة لكلّ نقطة يدويّاً | IDOR على حالة الحقل |

---

## 2. الفجوات الحرجة (Critical Gaps)

| # | الفجوة | الدليل (`file:line`) | الوسم |
|---|---|---|---|
| C1 | **التوصية تُولَّد بلا تخزين ولا حدث تدقيق** — `rec_id` عابر في الذاكرة، لا جدول `recommendations` في الهجرات، لا `recommendation.*` في `EventType` | `internal_orchestrator.py:98`، `routers/recommendations.py:60`، `event_bus.py:114-182` | [ساكن] |
| C2 | **الشرح غير مرتبط ولا مُخزَّن** — `/decision/explain` حساب نقيّ بلا `rec_id`؛ يستحيل جلب شرح توصية سابقة | `routers/decision.py:55` | [ساكن] |
| C3 | **بادئة NATS خاطئة تكسر الاشتراك** — `SAHOOL.alerts.weather` (كبيرة) خارج تيّار `sahool.>` (حسّاس للحالة) | `agents/notification/agent.py:333` | [ساكن] |
| C4 | **الإشعار لا يصل الموبايل** — لا بنية push (FCM/APNs) في المستودع كلّه، وتطبيق Flutter بلا عميل WebSocket ولا تسجيل push | `mobile/sahool_app/pubspec.yaml`، grep صفر لـ`fcm/firebase/apns/device_token` | [ساكن] + [حيّ] |
| C5 | **NDVI الحقيقيّ لا يُغيّر القرار** — يُخزَّن «معلوماتيّاً لا يُغيّر صلاحيّة القرار»؛ القرار يستهلك `salinity_class`/`crop_vigor` فقط | `field_state_projection.py:206-215, 232-242` | [ساكن] |
| C6 | **تعارض عتبة الإجهاد الحراريّ** — `35/40°م` (محرّك التنبيهات) مقابل `38°م` (تراكب الطقس) بلا رابط ⇒ تنبيهات متناقضة لنفس الحقل عند 37°م | `api/alert_rules.py:39-40` مقابل `core/weather_overlay.py:26` | [ساكن] |

---

## 3. المخاطر العالية (High Risks)

- **H1 — تفويض فاشل-مفتوح:** لا middleware مصادقة عالميّ ولا `APIRouter(dependencies=[...])`؛ ~96 نقطة بلا تبعيّة مصادقة. الأخطر **IDOR على حالة الحقل**: `GET /api/v1/field/operational-state` يأخذ `field_id` بلا مصادقة. `routers/field_single.py:22`، `api/main.py` (لا غطاء). [ساكن] *(أكّدته أداة الفاحص: 1 نقطة تمسّ قاعدة + 97 عامّة).*
- **H2 — 7 اشتراكات NATS يتيمة:** `pest.alert`/`irrigation.recommendation`/`fertilizer.recommendation`/`inventory.low_stock`/`task.assigned`/`economic.analysis`/`weather.forecast.updated` مُشترَك بها بلا ناشر ⇒ تغذية الإشعارات الحيّة موصولة من جهة المستهلك فقط. `agents/notification/agent.py:334-339`، `weather-polygon-worker/src/main.py:115`. [ساكن]
- **H3 — فجوات سجلّ التدقيق:** إدراج التنبيهات بالجملة بلا `ALERT_CREATED` (`api/main.py:1871`)؛ تنفيذ موزِّع القرار بلا حدث domain (`routers/decision_dispatch.py:298`)؛ توصية→أمر عمل بلا حدث ولا `WORK_ORDER_*` في الكتالوج (`routers/agro_intelligence.py:253`). [ساكن]
- **H4 — ET0 Hargreaves مُكرَّر ×4 بقيم Ra متعارضة:** `Ra=15.0` (`season_simulation.py:423`) مقابل `14.0` (`weather_analytics.py:125`) مقابل المحسوب (`water_balance.py:120`) ⇒ نفس الحقل يعطي ET0 مختلفاً. [ساكن]
- **H5 — احتياج الريّ بصيغتين:** `fao56.compute_irrigation` (مع Ks ملوحة + غسيل) مقابل `water_balance.water_balance` (بلا ملوحة) ⇒ قيمتان لنفس السؤال في حقل مالح. `core/engines/fao56.py:249` مقابل `api/water_balance.py:183`. [ساكن]
- **H6 — عتبات الملوحة/pH مُكرَّرة ×3 (نسخ لا استيراد):** `agronomic_state_engine.py:29-30` مقابل `decision_engine.py:187-191` مقابل `decision_regression.py:99-111`. [ساكن]
- **H7 — نوى نقيّة ميّتة (محسوبة/مُختبَرة بلا توصيل):** `transfer_learning`، `multi_season_analytics`، `field_trial_design`، `feedback_closure`، `terroir_index`، `practice_promotion`، `decision_regression`. [ساكن]

---

## 4. التدفّقات المكسورة (Broken Flows)

| التدفّق | الحالة | السبب |
|---|---|---|
| User → nginx → Service → DB | ✅ INTACT | توجيه nginx سليم؛ `tenant_connection` يضبط سياق RLS |
| Recommendation → Explanation → Audit | 🔴 BROKEN | لا تخزين، لا حدث، لا ربط شرح (C1/C2) |
| Notification → Mobile | 🔴 BROKEN (الحدود) | WS داخل المنصّة يعمل؛ لا عميل WS/ push في Flutter (C4) |
| Satellite → NDVI → Field State → Recommendation | 🟠 PARTIAL | موصول هيكليّاً لكن NDVI «لا يُقرِّر» (C5)، والابتلاع المجدول يمرّر نطاقاً مفرداً كـ`raster_url` ⇒ `valid_pixels=0` ⇒ `last_ndvi_mean=NULL`. `imagery_automation.py:262-287` |

---

## 5. التكاملات المفقودة (Missing Integrations)

- **M1** — بنية push للموبايل (FCM/APNs) + عميل WebSocket في Flutter. [ساكن]
- **M2** — ناشر NATS لـ`sahool.weather.forecast.updated` (لا أحد ينشره ⇒ polygon-worker لا يُشغَّل أبداً). [ساكن/حيّ]
- **M3** — `actuator-service` يشير لوسيط MQTT `sahool-fastbee:1883` غير مُعرَّف في أيّ مكان. `docker-compose.v9.yml:774`. [ساكن]
- **M4** — كاتب لجدول `zonal_stats` (سلسلة NDVI زمنيّة) — مُعرَّف بلا أيّ `INSERT`. `v14_imagery_storage.sql`. [ساكن]
- **M5** — ربط ناشري التوصيات (آفات/ريّ/تسميد) بمواضيع NATS التي يشترك بها وكيل الإشعارات (H2). [ساكن]

---

## 6. حاجزات الإنتاج (Production Blockers)

1. **التفويض فاشل-مفتوح (H1)** — أيّ نقطة جديدة تُنسى تبعيّتها = مكشوفة. حاجز أمنيّ.
2. **التوصية بلا أثر/تدقيق (C1/C2)** — يكسر التتبّع/الحوكمة (Audit Trail Completeness).
3. **بادئة NATS الخاطئة (C3)** — مستهلك دائم معطّل بصمت.
4. **تعارض العتبات (C6/H4/H5/H6)** — قرارات/تنبيهات متناقضة = فقدان ثقة المستخدم.

---

## 7. خطة الإصلاح المرتّبة (Prioritized Fix Plan)

> لا إضافة مزايا — إصلاح مخاطر فقط. كلّ بند يشير لفجوته.

### P0 — حاجزات (هذا الأسبوع)
1. **غطاء مصادقة على مستوى التطبيق** — `dependencies=[Depends(get_current_user)]` على المستوى الأعلى + **allowlist صريح** للنقاط العامّة (أمثال/أقاليم/login). يحوّل النمط من فاشل-مفتوح إلى فاشل-مغلق. *(H1)* — + حارس CI ثابت يمنع نقطة `/api/v1` جديدة بلا مصادقة (نمط حارس التفكيك).
2. **إصلاح بادئة `SAHOOL.` → `sahool.`** سطر واحد + حارس بادئة في الفاحص (موجود). *(C3)*
3. **تخزين + تدقيق التوصية** — جدول `recommendations` (RLS+FORCE، هجرة v77) + إصدار `RECOMMENDATION_CREATED` عبر الـoutbox + ربط الشرح بـ`rec_id`. *(C1/C2)*
4. **استخراج `core/thresholds.py`** — مصدر واحد لعتبات الحرارة/الصقيع/الملوحة/pH، يستورده محرّك التنبيهات وتراكب الطقس والقرار. يحلّ تعارض 35/38. *(C6/H6)* — + حارس «لا عتبة مُكرَّرة».

### P1 — مخاطر عالية
5. **ربط/تقليم الاشتراكات اليتيمة** — انشر ناشري الإشعارات الفعليّين أو احذف الاشتراكات الميّتة. *(H2/M5)*
6. **توحيد ET0 والريّ** — دالّة Hargreaves واحدة (`water_balance.et0_hargreaves`) + دالّة ريّ واحدة (`fao56.compute_irrigation` مع الملوحة) تستدعيها طبقة API. *(H4/H5)*
7. **سجلّ التدقيق الكامل** — `ALERT_CREATED` على الإدراج بالجملة + حدث domain لموزِّع القرار + `WORK_ORDER_*` في الكتالوج. *(H3)*
8. **إصلاح ابتلاع NDVI المجدول** — استدعاء مسار `process-from-stac` متعدّد النطاقات بدل تمرير نطاق مفرد. *(C5/Flow4)*
9. **الموبايل** — عميل WebSocket في Flutter + بنية push (FCM) + جدول رموز الأجهزة. *(C4/M1)* — أكبر بند (يحتاج بيئة Flutter).

### P2 — متوسّط
10. توصيل أو تقاعُد النوى الميّتة (H7) — قرار لكلّ وحدة.
11. كاتب `zonal_stats` / تفعيل `ndvi_timeseries` لكلّ تاريخ (M4).
12. توثيق سياسة `audit_log` ذات السياق الفارغ؛ إضافة `ON DELETE` صريح على FKs الناقصة؛ حارس يؤكّد دور `sahool_jobs` للعمّال.

---

## 8. الأداة المصاحبة — Sahool Inspector

`tools/sahool_inspector.py` (قابلة للتشغيل، تُصدِر PASS/WARN/FAIL + رمز خروج):
- فحوصات ساكنة تعمل الآن: RLS coverage، router wiring، NATS subjects، endpoint authz، migration manifest.
- فحوصات حيّة محجوزة لبيئتك (تُطبَع SKIP بصدق): تنفيذ التدفّقات، NATS وقت التشغيل، RLS على Postgres حيّ، Replay، رحلة الإشعار للموبايل.
- النتيجة الحاليّة على `main`: **FAIL** (بسبب IDOR حالة الحقل) — مع PASS لـRLS/الراوترات/MANIFEST (يطابق حُرّاس CI الخضراء، بلا إنذار كاذب).

```
python tools/sahool_inspector.py          # تقرير + رمز خروج
python tools/sahool_inspector.py --json    # JSON للأتمتة/CI
```

---

## 9. منهجيّة وحدود

- المصدر: شجرة `main` فقط (استُبعدت نسخ `.claude/worktrees/*`). كلّ بند بدليل `file:line`.
- **لم يُعدَّل أيّ كود إنتاجيّ** — تقرير + أداة فقط (التزاماً بـ«لا مزايا جديدة هذا الأسبوع»).
- البنود [حيّ] تنتظر تشغيل الخدمات في بيئتك لتأكيدها — لا تُحتسَب إثباتاً هنا.
