# التحليل والتتبع التشغيلي لحزمة Sahool 73666ee

التاريخ: 2026-07-12  
النطاق: `sahool_73666ee_multitenancy_verified.zip`  
التركيز: Decision-Service، Model Registry Adapter، Runtime Work Feed، Worker→Tenant Authorization، CI والتشغيل عبر Compose.

## الحكم التنفيذي

التدفق التشغيلي الأساسي موجود ومترابط من حيث الكود:

`Model Registry Adapter → اكتشاف المستأجرين → Runtime Work Feed → Durable Lease → تنفيذ Side Effect → Receipt → Active State`

لكن الحزمة لا تحقق عزلاً إنتاجياً كاملاً للعمال متعدد المستأجرين. التنفيذ الحالي يفرض العزل فقط بعد ظهور أول تسجيل للعامل. العامل غير المسجل يمر عبر مسار توافق قديم يعيد `True` لأي `tenant_id`، كما أن إعدادات البيئة المحلية تتقدم على الاكتشاف من الخادم. لذلك يوجد فرق بين:

- **تقسيم تشغيلي وظيفي:** موجود.
- **تفويض أمني fail-closed:** غير مكتمل.
- **إثبات نشر كامل في Compose/Kubernetes:** غير ظاهر في الحزمة.

## التتبع التشغيلي الفعلي

### 1. بدء عامل دورة حياة النماذج

نقطة الدخول هي:

`services/model-registry-adapter/service.py::main`

التسلسل:

1. `validate_runtime()` يتحقق من إعدادات التشغيل.
2. ينشأ `LifecycleRuntime()`.
3. يبدأ خادم صحة منفصل على `PORT` الافتراضي 8099.
4. تبقى `/readyz` بحالة 503 حتى نجاح أول دورة اتصال فعلية.
5. يستدعي `run_once(runtime)` باستمرار مع backoff من 1 إلى 60 ثانية عند الفشل.

هذه نقطة جيدة: الجاهزية لا تعلن قبل إثبات الوصول إلى Decision-Service.

### 2. تحديد المستأجرين الذين يخدمهم العامل

الدالة:

`services/model-registry-adapter/service.py::resolve_tenants`

ترتيب الأولوية الفعلي:

1. `RUNTIME_TENANT_IDS`
2. `RUNTIME_TENANT_ID`
3. `GET /v1/learning/runtime-workers/{worker_id}/tenants`

النتيجة التشغيلية:

- عند وجود متغيرات البيئة لا يستعلم العامل من الخادم أصلاً.
- عند غيابها، يجلب التقسيم المسجل من Decision-Service.
- إذا كانت النتيجة فارغة يفشل العامل ولا يدخل حالة idle صامتة.

المشكلة: متغيرات البيئة تعد مصدر سلطة أعلى من سجل الخادم، لا مجرد قيد إضافي. لذلك يمكن نشر عامل بقائمة محلية لا تتطابق مع سجل التفويض.

### 3. اكتشاف المستأجرين من Decision-Service

المسار:

`GET /v1/learning/runtime-workers/{worker_id}/tenants`

ينفذ:

`persistence.py::list_worker_tenants`

ويعيد كل السجلات المفعلة للعامل. لا يطبق هذا المسار تحققاً يربط هوية المتصل بقيمة `worker_id` المطلوبة. الحماية الوحيدة العامة هي service bearer token إذا كان `DECISION_SERVICE_AUTH_TOKEN` مضبوطاً.

### 4. طلب العمل لكل مستأجر

العامل يستدعي:

`GET /v1/learning/runtime-work?worker_id=...&limit=20`

مع:

`X-Tenant-Id: <tenant>`

Decision-Service ينفذ بالترتيب:

1. استخراج المستأجر عبر `_tenant(x_tenant_id)`.
2. رفض `worker_id` الفارغ.
3. التحقق أن Decision-Service هو System of Record.
4. استدعاء `worker_tenant_authorized(worker_id, tenant_id)`.
5. عند النجاح استدعاء `list_runtime_work(...)`.

### 5. قاعدة التفويض الحالية

الدالة:

`persistence.py::worker_tenant_authorized`

السلوك الحقيقي:

- إذا لم يوجد أي سجل للعامل: `True`.
- إذا وجد أي سجل: يسمح فقط للمستأجرات المفعلة.

هذا يعني أن عاملًا باسم جديد يستطيع المرور لأي مستأجر في وضع التوافق القديم، بشرط امتلاكه وصولاً إلى الخدمة أو bearer token المشترك.

### 6. Claims والـleases

`list_runtime_work` يستخدم جدول:

`decision_model_runtime_work_claims`

ويدعم:

- `worker_id`
- `work_type`
- `work_key`
- `lease_expires_at`
- `attempt`
- إعادة الاستحواذ بعد انتهاء الـlease

هذا يمنع معالجة نفس side effect بالتوازي بين نسخ متعددة، بشرط أن جميع النسخ تستخدم نفس Decision-Service وقاعدة البيانات.

### 7. تنفيذ أنواع العمل

`_run_once_for_tenant` يدعم صراحة:

- `post_activation_verification`
- `rollout_apply`
- `monitoring_window`
- `retraining_dispatch`
- `activation_command`
- `rollback_command`
- `active_state_reconcile`

أي نوع غير معروف يؤدي إلى `RuntimeContractError`، وهو fail-closed صحيح.

### 8. التنفيذ الخارجي

التنفيذ موزع على adapters HTTP/CAS:

- Traffic controller يستخدم compare-and-swap.
- Inference verifier يفحص digest/schema/feature set/smoke inference.
- Registry activation والrollback تنفذان خارج Decision-Service ثم تسجلان receipt.
- الأخطاء تقلب readiness إلى 503 وتدخل backoff.

### 9. التسجيل والإلغاء

المسار:

`POST /v1/learning/runtime-workers/{worker_id}/tenants`

يقبل:

- `tenant_id`
- `enabled`
- `idempotency_key`
- `X-Registered-By`

ويكتب في:

`decision_runtime_worker_tenants`

السجل الحالي mutable باستخدام `ON CONFLICT (worker_id, tenant_id) DO UPDATE`.

## النتائج الجنائية التشغيلية

### حرجة: fail-open للعامل غير المسجل

الوصف والتعليقات والاختبارات تعتبر هذا توافقاً خلفياً مقصوداً. لكنه يترك ثغرة مباشرة: اسم عامل جديد لا يملك أي صفوف يصبح مخولاً لأي مستأجر يرسله في الرأس.

الأثر:

- تجاوز partition registry.
- إمكانية سحب leases لمستأجر آخر.
- تعطيل العامل الشرعي حتى انتهاء الـlease.
- تنفيذ side effects تحت partition غير مخصص.

### حرجة: replay قد يعكس الإلغاء

جدول الحالة يحتفظ بمفتاح idempotency واحد فقط لكل زوج `(worker_id, tenant_id)` بسبب upsert. إعادة أمر قديم بمفتاح قديم بعد تحديثات لاحقة قد لا تجد صفاً مطابقاً لذلك المفتاح، ثم تنفذ upsert على الزوج وتعيد الحالة القديمة.

الحل يتطلب command ledger append-only منفصلاً عن current-state projection.

### عالية: هوية العامل غير مرتبطة تشفيرياً بـworker_id

كل من discovery وruntime-work يقبل `worker_id` من path/query. bearer token مشترك بين الخدمات لا يثبت هوية عامل بعينه. عامل يملك التوكن يستطيع ادعاء معرف عامل آخر.

### عالية: إدارة التسجيل لا تملك RBAC حقيقياً

`X-Registered-By` قيمة وصفية يرسلها العميل. لا توجد مطالبة JWT موثقة أو role check أو mTLS identity تثبت أن المتصل Operator.

### عالية: أولوية متغيرات البيئة تتجاوز سلطة الخادم

`RUNTIME_TENANT_IDS` و`RUNTIME_TENANT_ID` تمنعان server discovery بالكامل. في نموذج SaaS يجب أن تكون القائمة المحلية تقاطعاً مع التفويض المركزي، لا بديلاً عنه.

### عالية: ربط النشر غير مكتمل

البحث في `docker-compose.v9.yml` لم يظهر خدمة مستقلة واضحة لـ`model-registry-adapter` بإعدادات:

- `DECISION_SERVICE_URL`
- `DECISION_SERVICE_TOKEN`
- `RUNTIME_TENANT_ID(S)`
- `MODEL_TRAFFIC_CONTROLLER_URL`
- `MODEL_INFERENCE_VERIFY_URL`

الخدمة الموجودة باسم `sahool-model-registry-worker` تستخدم `api.phase_runtime_workers -m model`، وهي مسار runtime قديم مختلف عن `services/model-registry-adapter/service.py`. هذا يخلق احتمال وجود عاملين مختلفين أو كود غير منشور.

### متوسطة: authorization table بلا history كامل

الجدول يسجل `created_by` و`updated_at` فقط. لا يحتفظ بتسلسل enable/disable مستقل أو سبب التغيير أو principal موثق.

### متوسطة: قيود قاعدة البيانات غير كافية

الهجرة 024 لا تفرض:

- طول/صيغة `worker_id`.
- صيغة SHA-256 على `request_hash`.
- طول `idempotency_key`.
- principal type أو actor identity.
- `disabled_at` وسبب الإلغاء.

### متوسطة: CI يثبت الوجود أكثر من السلوك

`wx12_runtime_multitenancy_gate.py` حارس نصي/بنيوي. اختبار PostgreSQL الموجود يثبت partitioning بعد التسجيل، لكنه يثبت أيضاً أن العامل غير المسجل مسموح له. لا توجد اختبارات لـ:

- unknown worker في production.
- stale replay بعد revoke.
- impersonation لعامل آخر.
- env partition خارج server authorization.
- concurrent register/revoke.

## التحقق المنفذ في هذه الجلسة

- فك ZIP وفحص بنية الملفات: PASS.
- `wx12_runtime_multitenancy_gate.py`: PASS.
- `wx12_runtime_certification_gate.py`: PASS.
- اختبارات Model Registry Adapter: `7 passed`.
- compileall للخدمات ذات الصلة: لم تظهر أخطاء قبل انتهاء مهلة التنفيذ.
- اختبارات PostgreSQL للعامل: `2 skipped` لغياب `DATABASE_URL`.
- تحذيران فقط: استخدام FastAPI `on_event` القديم.

## مخطط التتبع المختصر

```text
Operator/API
  └─ POST worker→tenant registration
      └─ decision_runtime_worker_tenants (mutable projection)

Model Registry Adapter
  ├─ resolve_tenants()
  │   ├─ env list/single tenant  [يتجاوز الاكتشاف]
  │   └─ GET worker tenants
  └─ لكل tenant:
      └─ GET runtime-work + worker_id + X-Tenant-Id
          ├─ service token guard إن كان مضبوطاً
          ├─ worker_tenant_authorized
          │   ├─ لا تسجيل → ALLOW   [ثغرة]
          │   └─ مسجل → enabled row required
          ├─ durable claim/lease
          └─ work item
              ├─ activation/rollback
              ├─ verification/rollout
              ├─ monitoring/retraining
              └─ reconcile
                  └─ external adapter/CAS
                      └─ receipt → Decision-Service
```

## خطة الإغلاق الصحيحة

1. إضافة وضع إنتاجي إلزامي `RUNTIME_WORKER_AUTHZ_REQUIRED=true` وجعل unknown worker يرفض دائماً؛ في production يجب أن يكون هذا السلوك غير قابل للتعطيل.
2. إنشاء جدول أوامر append-only، مثلاً `decision_runtime_worker_tenant_commands`، بمفتاح idempotency فريد عالمياً لكل عامل، ثم إسقاط projection للحالة الحالية منه.
3. استخدام هوية workload موثقة: mTLS/SPIFFE أو JWT service identity، واشتقاق `worker_id` من الهوية بدلاً من قبولها من query/path.
4. حماية register/list بصلاحيات منفصلة: operator admin مقابل worker self-discovery.
5. جعل env tenant list قيداً إضافياً: `effective = server_authorized ∩ env_allowed`، وعدم السماح للـenv بإنشاء صلاحية.
6. إضافة migration بقيود صيغة وطول، و`disabled_at`, `disabled_by`, `reason`, `command_id`.
7. توحيد مسار النشر: إما نشر `model-registry-adapter/service.py` صراحة، أو حذف المسار غير المستخدم وربط compose/Helm/K8s بالخدمة الصحيحة.
8. إضافة اختبارات PostgreSQL وتكامل HTTP للحالات الحرجة المذكورة، وتشغيلها كمانع merge.
9. تدوير service token وتحويله من قيمة مشتركة إلى credential لكل workload مع audience محدد.
10. إضافة metrics وaudit events: authz_denied, unknown_worker, stale_replay_conflict, tenant_discovery_count, lease_claim_conflict.

## التصنيف النهائي

| المحور | النتيجة |
|---|---|
| دورة Runtime والـleases | سليمة وظيفياً |
| اكتشاف المستأجرين | موجود |
| عزل العامل بعد التسجيل | ناجح |
| عزل العامل غير المسجل | فاشل |
| سلامة revoke/idempotency | غير مكتملة |
| هوية workload | غير مثبتة |
| ربط Compose بالخدمة الجديدة | غير مثبت |
| جاهزية اعتماد إنتاجي | محجوبة |

الحزمة تصلح كزيادة وظيفية multitenancy، لكنها لا تستحق وصف “production tenant isolation verified” قبل إغلاق مسار unknown-worker، دفتر أوامر idempotency، وهوية العامل، وربط النشر الفعلي.

---

## ملحق التكامل (أُضيف عند الإنزال — لا يُعدَّل النصّ الأصليّ أعلاه)

التقرير حُلِّل على `sahool_73666ee_multitenancy_verified.zip`؛ معظم بنوده كان قد عولج في
كوميت التصلّب `a0f3e24` (ردّاً على FORENSIC_AUDIT_SAHOOL_73666EE) قبل وصول هذا التقرير،
وبند واحد جديد أُغلق في كوميت هذا الملحق. الخريطة بنداً بنداً:

| بند التقرير | الحالة عند الإنزال |
|---|---|
| حرجة: fail-open للعامل غير المسجّل | **مُعالَج @ `a0f3e24`** — راية مرحليّة `DECISION_STRICT_WORKER_TENANTS` (fail-closed)، برهان HTTP 403 لعامل مجهول على PG حقيقيّ. الافتراض off يصون التنصيبات المفردة؛ قلبه ضمن قائمة تفعيل الإنتاج للمشغّل. |
| حرجة: replay يعكس الإلغاء | **مُعالَج @ `a0f3e24`** — migration 025: سجلّ أوامر append-only `decision_runtime_worker_tenant_commands` (UNIQUE(worker_id, idempotency_key) + resulting_revision) + الجدول القائم إسقاطاً بمراجعة رتيبة؛ برهان enable→disable→stale-replay يبقى معطَّلاً. (التصميم المقترح في التقرير — البند 2 من خطّة الإغلاق — هو المُنفَّذ حرفيّاً.) |
| عالية: هويّة العامل غير مربوطة تشفيريّاً | **فجوة OPEN موثَّقة** `WORKER-IDENTITY-BINDING` في `sahool-brain/gaps/registry.md` — اعتماد لكلّ workload (mTLS/SPIFFE/JWT) قرار بنية تحتيّة، لا يُقلَّد بترويسة. |
| عالية: التسجيل بلا RBAC حقيقيّ | ضمن الفجوة نفسها (`runtime.worker_tenant.manage` في التصميم المُوصى). الحدّ الحاليّ: التوكن المشترك opt-in + `DECISION_REQUIRE_AUTH_TOKEN` يجعل SoR بلا توكن غير جاهز (readyz degraded). |
| عالية: أولويّة env تتجاوز الخادم | **مُستوعَبة تحت strict mode** — الـfeed يتحقّق من كلّ طلب خادميّاً؛ env pin خارج القسمة يُرفض 403 (لا يستطيع "إنشاء" صلاحيّة). التقاطع الصريح `configured ∩ authorized` في الـadapter تحسين لاحق ضمن فجوة الهويّة. |
| **عالية: ربط النشر غير مكتمل** | **البند الجديد الوحيد — مؤكَّد وأُغلق في كوميت هذا الملحق.** compose كان يشغّل فقط `sahool-model-registry-worker` (`api.phase_runtime_workers model` — عامل منصّاتيّ يعالج `model_promotion_history_runtime`، **مكمِّل لا بديل**) بينما `services/model-registry-adapter` (runtime دورة الحياة WX-12) بلا خدمة. أُضيفت `sahool-model-lifecycle-adapter` خلف profile اختياريّ `model-lifecycle` (الإنتاج يتطلّب URLs/tokens خارجيّة يوفّرها المشغّل — بدء صامت نصف-مُهيّأ خطأ)، بكامل متغيّراتها في `.env.example`، والبوّابة تمنع انحدار الربط. |
| متوسّطة: جدول التفويض بلا history | **مُعالَج @ `a0f3e24`** — السجلّ الـappend-only هو الـhistory (actor + requested state + revision + hash + timestamp). `disabled_at/reason` المقترحان يُغطّيهما السجلّ فعليّاً (أمر disable = صفّ دائم بمنشئه ووقته). |
| متوسّطة: قيود DB غير كافية | **مُعالَج @ `a0f3e24`** — CHECKs الطول/الصيغة على السجلّ (صلبة) والإسقاط (NOT VALID). |
| متوسّطة: CI يثبت الوجود لا السلوك | **مُعالَج @ `a0f3e24`** — 5 اختبارات سلوك على PG+HTTP (unknown-worker strict 403 · stale replay · append-only/CHECKs · رتابة revision · قسمة الـfeed) هي الدليل الأوّليّ؛ البوّابة الساكنة صارت ثانويّة وعُمِّقت (ومعها رموز ربط النشر). |
| بند الخطّة 9 (توكن لكلّ workload) وبند 10 (metrics/audit events) | ضمن `WORKER-IDENTITY-BINDING` (الأوّل) ومؤجَّل صادق كتحسين رصد (الثاني — أحداث outbox موجودة لكلّ أمر تسجيل). |

**ملاحظة منهجيّة:** اختبارات PG في بيئة المُدقِّق `skipped` لغياب `DATABASE_URL` — كلّ البراهين
أعلاه نُفِّذت محلّيّاً على Postgres حقيقيّ (قاعدة نظيفة، migrations 001–025) وفي CI.
