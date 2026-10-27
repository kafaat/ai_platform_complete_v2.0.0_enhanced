# الدفعة المرشّحة v234–v236 — شروط ما قبل تطبيقها على staging

> **حدّ هذه الوثيقة:** شروطٌ ومعطياتٌ مقيسة من المستودع فقط. لا تُطبَّق هجرة، ولا يُشغَّل المُهاجر، ولا تُمسّ قاعدة staging أو الإنتاج. التجميد قائم.
>
> **الأساس:** `main` = `5c7e1cb83`. ومراجعة المالك في 2026-10-27 هي مصدر الشروط الأربعة.
> **الخطّ التاريخيّ:** تقرير الفحص الثلاثيّ على `2c7637563` (2026-10-25)، وهو فحصٌ ثابت بلا خدمات ولا قواعد. يثبت نجاح الحرّاس الثابتة، لا نجاح الترقية على قاعدة قائمة، ولا سلامة البيانات، ولا زمن الأقفال والتراجع.

## ١. ما تحويه الدفعة، وما يفعله المُهاجر فعلاً

| الهجرة | ما تفعله | التغليف | الأقفال المتوقَّعة |
|---|---|---|---|
| `v234_learning_agronomic_review.sql` (55 سطراً) | ثلاثة أعمدة في `online_learning_updates` (اثنان `NOT NULL DEFAULT`) + قيدا `CHECK` **دون `NOT VALID`** | `BEGIN…COMMIT`، كلّ شيء أو لا شيء | `ACCESS EXCLUSIVE` على `online_learning_updates` طوال التحقّق من القيدين (مسحٌ كامل) |
| `v235_decision_chain_correlation.sql` (122 سطراً) | `correlation_id uuid` في خمسة جداول + فهارس جزئيّة + **3 دوالّ و10 مشغّلات `BEFORE INSERT`/`BEFORE UPDATE`** على الجداول الخمسة | **بلا `BEGIN…COMMIT`** | `ADD COLUMN` (NULL) قصير؛ و`CREATE INDEX` **دون `CONCURRENTLY`** ⇒ `SHARE` يحجب الكتابة في `decision_record` و`dispatch_decisions` و`execution_ledger` و`as_applied_irrigation_runs` و`as_applied_irrigation_receipts` طوال بناء كلّ فهرس؛ و`CREATE TRIGGER` ⇒ `SHARE ROW EXCLUSIVE` قصير |
| `v236_raster_follow_up_requests.sql` (38 سطراً) | جدول جديد بـRLS+FORCE وقيود | `BEGIN…COMMIT` | جدولٌ جديد؛ لا قفل على القائم |

**مشغّلات v235 تغيّر سلوك الكتابة، لا المخطّط فقط** (`migrations/v235_decision_chain_correlation.sql:32-121`):

- **عند الإدراج:** الجذر (`decision_record` و`dispatch_decisions`) يأخذ `correlation_id` يولّده الخادم، ويُرفض إدراجٌ يحمله صراحةً. والأبناء يرثونه من الأب في المستأجر نفسه، أو NULL إن لم يوجد أب. والكود القديم لا يذكر العمود، فالمتوقَّع أن يمرّ.
- **عند التحديث:** يُرفض (`check_violation`) أيّ تغييرٍ لـ`tenant_id` أو `correlation_id` أو مفتاح الأب في الجداول الخمسة. **وهذا قيدٌ جديد على كلّ كود يكتب فيها، قديمِه وجديده.**
- **كلفة:** كلّ إدراجٍ في جدولٍ ابن يجري `SELECT` على الأب.

**المُهاجر لا يطبّق ثلاثة ملفّات بل MANIFEST كلّه** (`migrations/apply_in_compose.sh:90-97`): 234 ملفّاً بالترتيب، كلٌّ بـ`psql -f` و`ON_ERROR_STOP=1`، **بلا `--single-transaction`**. ثمّ يعيد تهيئة دور التطبيق ومنحه (السطور 101 وما بعدها). ويتحقّق أنّ آخر مدخل `.sql` هو `v206_rls_final_hardening.sql` (السطر 84). فالتجربة يجب أن تجري بالمُهاجر نفسه على نسخةٍ مستعادة، لا بالملفّات الثلاثة وحدها.

## ٢. الشروط الأربعة

### ٢.١ نسخة احتياطيّة مُثبتة باختبار استعادة

- نسخةٌ من قاعدة staging، ثمّ **استعادتها إلى قاعدةٍ منفصلة** تُقارن بالأصل: عدد الجداول والأعمدة (`probe_schema_state.sh`)، والقيود والفهارس والسياسات (§٢.٢)، وعدد صفوف الجداول التي تمسّها الدفعة.
- **لا نسخة بلا استعادةٍ ناجحة.** وتُسجَّل هويّة النسخة (الوقت والحجم والبصمة) في دليل القبول.

### ٢.٢ فحصٌ حيّ أوسع من الجداول والأعمدة

`migrations/probe_schema_state.sh` يقرأ وجود الجداول والأعمدة **فقط**، ويصرّح بذلك. ويُضاف إليه، **قراءةً فقط وباتّصال التطبيق** حيث يلزم:

```sql
BEGIN READ ONLY;
-- القيود على الجداول التي تمسّها الدفعة
SELECT conrelid::regclass, conname, contype, convalidated, pg_get_constraintdef(oid)
  FROM pg_constraint
 WHERE conrelid IN ('online_learning_updates'::regclass, 'decision_record'::regclass,
                    'dispatch_decisions'::regclass, 'execution_ledger'::regclass,
                    'as_applied_irrigation_runs'::regclass, 'as_applied_irrigation_receipts'::regclass)
 ORDER BY 1, 2;
-- الفهارس
SELECT tablename, indexname, indexdef FROM pg_indexes
 WHERE schemaname = 'public' AND tablename IN ('online_learning_updates','decision_record','dispatch_decisions',
       'execution_ledger','as_applied_irrigation_runs','as_applied_irrigation_receipts') ORDER BY 1, 2;
-- RLS وFORCE والمالك والسياسات
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner)
  FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
   AND c.relname IN ('online_learning_updates','decision_record','dispatch_decisions','execution_ledger',
                     'as_applied_irrigation_runs','as_applied_irrigation_receipts','commands');
SELECT polrelid::regclass, polname, polcmd, pg_get_expr(polqual, polrelid), pg_get_expr(polwithcheck, polrelid)
  FROM pg_policy ORDER BY 1, 2;
-- الأدوار
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname NOT LIKE 'pg\_%' ORDER BY 1;
-- أحجام الجداول (لتقدير زمن الأقفال)
SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid))
  FROM pg_stat_user_tables WHERE relname IN ('online_learning_updates','decision_record','dispatch_decisions',
       'execution_ledger','as_applied_irrigation_runs','as_applied_irrigation_receipts');
ROLLBACK;
```

### ٢.٣ تجربة الترقية على النسخة المستعادة

1. **المُهاجر نفسه** على النسخة المستعادة (`SAHOOL_MIGRATE_APPLY=1` هناك فقط، لا في Railway)، مع تسجيل زمن كلّ ملفّ.
2. **قياس الأقفال** أثناء التجربة: `pg_locks` المنضمّ إلى `pg_stat_activity` كلّ ثانية، لرصد مدّة `ACCESS EXCLUSIVE` على `online_learning_updates` ومدّة `SHARE` على الجداول الخمسة، مع حِملٍ كتابيّ تجريبيّ يُقاس انتظاره.
3. **بعدها:** `probe_schema_state.sh` ⇒ `status=PASS`، وفحص §٢.٢ مقارنةً بما قبله: القيدان `convalidated=true`، والفهارس الخمسة موجودة، وRLS والسياسات لم تتغيّر.
4. **توافق نسخة التطبيق السابقة مع المخطّط الجديد:** تشغيل الـSHA العامل في staging حالياً (`d6ddf38ce`) على النسخة المرقّاة، ثمّ **كلّ** مسارات الكتابة التي تمسّ الجداول الستّة: إدراجاً وتحديثاً. المتوقَّع في v234 أن تعمل، لأنّ القيم الافتراضيّة `'unreviewed'`/`false` تحقّق `chk_oluj_agronomic_approval_consistency`. **والمتوقَّع في v235 غير مضمون:** مشغّلات التحديث ترفض تغيير `tenant_id` ومفتاح الأب، والبحث الثابت في كود `d6ddf38ce` و`fa92a1f7e`، دون الاختبارات، وجد ثلاث عبارات `UPDATE` على الجداول الخمسة. لا تغيّر أيٌّ منها عموداً محميّاً:
   - `services/sahool-platform/api/routers/decision_dispatch.py:476` و`:646`: `SET exec_status`.
   - `services/decision-service/persistence.py:640`: `SET review_state`.

   وهذا دليلٌ ثابت لا إثبات، لأنّ SQL المبنيّ ديناميكيّاً أو الموزّع على أسطر قد يفلت من البحث. **يُقاس على النسخة المرقّاة ولا يُفترض.**

### ٢.٤ إجراء التعافي من فشلٍ جزئيّ

| موضع الفشل | الحالة بعده | التعافي |
|---|---|---|
| داخل v234 أو v236 | المعاملة ترتدّ، والملفّ لم يُطبَّق أصلاً | يُصلَح السبب ثمّ يُعاد المُهاجر. ما سبق الملفّ في MANIFEST idempotent |
| داخل v235 | **جزئيّ:** ما سبق العبارة الفاشلة باقٍ (أعمدةٌ أو فهارس) | يُعاد المُهاجر بعد إصلاح السبب: كلّ عبارات v235 `IF NOT EXISTS` أو `CREATE OR REPLACE` أو `DROP TRIGGER IF EXISTS` ثمّ `CREATE TRIGGER`، فيُكمل الباقي. ولا تراجع يدويّ إلّا لسببٍ يمنع الإكمال، ويُختبر على النسخة المستعادة أوّلاً |
| `CREATE INDEX` يفشل في منتصفه | **غير متوقَّع أن يبقى فهرسٌ غير صالح:** البناء غير المتزامن يرتدّ كلّه، و`INVALID` يخصّ `CONCURRENTLY` | يُتحقَّق بـ`SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid` قبل الإعادة وبعدها |
| فشلٌ بعد الهجرات (منح الأدوار) | الهجرات مطبّقة والمنح ناقصة | يُعاد المُهاجر (المنح idempotent)، ويُفحص `has_table_privilege` لدور التطبيق |
| فشلٌ لا يُصلَح بالإعادة | — | **الاستعادة من النسخة المُثبتة في §٢.١**، وإعادة نشر نشر التطبيق السابق |

**ملفّا التراجع `.down.sql` ليسا جزءاً من هذا الإجراء:** لا يعكسان هذه الدفعة، وتشغيلهما يمسّ حماية RLS وappend-only (§٣). فهما ليسا شرطاً لترقية v234–v236، ما لم تعتمد خطة الاستعادة عليهما، وهي لا تعتمد.

## ٣. ملفّا التراجع القديمان

236 ملفّ SQL = 234 هجرةً أماميّة في MANIFEST + ملفّا تراجع مستثنيان صراحةً بلاحقة `.down.sql`: `scripts/ci/database_contract_graph.py:77` (يعتمد عليه `migration_graph_guard`)، و`migrations/validate_migrations.py:95-97`، و`tests_v9/test_manifest_completeness.py`.

| الملفّ | آخر تعديل له | آخر تعديل للهجرة الأماميّة | يشغّله شيء؟ |
|---|---|---|---|
| `v9_append_only_enforcement.down.sql` | `6dce82bab` 2026-06-09 | `6dce82bab` 2026-06-09 | لا (لا workflow ولا سكربت ولا اختبار) |
| `v9_rls_tenant_isolation.down.sql` | `6dce82bab` 2026-06-09 | `e28d7bab6` 2026-06-17 (تعديلان بعده) | لا |

سُجِّلا فجوةً: `MIGRATION-DOWN-SCRIPTS-UNTESTED-POSSIBLY-STALE-01`. **واختلاف تاريخ التعديل مؤشّرٌ يستدعي الفحص، لا إثباتٌ لخلل.**

## ٤. حالة الشروط

| الشرط | الحالة |
|---|---|
| ٢.١ نسخة + اختبار استعادة | NOT_RUN |
| ٢.٢ الفحص الحيّ | NOT_RUN. العائق وصول: لا اتّصال لي بقاعدة staging |
| ٢.٣ التجربة والأقفال والتوافق | NOT_RUN. يحتاج النسخة المستعادة |
| ٢.٤ إجراء التعافي | مكتوب هنا، ولم يُجرَّب |
| تطبيق الدفعة على staging | خارج المرحلة (التجميد قائم) |
