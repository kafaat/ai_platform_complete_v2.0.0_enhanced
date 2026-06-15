# تدقيق معماريّ — 2026-06-14 (تحقّق مباشر من الكود)

استجابةً لمراجعة معماريّة خارجيّة رصدت ثماني فجوات. كلّ بند أدناه **مُتحقَّق مباشرةً
من المصدر/الترحيلات** (لا من الوثائق)، مع تصحيح ادّعاءات بالغ فيها التدقيق الآليّ.

## خلاصة تنفيذيّة

التقييم الخارجيّ **دقيق في وصف ما هو موجود**، لكنّ تأطيره لبعضه كـ«فجوات مخفيّة /
عدم اتّساق» غير دقيق: أغلب الملاحظات **قرارات تصميم متعمَّدة وموثَّقة ذاتيّاً** —
نقيض نمط «يبدو X لكنّه سرّاً ليس X». وعزل المستأجِرين **مكتمل** لا ناقص.

| البند | ادّعاء المراجعة | الواقع المُتحقَّق |
|---|---|---|
| عزل المستأجِرين | «ثغرات حرجة: field_lifecycle/sharing_keys بلا سياسة» | **خاطئ** — 52/52 جدول tenant_id عليه RLS+FORCE+سياسة |
| خدمات stub | «تبدو مستقلّة لكنّها stub» | صحيح لكن **مُعلَن بصدق** (الكود يقول «stub» ويُرجع 501) |
| Raster/NDVI synthetic | «vegetation تعتمد synthetic» | صحيح، لكن **مُعلَّم estimate**؛ القرارات الزراعيّة تستخدم NDVI حقيقيّاً |
| فشل صامت (~18) | «يخفي فشل مزامنة/تنبيه» | 23 معالِجاً، أغلبها مشروع؛ 5 عريضة أُصلِحت (PR #149) |
| CDES جزئيّ | «API→DB لا CDES» | صحيح جزئيّاً؛ لكن «لا مستهلكين» **خاطئ** (وكيل الإشعارات يستهلك) |

---

## 1) عزل المستأجِرين (Multi-Tenant) — **مكتمل**، ومحروس آليّاً الآن

تحقّق مباشر من 55+ ترحيلاً:

- **52 جدولاً يحوي `tenant_id`، وكلّها مغطّاة** بـ`ENABLE RLS` + سياسة عزل +
  `FORCE` (الأخير عبر `v9_rls_force_all.sql` الذي يُطبَّق بعد إنشاء الجداول).
- ادّعاءا التدقيق الآليّ **خاطئان**:
  - `field_lifecycle`: له سياسة `field_lifecycle_tenant_isolation` (`v10:104`).
  - `sharing_keys`: له سياسة `sharing_keys_owner` (`v12:109`).
  - الجداول الثلاثة الموهومة (`approval_workflows/edge_results/guardrails_log`)
    تُغطّى بحلقة `v9_new_tables.sql:109` (ENABLE + policy)، ثمّ FORCE.
- تحقّق ثابت إضافيّ: لا ترحيل **بعد** `v9_rls_force_all` يُفعّل RLS دون FORCE،
  ولا ترحيل يُفعّل RLS دون سياسة.

**الفجوة الحقيقيّة الوحيدة:** الحارس البنيويّ كان سكربت shell يتيماً
(`tests_v9/test_rls_enforcement.sh` غير مربوط بـCI/Makefile).
**الإصلاح (هذا PR):** `tests_v9/test_rls_isolation_negative.py` (integration) يفرض
على قاعدة مُرحَّلة فعليّة في CI: (A) صفر RLS بلا FORCE، (B) كلّ RLS له سياسة،
(C) كلّ جدول tenant_id عليه RLS، (D) السياسات تستند إلى `current_setting`.

---

## 2) الخدمات الـstub — تجميع متعمَّد ومُعلَن (لا خداع)

| الخدمة | التصنيف | الحقيقة |
|---|---|---|
| `weather-service` | **stub رفيع** | يقول حرفيّاً «stub رفيع صادق»، يُرجع 501؛ المنطق في `sahool-platform/api` (`main.py:5`) |
| `indicators-service` | **stub رفيع** | stub صحّيّ؛ المنطق في `sahool-platform/api` (`main.py:4`) |
| `agriai-engine` | حقيقيّ + خطّاف ML مُعلَّق | `main.py:75` «Stub — implement with ML model» |
| `auth` | **حقيقيّ** | login/MFA/lockout حقيقيّة؛ «stub» تخصّ تسليم OTP فقط |

«Distributed monolith» قرار تجميع متعمَّد (healthcheck أخضر بصدق)، لا تسرّب عرضيّ.

**قرارك مطلوب:** هل (أ) يبقى التجميع (موثَّق هنا)، أم (ب) تُفصَل weather/indicators
لخدمات مستقلّة حقيقيّة (جهد كبير)؟ التوصية: (أ) — لا قيمة تشغيليّة كافية للفصل الآن.

## 8) تضخّم Compose (Config Drift) — **مؤكَّد، وعولِج جزئيّاً (توثيق)**

`docker-compose.v9.yml` و`docker-compose.fixed.yml` كان لهما **ترويسة متطابقة
(كلاهما يقول «docker-compose.fixed.yml») لكن يختلفان بـ589 سطراً** — خطر انجراف
حقيقيّ زاده أنّ ترويسة v9.yml كانت تُسمّي نفسها خطأً «fixed.yml».

**الخريطة المُتحقَّقة (مراجع فعليّة عبر المستودع):**

| الملفّ | الدور | يُستخدَم في |
|---|---|---|
| **`docker-compose.v9.yml`** | **★ الإنتاج القانونيّ** | المرجع الأوسع: Makefile (`COMPOSE`) + سكربتات النشر + وثائق متعدّدة |
| `docker-compose.fixed.yml` | متغيّر/أصل تاريخيّ (ليس القانونيّ) | مُشار إليه في وثائق تشغيليّة (OPERATIONAL_CONTRACTS/DEPLOYMENT_HARDENING) + grafana + nginx/.env ⇒ **مُستخدَم، لا يُحذَف بلا تأكيد** |
| `docker-compose.unified.yml` | تركيب موحّد بحدود موارد | UNIFIED_SETUP.md |
| `docker-compose.light.yml` | تركيب خفيف بموارد مخفّضة | LIGHTWEIGHT_INTEGRATION.md |
| `docker-compose.erpnext.yml` | ERPNext كبديل ERP | ERPNEXT_SETUP_GUIDE.md |
| `docker-compose.test.yml` | بنية الاختبار | DEPLOYMENT_HARDENING.md |

**عولِج (هذا PR):** صُحّحت ترويسة `v9.yml` (تُسمّي نفسها صحيحاً + ★ canonical)،
ووُسِم `fixed.yml`/`unified`/`light` بأدوارها صراحةً (تعليقات فقط، YAML سليم).
**يبقى قرارك:** هل يُحذَف `fixed.yml` (يحتاج إزالة مراجعه أوّلاً عبر المستودع) أم
يُبقى متغيّراً موثَّقاً؟ لم أحذفه (مُستخدَم في وثائق + grafana + nginx/.env).

---

## 3) خطّ Raster→NDVI — القرارات الزراعيّة **حقيقيّة**، العرض فقط تقديريّ

- `raster-service`: **حقيقيّ بكسليّاً** (Sentinel-2 COGs عبر rasterio/Element84) —
  indicator-grid/timeseries/tiles/change/prescription.
- `field_state` (مصدر القرار الزراعيّ) يقرأ **NDVI حقيقيّاً** من DB
  (`imagery_automation_fields.last_ndvi_mean`، يملؤها raster-service) —
  `field_state_projection.py:101`. فالتحكيم الزراعيّ لا يستخدم synthetic.
- `vegetation-analysis-service`: تقدير field-mean من نطاقات **synthetic مُعلَّمة**
  (`real_data:false` + `estimate_note`) — للعرض (بطاقة الصحّة/KPIs) فقط.

**الخطّة (منخفضة الخطر، لا تمسّ صيَغ المؤشّرات):** يُفضّل `/v1/analyze` بيانات
raster الحقيقيّة عند توفّرها (proxy لـ`indicator-grid` → `stats.mean`)، مع وسم
صريح وارتداد للتقدير المُعلَّم. المقطع: `vegetation-analysis-service/main.py:562`
(`_realistic_bands→_compute_indices`). **ملاحظة قيد:** يغيّر الأرقام المعروضة،
فيُنفَّذ بوسم واضح وارتداد، دون تغيير الصيغ.

---

## 5) CDES — بنية أحداث حقيقيّة، طبقة أوامر خاملة

- **حقيقيّ ويعمل:** EventBus + outbox (`emit_event` ذرّيّ) + OutboxWorker→NATS +
  23 نوع حدث، 6 منها تُصدَر فعلاً. **ووكيل الإشعارات يستهلك `sahool.events.>`**
  (`agents/notification/agent.py`) — فادّعاء «لا مستهلكين» **خاطئ**.
- **فجوات حقيقيّة (P1):**
  - لا أنواع أحداث للتنبيهات (`ALERT_CREATED/ACKNOWLEDGED`) — التنبيهات غير تفاعليّة.
  - ~11 نقطة كتابة لا تُصدِر أحداثاً (farm/inventory/equipment/schedule/task…).
  - 6 أنواع أحداث مُعرَّفة بلا إصدار (TRUEUP_APPLIED، AI_SUGGESTION…).
  - طبقة الأوامر (`command_store`/`command_dispatcher`) موجودة لكن **غير مُستدعاة** —
    خارطة طريق (Phase 3) لا عيب.
- **التوصية:** إصدار `ALERT_CREATED` (الأعلى قيمة) + حذف/تنفيذ الأنواع اليتيمة.
  ليست إعادة هيكلة CDES شاملة (قرار استراتيجيّ).

---

## 6) الفشل الصامت — 23 معالِجاً، الأغلب مشروع

تدقيق AST: 23 معالِجاً جسمه `pass`. ~11 يلتقط استثناءً **محدّداً** (نمط سليم)،
وعدّة best-effort cache مُوثَّقة، و2 «بوّابات عقد» تُسجّل الحالة (ليست صامتة).
الـ5 العريضة (`except Exception: pass` بلا تسجيل) **أُصلِحت في PR #149**.
لا واحد منها يُخفي فقدان بيانات مزارع حسّاس.

---

## جدول الأولويّات

| # | البند | الحالة |
|---|---|---|
| 1 | حارس عزل RLS في CI | ✅ هذا PR |
| 2 | تصحيح ادّعاءات العزل الخاطئة | ✅ موثَّق + محروس |
| 3 | تسجيل المعالِجات الصامتة العريضة | ✅ PR #149 |
| 4 | توثيق الخدمات الـstub + config drift | ✅ هذا المستند |
| 5 | `ALERT_CREATED` event | ⏳ موصى (P1، صغير) |
| 6 | veg `/v1/analyze` يفضّل raster الحقيقيّ | ⏳ خطّة (يغيّر أرقام العرض — يحتاج موافقتك) |
| 7 | فصل خدمات stub / CDES شامل / طبقة أوامر | ⛔ قرار استراتيجيّ (قرارك) |

> المنهج: لا إعادة هيكلة عمياء لـ18 خدمة. ما هو **عيب** يُصلَح ويُحرَس؛ ما هو
> **قرار تصميم** يُوثَّق وتُعطى توصية؛ ما يحتاج قراراً استراتيجيّاً يُعرَض عليك.
