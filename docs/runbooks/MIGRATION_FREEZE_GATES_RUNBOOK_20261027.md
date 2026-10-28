# Runbook — الهجرات المحجوبة خلف البوّابات المجمّدة

> **هذه الوثيقة لا تأذن بشيء.** لا تفتح بوّابة، ولا تُصدِر تفويض GATE-01، ولا تضبط
> `SAHOOL_MIGRATE_APPLY`، ولا تطبّق هجرة. هي إجراءٌ مكتوب لِما يلزم **حين** يقرّر المالك
> ذلك، مع شروط التوقّف والإيصالات. كلّ خطوة فيها تحمل علامة **قرار المالك** حيث يلزم.
>
> المرجع: `main` = `5c7e1cb83`، 2026-10-27. الحقائق مقتبسة بمواضعها؛ ما لا يذكره المستودع
> مكتوب **UNKNOWN**. الحالة الحيّة لقاعدتي staging والإنتاج **غير مقروءة منذ 2026-10-16**.

## ١. ثلاث طبقات تجميد — كلٌّ يحجب شيئاً مختلفاً

| الطبقة | ما تحجبه | آليّتها | من يفتحها |
|---|---|---|---|
| **أ. GATE-01** (تجميد المسارات الفيزيائيّة في CI) | **تسجيل** أيّ هجرة جديدة: `migrations/MANIFEST.txt` و`scripts_v9/run_migrations.sql` و`docs/architecture/db_ownership.yml` مسارات مجمّدة (`docs/architecture/gate01_policy.json` → `frozen_paths`)، والحالة `CLOSED` | `scripts/ci/gate01_frozen_path_guard.py` في وظيفة `gate01-physical-effect-freeze` (`.github/workflows/no-report-only-change.yml`) — يحمرّ أيّ PR يمسّ مساراً مجمّداً بلا تفويضٍ مطابق للبايتات | تفويضٌ (adjudication) يصدره **المالك** لكلّ تغيير، يُستهلك مرّة واحدة |
| **ب. إذن التطبيق** `SAHOOL_MIGRATE_APPLY` | **تطبيق** أيّ هجرة بالمُهاجر: بدونه يطبع `MIGRATIONS_NOT_APPLIED reason=apply_not_permitted` ويقرأ المخطّط قراءةً فقط (`migrations/apply_in_compose.sh:53-69`) | متغيّر بيئة على خدمة المُهاجر؛ `deploy/railway/Dockerfile.migrate` لا يخبزه (`sahool-brain/decisions/ledger.md:3695`) | **المالك** — المشغّل يضبطه عند قرار الهجرة فقط |
| **ج. تجميد الحادثة** (2026-10-12) | أيّ دمج يمسّ النشر، أو تغيير على Railway، أو إعادة تشغيل للمُهاجر، أو هجرة | قاعدة مالك مكتوبة (`sahool-brain/hot.md`، والفجوة المفتوحة في `sahool-brain/gaps/registry.md` حول حادثة المُهاجر غير المحروس) | **المالك** — «فكّ التجميد مأذون مسارَ عمل، وشروط تطبيق الهجرات الحيّة لم تُثبت» (قرار 2026-10-27) |

**لماذا الثلاث معاً:** الطبقة أ تمنع *إضافة* هجرة إلى المستودع؛ ب تمنع *تطبيقها* آليّاً؛ ج تمنع
*أيّ مسٍّ* للبيئة الحيّة. فتح أ لا يفتح ب، وفتح ب لا يجعل ج مستوفاة.

**تحذير بنيويّ قبل أيّ PR يمسّ `migrations/`:** خدمة المُهاجر `sahool-migrate-main` موصولة بفرع
`main` في البيئتين، بأنماط مراقبة `/migrations/**` و`/deploy/railway/Dockerfile.migrate`
(`docs/architecture/railway_watch_patterns.json`)، بسياسة إعادة تشغيل `NEVER`. أيّ دمجٍ يمسّ
`migrations/` **يُطلِق المُهاجر في staging والإنتاج**. يعمل قراءةً فقط ما دام
`SAHOOL_MIGRATE_APPLY≠1` — لكنّه يعمل. والفجوة `MIGRATOR-AUTO-DEPLOYS-ON-EVERY-MAIN-PUSH-01`
مفتوحة. فقبل الدمج: **تأكّد من قيمة `SAHOOL_MIGRATE_APPLY` على خدمة المُهاجر في البيئتين**
(قراءةً، بلا كشف قيم أسرار)، وإلّا فدمجٌ واحد يكرّر حادثة 2026-10-12.

## ٢. الجرد

### ٢.١ المجموعة A — في MANIFEST، **غير مثبتة التطبيق** حيّاً

خطّ الأساس الحيّ: آخر فحص PASS قُرئ على 231 ملفّاً (2026-10-12/13). في 2026-10-16 سجّل
مُهاجرا البيئتين `apply_not_permitted` و«ثلاثة أعمدة U07 غائبة»
(`docs/runbooks/REMAINING_RUNTIME_ACCEPTANCE_20261016.md`)، أي أنّ v234 **غائبة**. لا سجلّ
في المستودع لتشغيلات المُهاجر بعد #1201 و#1211: حالة v235 وv236 حيّاً **UNKNOWN**.

| الهجرة | الغرض | معاملة؟ | الأقفال والأثر | الاعتماديّات | الأدلّة القائمة |
|---|---|---|---|---|---|
| `v234_learning_agronomic_review.sql` | U07: المراجعة الزراعيّة مستقلّة عن التتبّع | `BEGIN…COMMIT` | 3 أعمدة (اثنان `NOT NULL DEFAULT`) + قيدا `CHECK` **بلا `NOT VALID`** ⇒ مسحٌ كامل تحت `ACCESS EXCLUSIVE` على `online_learning_updates` | v119 (الجدول) | وحدة بلا قاعدة (`tests_v9/test_learning_review_persistence_gap.py`)؛ PGlite (ليس PostgreSQL أصليّاً)؛ ضمن MANIFEST كاملاً على قاعدة **فارغة** في CI. فحص يدويّ 2026-10-27 على PG16: تطبيقٌ مزدوج سليم + 12 حالة قيد صحيحة |
| `v235_decision_chain_correlation.sql` | `correlation_id` يملكه الخادم على 5 جداول قرار/تنفيذ | **لا** | 5 `ADD COLUMN` + 5 `CREATE INDEX` **بلا `CONCURRENTLY`** (تحجب الكتابة طوال البناء) + 3 دوالّ + 10 مشغّلات (`DROP`/`CREATE`) **تغيّر سلوك الكتابة**: ترفض تعديل `tenant_id` و`correlation_id` ومفتاح الأب | v66، v67، v68، v78، v178 | PG16 أصليّ على قاعدة فارغة (`services/decision-service/tests/test_platform_v235_correlation_pg16.py`، 62 ناجحاً في CI). **لا اختبار ترقية على بيانات** |
| `v236_raster_follow_up_requests.sql` | جدول طابور متابعة التصوير | `BEGIN…COMMIT` | جدول جديد فقط + RLS `FORCE` + سياسة + فهرس — **لا قفل على جدول قائم** | لا FK | PG16 أصليّ، v236 وحدها على قاعدة فارغة (`tests_v9/test_imagery_follow_up_pg16.py`، 9/9) |

ترتيب الخطر: v236 أدنى، ثمّ v234، ثمّ **v235 الأعلى** (بلا معاملة، فهارس حاجبة، مشغّلات تغيّر
سلوك الكتابة).

### ٢.٢ المجموعة B — مطلوبة لكنّها **لم تدخل MANIFEST** (تحجبها GATE-01 أو قرار)

كلّها `open` في `sahool-brain/gaps/registry.md` ومصنّفة في `sahool-brain/reports/gap_triage_20261025.md`.

| الفجوة | التغيير المطلوب في المخطّط | الحاجب |
|---|---|---|
| `CP997-05-EDGE-IDEMPOTENCY-GLOBAL-UNIQUE-VS-TENANT-LOOKUP-01` | فهرس فريد جزئيّ `(tenant_id, idempotency_key)` + هدف `ON CONFLICT` في الراوتر | GATE-01؛ محاولةٌ سابقة ضمن v231 حمّرت وأُزيلت |
| `SECURITY-DEFINER-FUNCTIONS-OWNED-BY-SUPERUSER-WITH-PUBLIC-EXECUTE-01` | جرد الكتالوج ثمّ هجرة: مالك `NOSUPERUSER`، `search_path` ينتهي بـ`pg_temp`، `REVOKE … FROM PUBLIC` | تجميد + MANIFEST |
| `TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01` | توحيد اسم GUC المستأجر في سياسات RLS | تجميد + قرار ترتيب من المالك |
| `UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01` | مخطّط مصدر الماء لكلّ حقل/موسم + تعديل `phase_runtime_workers.py` المجمّد | GATE-01 (MANIFEST + العامل) |
| `RS-WEEKLY-INSIGHTS-DELIVERY-01` | جدول لقطة/outbox أسبوعيّ | تجميد + خيار المالك |
| `REPORT3-U08-FOLLOWUP-TASK-NOT-LINKED-TO-OUTCOME-01` | علاقة متابعة ↔ ممارسة/نتيجة | خيار المالك + GATE-01 |
| `REPORT2-C04-QUEUED-PUSH-RECEIPTS-HAVE-NO-CONSUMER-01` | حالات/حقول تسليم جديدة | المالك + التجميد |
| `CAP-INT-004-INTEGRATION` | هجرة لحفظ الإيصالات | المالك + التجميد |
| `FIELD-WEATHER-OVERLAY-HAS-A-READER-AND-NO-WRITER-01` | الخيار ١ «قد» يحتاج هجرة | المالك |
| نسخة حدود الموسم (مراجعة الموسمين 2026-10-27، `S4-b`) | ربط الموسم بنسخة مضلّعه ومساحته التاريخيّة | قرار تصميم + GATE-01 |

### ٢.٣ المجموعة C — هجرات خدمة القرار (مشغّلٌ وسجلٌّ منفصلان، خارج GATE-01)

`034` (العمليّة A على staging) و`036` بلا قراءة حالة تطبيقٍ في المستودع
(`REMAINING_RUNTIME_ACCEPTANCE_20261016.md`). تُعامَل بإجراءها الخاصّ هناك؛ لا يغطّيها هذا الدليل.

### ٢.٤ خارج النطاق

`v9_append_only_enforcement.down.sql` و`v9_rls_tenant_isolation.down.sql` مستثنيان عمداً من
MANIFEST. لا نصّ تراجع لـv234–v236. التراجع بالاستعادة فقط (§٥).

## ٢-مكرّر. تعارضٌ يجب أن يحسمه المالك قبل أيّ تطبيق: **مسار التطبيق**

| | المسار ١ — ملفٌّ واحد بايتاته بعينها | المسار ٢ — المُهاجر (`SAHOOL_MIGRATE_APPLY=1`) |
|---|---|---|
| المصدر | `REMAINING_RUNTIME_ACCEPTANCE_20261016.md`: «طبّق بايتات v234 هذه فقط … لا تستدعِ مشغّل MANIFEST، ولا تضبط `SAHOOL_MIGRATE_APPLY=1`، ولا تُعِد إقلاع الأدوار» | `migrations/apply_in_compose.sh` كما هو |
| ما يُنفَّذ | ملفّ الهجرة وحده | **234 ملفّاً** بترتيب MANIFEST بلا معاملة جامعة، ثمّ **إعادة تجهيز الأدوار** (`ALTER ROLE … PASSWORD` من البيئة، المنح، `REVOKE CONNECT … FROM PUBLIC`) |
| الخطر | يُفترض أن يكون المنفِّذ هو الدور الذي أنشأ الامتيازات الافتراضيّة، وإلّا لم يرث الجدول الجديد منحه (§٤.٣) | نطاقٌ أوسع بكثير من الدفعة؛ هو بالضبط ما فعلته حادثة 2026-10-12 |
| التوصية | **المسار ١** لهذه الدفعة | فقط بقرارٍ منفصل وبعد تجربة كاملة على نسخة مستعادة |

## ٣. فتح الطبقة أ — تسجيل هجرة جديدة (المجموعة B)

**لكلّ هجرة تفويضٌ منفصل.** التفويضات الأربعة عشر القائمة كلّها `CONSUMED`، ولا تفويض نشط.

1. **قرار المالك** بالتغيير ونطاقه (ملفّ الهجرة + أيّ مسار مجمّد آخر يلزم).
2. **PR الكود والهجرة أوّلاً بلا MANIFEST**، باختبار PostgreSQL أصليّ على **قاعدة بمخطّط سابق
   وبيانات** (لا قاعدة فارغة فقط)، وتجربة تطبيقٍ مزدوج.
3. **ملفّ تفويض** في `docs/architecture/gates/adjudications/GATE01-ADJ-<date>-<n>.json`، يتحقّق منه
   الحارس (`scripts/ci/gate01_frozen_path_guard.py::_authorization_errors`):
   - `schema: "sahool.gate01_adjudication/v1"`، و`gate_id` مطابق، و`status: "ISSUED"`، و`one_time` غائب أو `true`؛
   - `expires_on` قابل للتحليل وغير منتهٍ؛
   - `phase0_baseline_ref.commit_sha` = خطّ الأساس في السياسة؛
   - `allowed_paths` يشمل كلّ مسار مجمّد يمسّه الـPR: عادةً `migrations/MANIFEST.txt` و`scripts_v9/run_migrations.sql`، و`docs/architecture/db_ownership.yml` إن تغيّرت ملكيّة جدول؛
   - `authorized_blobs` = blob SHA لكلّ مسار من تلك بالضبط، و`authorized_patch_sha256` = sha256 للأسطر المرتّبة `path\0blob\n`.
   - **ما لا يتحقّق منه الحارس:** `approved_by` والتوقيع والـPR و`supplemental_byte_bindings` — هذه سجلٌّ فقط، والملفّات نفسها تصرّح بذلك (`provenance_honesty`).
4. **قيود الـPR نفسه:** تبقى `v206_rls_final_hardening.sql` آخر مدخل `.sql` في MANIFEST (وإلّا يخرج المُهاجر بـ1، `apply_in_compose.sh:84-88`)؛ `scripts_v9/run_migrations.sql` متزامن (`tests_v9/test_migration_runners_in_sync_20260705.py`)؛ `migrations/schema_probe_contract.env` معاد توليده ليطابق بصمة MANIFEST الجديدة.
5. **قبل الدمج:** التحقّق من `SAHOOL_MIGRATE_APPLY` على المُهاجر في البيئتين (§١، التحذير البنيويّ).
6. **بعد الدمج:** التزامٌ منفصل يختم التفويض `CONSUMED` بـ`merge_sha` و`consumed_on`/`consumed_by`. تفويضٌ `ISSUED` نزلت بايتاته يحجب **كلّ** PR لاحق (`stale_authorization_errors`).

**التسجيل لا يعني التطبيق.** دخول الهجرة MANIFEST يضعها في المجموعة A، وتطبيقها حيّاً هو §٤.

## ٤. فتح الطبقتين ب وج — تطبيق المجموعة A

### ٤.١ الشروط المسبقة (كلّها **NOT_RUN** اليوم)

مفصّلة في وثيقة #1294 (`sahool-brain/reports/migration_batch_v234_v236_prerequisites_20261027.md` على فرعه):

1. **نسخة احتياطيّة مُثبتة باختبار استعادة** للبيئة الهدف، بوقتٍ وبصمةٍ مسجّلين.
2. **فحص حيّ قراءةً فقط** أوسع من الجداول والأعمدة: القيود وتعريفاتها و`convalidated`، الفهارس و`indisvalid`، RLS وFORCE والمالك والسياسات، الأدوار وامتيازاتها، أحجام الجداول المعنيّة. `migrations/probe_schema_state.sh` يقرأ الجداول والأعمدة فقط.
3. **تجربة على النسخة المستعادة** بالمسار المختار في §٢-مكرّر، مع قياس الأقفال تحت حِمل كتابيّ، وتوافق نسخة التطبيق المنشورة حاليّاً مع المخطّط الجديد (مشغّلات v235 ترفض تحديثاتٍ كانت تُقبل).
4. **حقن الفشل في v235** بعد كلّ مرحلة (منها بين `DROP TRIGGER` و`CREATE TRIGGER`)، ثمّ إعادة الملفّ ومقارنة `pg_get_indexdef` و`md5(pg_get_functiondef)` و`pg_get_triggerdef` وبصمات البيانات بحالةٍ مرجعيّة.
5. **قرار المالك في RPO**: إيقاف الكتابات أثناء النافذة، أو حفظ ما يُكتب بعد النسخة — الاستعادة ليست تراجعاً بلا خسارة.
6. **قرار المالك** بالمسار (§٢-مكرّر) وبالنافذة الزمنيّة، **لكلّ بيئة على حدة**: staging أوّلاً، والإنتاج بعد قبول staging.

### ٤.٢ التنفيذ — المسار ١ (ملفٌّ واحد)

لكلّ ملفّ بترتيب MANIFEST (v234 ثمّ v235 ثمّ v236)، وفي جلسةٍ مستقلّة لكلّ ملفّ:

```bash
# 0) البايتات المعتمدة بعينها
git show <APPROVED_SHA>:migrations/<FILE>.sql > /tmp/<FILE>.sql
sha256sum /tmp/<FILE>.sql            # يُسجَّل ويُطابَق بالإيصال

# 1) لقطة قبل (قراءةً فقط) — انظر §٤.٣ لكلّ ملفّ
# 2) التطبيق بالدور الذي يملك الجداول ويملك الامتيازات الافتراضيّة
PGOPTIONS='-c lock_timeout=5s -c statement_timeout=15min -c search_path=public' \
  psql "$OWNER_DSN" -X -v ON_ERROR_STOP=1 -f /tmp/<FILE>.sql
# 3) لقطة بعد + فحوص §٤.٣
```

- الملفّ يملك `BEGIN/COMMIT` (v234/v236): **لا تلفّه بمعاملةٍ خارجيّة** «للتجربة»؛ سيُلتزَم من الداخل.
- v235 **بلا معاملة**: فشلٌ في منتصفه يترك تطبيقاً جزئيّاً ⇒ §٥ فوراً.
- انتهاء `lock_timeout` أو أيّ خطأ = **فشل**: افصل، اقرأ الكتالوج من جديد، ولا تُعِد قبل فهم الحالة.
- **لا** `SAHOOL_MIGRATE_APPLY=1`، ولا إعادة تشغيل للمُهاجر، ولا إقلاع أدوار.

### ٤.٣ فحوص ما بعد كلّ ملفّ

**v234:**
```sql
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'online_learning_updates'
   AND column_name IN ('review_status','agronomically_approved','agronomic_review');
SELECT conname, convalidated, pg_get_constraintdef(oid)
  FROM pg_constraint
 WHERE conrelid = 'online_learning_updates'::regclass AND conname LIKE 'chk_oluj_agronomic_%';
SELECT review_status, agronomically_approved, count(*) FROM online_learning_updates GROUP BY 1,2;
-- المتوقَّع: قيدان convalidated=true؛ الصفوف القديمة كلّها unreviewed/false
```

**v235:**
```sql
SELECT indexrelid::regclass, indisvalid, pg_get_indexdef(indexrelid)
  FROM pg_index WHERE indexrelid::regclass::text LIKE 'idx_%_correlation';      -- 5، كلّها valid
SELECT proname, md5(pg_get_functiondef(oid)) FROM pg_proc
 WHERE proname IN ('sahool_chain_correlation_root','sahool_chain_correlation_immutable',
                   'sahool_platform_chain_correlation');                         -- 3 = البصمات المرجعيّة
SELECT tgrelid::regclass, tgname, tgenabled FROM pg_trigger
 WHERE tgname LIKE 'trg_%_correlation_%' AND NOT tgisinternal;                   -- 10، كلّها 'O'
```
ثمّ قبولٌ وظيفيّ: كتابةٌ مشروعة من التطبيق المنشور تنجح، وتعديل `tenant_id` أو `correlation_id` يُرفض.

**v236:**
```sql
SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = 'raster_follow_up_requests'::regclass;
SELECT polname, pg_get_expr(polqual, polrelid) FROM pg_policy WHERE polrelid = 'raster_follow_up_requests'::regclass;
SELECT has_table_privilege('sahool_app', 'raster_follow_up_requests', 'SELECT,INSERT,UPDATE');
-- false ⇒ المنفِّذ ليس صاحب الامتيازات الافتراضيّة؛ منحٌ صريح يحتاج قراراً منفصلاً لا اجتهاداً
```

**وللجميع:** `migrations/probe_schema_state.sh` قراءةً فقط بعد الملفّات الثلاثة ⇒ المتوقَّع
`SCHEMA_INSPECTION status=PASS … first_missing=none` على بصمة MANIFEST الحاليّة.

### ٤.٤ ترتيب البيئات

staging: §٤.١ ← §٤.٢ ← §٤.٣ ← قبول التطبيق المنشور على staging (الكتابة والقراءة الطبيعيّتان
لمسارات الجداول الخمسة وجدولَي v234/v236) ← **قرار مالك** ← الإنتاج بالخطوات نفسها، بنسخته
الاحتياطيّة المُثبتة الخاصّة.

## ٥. التوقّف والتعافي

| الموضع | الحالة | الإجراء |
|---|---|---|
| قبل التطبيق | شرطٌ من §٤.١ لم يُستوفَ | **لا تبدأ** |
| v234/v236 أثناء التطبيق | خطأ أو انتهاء مهلة | المعاملة تتراجع وحدها؛ اقرأ الكتالوج وأكّد عدم تغيّره |
| v235 أثناء التطبيق | خطأ بعد بعض العبارات | تطبيقٌ جزئيّ: قارن بالمرجع؛ إعادة الملفّ مقبولة **فقط** بعد إثبات حقن الفشل (§٤.١-٤) أنّها تستعيد التعريفات المتطابقة؛ وإلّا الاستعادة |
| بعد التطبيق | التطبيق المنشور يفشل في كتابةٍ مشروعة | أوقف الكتابات، وقرار المالك: تعطيل المشغّل المعنيّ بقرارٍ موثّق، أو الاستعادة |
| أيّ لحظة | شكّ في سلامة البيانات | الاستعادة من النسخة المُثبتة، بالـRPO المقرَّر |

لا نصوص تراجع لـv234–v236، والنصّان القديمان غير مختبرَين (`MIGRATION-DOWN-SCRIPTS-UNTESTED-POSSIBLY-STALE-01`)
ولا يُستعملان هنا.

## ٦. الإيصال — لكلّ ملفّ ولكلّ بيئة

```text
environment:            staging | production
migration_file:         vNNN_….sql
approved_source_sha:    <40 hex>
file_sha256:            <64 hex>
path:                   1 (single file) | 2 (migrator)   — مع قرار المالك
owner_approval_ref:     <نصّ أو رابط>
backup_id + restore_test_ref:
pre_snapshot_ref / post_snapshot_ref:
started_utc / finished_utc / lock_wait_max:
post_checks:            PASS | FAIL (+ المخرجات)
schema_probe:           SCHEMA_INSPECTION status=… first_missing=…
app_acceptance:         PASS | FAIL | NOT_RUN
operator:
```

يُحفظ الإيصال تحت `certification/evidence/` ويُسجَّل في `sahool-brain/log.md`، وتُحدَّث الفجوات
المعنيّة. **نجاح النشر ليس قبول المخطّط.**

## ٧. تعارضات وتقادم وُجدت أثناء الجرد

1. مسار التطبيق (§٢-مكرّر): هذا الدليل يتبنّى المسار ١ ويُبقي القرار للمالك.
2. صفّ `REPORT3-U07-REVIEW-DECISION-NOT-PERSISTED-01` في السجلّ ما زال يقول «غير مدموج»، بينما
   `GATE01-ADJ-2026-10-16-001` يثبت دمجه في #1199 (`9f0bcece`) — مدموجٌ في الكود، غير مطبَّق حيّاً.
3. ادّعاء «لا قاعدة إنتاج حيّة» في التصنيف وفي `MIGRATION-STATE-IN-PRODUCTION-IS-UNREAD-01`
   يتعارض مع فحصَي القراءة 2026-10-12/13 على قاعدة الإنتاج.
4. مواضع أسطر متقادمة في السجلّ لـ`apply_in_compose.sh` (البوّابة الآن `:53-69`، ولا كلمات مرور افتراضيّة).
5. `supplemental_byte_bindings` في تفويضات v234/v235/v236 لا يقرؤها الحارس: ملفّات `.sql` نفسها لم تكن محروسة بـGATE-01.

## ٨. الحالة

| البند | الحالة |
|---|---|
| v234 حيّاً | **غائبة** (2026-10-16) |
| v235، v236 حيّاً | **UNKNOWN** |
| الشروط §٤.١ | **NOT_RUN** |
| قرار مسار التطبيق | **قرار المالك — معلَّق** |
| المجموعة B | لا تفويض صادر |
