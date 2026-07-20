# SCOUT-INGEST-01 · B1.3 — إسقاط المقبولة إلى domain (مواصفة للمراجعة)

**الحالة:** ✅ **(أ) معتمدة ومُنفَّذة** (v199 + عامل + نقطة قراءة + برهان حيّ). **السابق:** B1.2b (`scout-ingest-service`
خدمة مالكة). **التالي:** B1.4 (Kobo) · **الدَّين الموثَّق:** B1.3b (توحيد العرض مع FieldView، محفّزه في §6).

---

## 1. ما هو B1.3 (الغاية)

الإدخالات الخارجيّة التي **اجتازت التحقّق السباعي** (`external_submissions.trust_status='accepted'`) يجب أن
تصبح مرئيّة كـ**مشاهدة ميدانيّة في domain** — لا أن تبقى حبيسة جدول الإدخال الخامّ. عامل `claim→project`
يقرأ المقبولة، يُطبّعها إلى دبّوس مشاهدة، ثمّ يُعلّم الصفّ `projected` (أو `dead_letter` عند فشل نهائيّ).
القاعدة الحاكمة مفروضة: **لا دخول للـdomain قبل التحقّق السباعي** (المقبولة فقط تُسقَط).

---

## 2. القرار الحاكم (يجب حسمه أوّلاً) — من يكتب دبّوس المشاهدة؟

**المأزق:** المواصفة العامّة (`SCOUT-INGEST-01_B1_spec.md`) قالت «تُسقَط عبر كتّاب `scouting_pins`/`observations`
**القائمين**». لكن جدولَي الوجهة **مملوكان للمنصّة، بكاتب وحيد**:

| الجدول | المالك/الكاتب | المصدر |
|---|---|---|
| `scouting_pins` | `[sahool-platform]` | `migrations/v94_scouting_pins.sql` · `db_ownership.yml:915` |
| `observations` | `[sahool-platform]` | `storage/lite_store.py` · `db_ownership.yml:759` |

هذا يصطدم مع الانضباط الذي صلّبناه في B1.2b (قرار (ج) / السابقة #201): **الخدمة تملك سطحها، المنصّة لا تنمو،
الكاتب الوحيد مقدَّس** — بل أضفنا حارساً يفرض أنّ `external_submissions` **يكتبه scout-ingest وحده**؛ والقاعدة
المتناظرة تقول: `scouting_pins` **تكتبه المنصّة وحدها**. فكتابة scout-ingest المباشرة في `scouting_pins`
تخرق نفس المبدأ الذي فرضناه للتوّ.

### الخيارات

- **(أ) [موصى] scout-ingest يملك جدول إسقاطه الخاصّ + يقرؤه عبر نقطته:**
  هجرة `external_field_observations` (مملوك `scout-ingest-service`، RLS FORCE، نمط v94) + عامل إسقاط
  **داخل scout-ingest** (accepted → صفّ مُطبَّع) + نقطة قراءة `GET /internal/scouting/external-observations`.
  **صفر تغيير منصّة · صفر خرق ملكيّة · يتّسق حرفيّاً مع #201 وقرار (ج).** توحيد العرض مع FieldView (أن
  تظهر المشاهدات الخارجيّة في دبابيس FieldView القائمة) يصبح **قراراً منفصلاً صريحاً B1.3b** (قراءة-اتّحاد
  على المنصّة، لا كتابة).

- **(ب) عامل إسقاط على المنصّة (Pattern A) يكتب `scouting_pins`:**
  المنصّة (المالكة) تكتب جدولها بنفسها؛ عامل `phase_runtime_workers`-style يقرأ `accepted` من
  `external_submissions` (منح SELECT للمنصّة) ويكتب `scouting_pins`. **يوحّد نموذج القراءة فوراً** لكن
  **يُنمّي وحدات المنصّة** (حارس module baseline، درس #178) — يعاكس انضباط strangler الذي دفعنا لقرار (ج).

- **(ج) scout-ingest يكتب `scouting_pins` مباشرة:** **مرفوض** — يخرق الكاتب الوحيد + الحارس المتناظر + RLS.

### التوصية: (أ)

يبقي B1.3 **بالكامل داخل ملكيّة scout-ingest** (صفر نموّ منصّة، صفر خرق ملكيّة، قابل للشحن فوراً)، ويجعل
**توحيد نموذج القراءة قراراً منفصلاً صريحاً** بدل تهريبه داخل عامل. متّسق مع قرار (ج): «مدخل خارجيّ ⇒ خدمة
مالكة تملك سطحها كاملاً — من الإدخال إلى القراءة».

---

## 3. التصميم (على افتراض اعتماد (أ))

### 3.1 الهجرة `v199_external_field_observations.sql`
جدول مُطبَّع مملوك لـscout-ingest — الحقول من `scouting_pins` (لا اختراع)، بلا حقول واجهة (color/photo):
```
observation_id   TEXT PRIMARY KEY,          -- مشتقّ حتميّاً من submission (idempotency)
tenant_id        UUID NOT NULL,
field_id         TEXT NOT NULL,
source_submission_key TEXT NOT NULL,        -- external_submissions.idempotency_key (نَسَب)
lat              DOUBLE PRECISION,           -- إن وُجِد في normalized_payload (لا اختلاق)
lng              DOUBLE PRECISION,
observed_property TEXT,                      -- من normalized_payload
value            JSONB,                      -- القيمة المرصودة كما طُبّعت
severity         TEXT,
observed_at      TIMESTAMPTZ,
projected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
```
- `UNIQUE`/PK على `observation_id` مشتقّ من `source_submission_key` ⇒ إسقاط **idempotent** (إعادة تشغيل
  العامل لا تُكرّر). `ON CONFLICT (observation_id) DO NOTHING`.
- **RLS FORCE + tenant_isolation** (مسافة واحدة، درس #179) نمط v94/v197.
- `db_ownership.yml`: `external_field_observations` owner/writers=`[scout-ingest-service]`؛
  `external_submissions` يكتسب `readers:[scout-ingest-service]` (العامل يقرؤه — وهو أصلاً مالكه).
- تزامن المُشغّلَين (MANIFEST + run_migrations) + حارس التزامن.

### 3.2 حالة الإسقاط على `external_submissions`
إضافة `projection_status TEXT NOT NULL DEFAULT 'pending' CHECK (IN ('pending','projected','dead_letter'))`
على `external_submissions` (عمود على جدول scout-ingest المملوك — لا مساس بغيره). **فقط `accepted` تُسقَط**؛
`quarantined`/`untrusted` تبقى `pending` بلا محاولة (تُصفّى في claim).

### 3.3 نواة الإسقاط النقيّة (`shared/contracts/ingest/projection.py`)
`project_submission(row) -> ExternalFieldObservation | ProjectionSkip` — دالّة نقيّة تُطبّع
`normalized_payload` إلى صفّ المشاهدة، أو تُرجِع تخطّياً مُصنَّفاً (field_id مفقود ⇒ dead_letter بسبب،
لا صفّ يتيم). قابلة للاختبار في tests_v9 بلا قاعدة (نمط ingest_handler).

### 3.4 العامل (داخل scout-ingest، Pattern A)
`claim` عبر `SELECT … WHERE trust_status='accepted' AND projection_status='pending' ORDER BY received_at
FOR UPDATE SKIP LOCKED LIMIT $N` → `project_submission` → `INSERT … ON CONFLICT DO NOTHING` في
`external_field_observations` → `UPDATE projection_status='projected'` (أو `dead_letter` + سبب عند
ProjectionSkip النهائيّ). يضبط `app.current_tenant` لكلّ عمليّة (دور `sahool_ingest`، لكن الإدراج يحتاج
INSERT على الجدول الجديد ⇒ يُمنَح). حلقة `POLL_SECONDS` + مدخل CLI + خدمة compose خلف
`SCOUT_INGEST_PROJECTION_ENABLED` (off افتراضاً).

### 3.5 نقطة القراءة
`GET /internal/scouting/external-observations?field_id=…` على scout-ingest (بتوكن لكلّ مصدر أو توكن
خدمة قراءة داخليّ — يُحسَم في التنفيذ)، tenant من السياق، RLS يقصّ. نظير `GET /internal/fields` لـ#201.

---

## 4. الحُرّاس + البرهان السلبيّ + التحقّق الحيّ

- **حارس ساكن** `test_v199_external_field_observations_static.py`: RLS FORCE (مسافة واحدة) · PK مشتقّ ·
  ownership=scout-ingest · تزامن المُشغّلَين.
- **حارس النواة** `test_ingest_projection.py` (unit): accepted⇒صفّ مُطبَّع · field_id مفقود⇒dead_letter
  (لا صفّ) · إعادة الإسقاط idempotent (نفس observation_id) · **quarantined لا يُسقَط أبداً** (برهان سلبيّ
  «لا دخول قبل السبعة»).
- **حارس الملكيّة** (تمديد `test_scout_ingest_service_ownership.py`): `external_field_observations` كاتبه
  scout-ingest وحده (لا platform).
- **برهان حيّ** `test_projection_live.py` (integration، PG16): accepted⇒مشاهدة تظهر · quarantined⇒لا شيء ·
  إعادة تشغيل العامل⇒لا تكرار · dead_letter عند field_id مفقود.

## 5. البوّابات (لكلّ commit)
`ruff` · **`pytest -m unit` الكامل** (درس #179، أيّ migration) · `build_release_bundle`+`validate` ·
`production_validation_gate` (migration) · **سويب `scripts/ci/*.py --check` كامل** (درس هذه الجلسة:
خدمة/جدول جديد يمسّ حُرّاس totality/drift — inventory · route_residual · health · dependency · ui-contract ·
api_versioning · route_mount · service_dependency_bundle). تسجيل أيّ نقطة جديدة في عقد المستهلك.

## 6. القرار المُعتمَد (أ) + شرطاه (لمنع تعفّن الدَّين)

**(أ) معتمدة** بمنطق (2) نفسه: (ب) كان سيُنمّي المنصّة في الشريحة التالية مباشرةً فيُبطِل نقاش الحراس الأربعة؛
و(أ) يحترم single-writer مرّتين (المنصّة وحدها تكتب `scouting_pins`، وscout-ingest وحده يكتب جدوله). ازدواج
نموذجَي القراءة **دَين موثَّق مؤجَّل لا خطأ معماريّ** — الـstrangler كلّه قائم على تأجيل التوحيد حتى تنضج الحدود.

**الشرط ①: محفّز B1.3b مكتوب الآن** (بلا محفّز «مؤجَّل» = «منسيّ»): يُوحَّد العرض مع FieldView عند **أوّل
مستهلك قرار حقيقيّ يحتاج رؤية موحّدة** (مثلاً محرّك التوصيات يقرأ الملاحظات الميدانيّة)، **أو** حين يتجاوز عدد
مصادر قراءة الملاحظات الميدانيّة **اثنين**. حينها يُتَّخذ قرار توحيد صريح (قراءة-اتّحاد على المنصّة، لا كتابة
عابرة للملكيّة).

**الشرط ②: عقد قراءة مُعلَن منذ اليوم** (مُنفَّذ): النقطة `GET /internal/scouting/external-observations`
بتوكن خدمة **مخصّص** (`SCOUT_INGEST_READ_TOKEN`، لا `SAHOOL_AGENT_TOKEN` المشترك)، ومُسجَّلة في جرد المسارات
كنموذج قراءة مستقلّ — فلا يكتشف مستهلك مستقبليّ الجدول ويقرؤه SQL مباشرةً (مرض direct-DB الذي طوردَ في p4).
حارس `test_read_channel_uses_dedicated_token_not_shared` يقفل العقد.

## 7. البرهان الحيّ (PG16، `test_projection_live.py`)
تحت الدور المقيَّد + دالّتَي DEFINER: **accepted+field ⇒ مشاهدة واحدة** · **quarantined ⇒ لا شيء** (برهان
سلبيّ «المقبولة فقط») · **field_id مفقود ⇒ dead_letter** (لا يتيم) · **إعادة تشغيل العامل ⇒ صفر مضاعفة**
(idempotent، observation_id مشتقّ + ON CONFLICT). + برهان يدويّ: trigger الخامّ يسمح بتحديث projection_status
ويرفض تحوير content_hash.
