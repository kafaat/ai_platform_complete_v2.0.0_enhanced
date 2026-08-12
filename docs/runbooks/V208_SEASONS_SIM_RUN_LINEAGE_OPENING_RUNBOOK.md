# دليل فتح `v208` — نَسَبُ إسقاط `seasons.sim_*` إلى سجلّ التشغيل

`HISTORICAL-SEASON-COMPOSITION-02` · `migrations/v208_seasons_sim_run_lineage.sql`

## ما تفعله هذه المِهجرة بالضبط

سطرٌ واحد من DDL، ولا شيء غيره:

```sql
ALTER TABLE seasons
    ADD COLUMN IF NOT EXISTS sim_run_id UUID;
```

عمودٌ **قابل للإفراغ** (`nullable`) · **بلا قيمة افتراضيّة** · **بلا مفتاح أجنبيّ** ·
**بلا فهرس**. ومعه `COMMENT ON COLUMN` فقط.

**والقيمةُ التي يشتريها:** `seasons.sim_*` هو أحدث إسقاطٍ تشغيليّ، وكان لا يحمل
`run_id` الذي أنتجه — فلا سبيل إلى الجزم أيُّ تشغيلٍ أنتج القيم الظاهرة. بعد
`v208` يصير الإسقاط منسوباً إلى `season_simulation_runs` (‏`v207`).

---

## ٠) الحقائق المقيسة قبل أيّ خطوة

قِيست كلّها على الشجرة قبل كتابة هذا الدليل، لا مأخوذة من ذاكرة:

| ما هو | القياس |
|---|---|
| موضع `v208` في `MANIFEST.txt` | المُدخَل **٢١٣** من ٢٢٦ |
| ترتيبُه مقصود | **يسبق `v206` عمداً** كي يبقى `v206` (تأكيد catalog RLS النهائيّ) آخِرَ ملفٍّ مطبَّق |
| الكاتب في الشيفرة | `services/sahool-platform/api/routers/seasons.py:403` |
| أهو داخل معاملة واحدة | **نعم** — `async with conn.transaction():` تضمّ `INSERT INTO season_simulation_runs` ثمّ `UPDATE seasons … sim_run_id = $8` |
| الحارس الساكن | `tests_v9/test_historical_season_bridge_static.py` — يفرض وجود العمود **وترتيبَ** الإدراج قبل التحديث |
| ملفّ تراجع `.down.sql` | **غير موجود** |
| مالك المِهجرات | `sahool_user` — `migrations/POSTGRES_SETUP.md:47` (وأكّده تدقيقُ قاعدةٍ حيّة 2026-08-12) |

---

## ١) ثلاثة حدود صدقٍ تُقرأ قبل التنفيذ لا بعده

### ١أ) `migrate.py up` **لا يُطبِّق `v208` وحده**

`cmd_up` يحسب `pending = [m for m in MIGRATION_ORDER if m not in applied]` ثمّ
يطبّقها **كلّها بالترتيب**. فلا يوجد في الأداة أمرٌ يقول «طبّق هذه المِهجرة فقط».

⇒ إن كان لديك مِهجراتٌ معلّقة أخرى، فـ`up` يفتحها معها. **اقرأ `status` أوّلاً
واعرف ما ستفتحه فعلاً.**

### ١ب) لا تراجعَ آليّ

`cmd_down` يبحث عن `v208_seasons_sim_run_lineage.down.sql` ولا يجده، فيقول
حرفيّاً: «لا يوجد تراجع وهميّ» ويخرج بـ`1`. والتراجع اليدويّ
(`ALTER TABLE seasons DROP COLUMN sim_run_id`) **يُتلِف نَسَبَ كلّ صفٍّ كُتِب بعد
الفتح** — لا يستعيد حالةً بل يمحو معرفة.

⇒ عمليّاً: هذه المِهجرة **تُفتَح ولا تُغلَق**. وهي آمنةٌ لذلك (عمودٌ `nullable`
مضاف)، لكنّ القرار يُتّخذ على هذا الأساس لا على افتراض وجود مخرج.

### ١ج) نافذةُ «مُطبَّقٌ وغير مُسجَّل»

التطبيق والتسجيل **نداءان منفصلان** لـ`psql`:

```python
_psql(url, file=path)                                  # ← الـDDL
_psql(url, "INSERT INTO schema_migrations(...) ...")   # ← التسجيل
```

فانقطاعٌ بينهما يترك العمود مُضافاً و`schema_migrations` لا تعرفه. والأثر عند
التشغيل التالي **محدود هنا** لأنّ `IF NOT EXISTS` تجعل إعادة التطبيق بلا ضرر —
لكنّ `status` سيقول «غير مُطبَّق» عن عمودٍ موجود. تُعالَج بالخطوة ٦.

---

## ٢) الشروط المسبقة

### الدور — وهنا فخٌّ وقعتُ فيه، فيُقال صريحاً

**استعمل `sahool_user`** — لا `sahool_jobs`:

```bash
export DATABASE_URL='postgresql://sahool_user:PASS@HOST/sahool'
```

**ولماذا هذا التحديد يهمّ:** `ALTER TABLE` يشترط **ملكيّة الجدول**، لا صلاحيّةَ
كتابةٍ فيه. والمرجع القانونيّ لنموذج الأدوار
(`migrations/POSTGRES_SETUP.md:47`) يقول: «**مالك الهجرات** (`sahool_user`،
superuser في صورة postgres الرسميّة)». فدورٌ غير مالكٍ يُنتِج
`must be owner of table seasons` مهما بلغت صلاحيّاته على البيانات.

**وتعليقُ `scripts_v9/migrate.py:57` يذكر `sahool_jobs`** — وهو يصف **مسار النشر
في k8s** (‏`migration-job.yaml` يمرّر `JOBS_DATABASE_URL`)، لا مالكَ المِهجرات في
التشغيل اليدويّ. وأوّل صياغةٍ لهذا الدليل أخذت التعليق مرجعاً للأدوار فأوصت
بالدور الخطأ — أصلحه تدقيقُ قاعدةٍ حيّة أظهر أنّ `sahool_user` هو المالك.
**والدرس المُعمَّم: تعليقٌ في أداةٍ يصف سياق استدعائها، لا يُعرِّف نموذج الأدوار.**

**وحدُّ صدقٍ على المسار الآليّ:** إن كان النشر في بيئتك يشغّل `migrate.py` بدور
`sahool_jobs` فهو يعمل هناك بترتيبٍ يمنحه ما يلزم؛ وهذا الدليل يصف **التشغيل
اليدويّ المباشر**، وفيه المالك هو `sahool_user`.

الأداة تقبل `DATABASE_URL` أو `MIGRATE_DB_URL` أو `JOBS_DATABASE_URL` بهذا
الترتيب. **لا تضع كلمة المرور في سطر أوامر مشترك ولا في سجلّ** — استعمل
`~/.pgpass` أو متغيّر بيئةٍ من خزنة الأسرار.

**وتحقّق من `v207` أوّلاً**، فـ`v208` يعتمد عليه **دلاليّاً لا بنيويّاً**: لا مفتاح
أجنبيّ يربط `sim_run_id` بـ`season_simulation_runs`، فالمِهجرة **ستنجح** حتّى لو
غاب الجدول — وينتج عمودٌ يشير إلى لا شيء.

```sql
SELECT to_regclass('public.season_simulation_runs') IS NOT NULL AS v207_present;
```

يجب أن تكون `t`. وإن كانت `f` فتوقّف: افتح `v207` قبله.

---

## ٣) القياس قبل الفتح

```bash
python3 scripts_v9/migrate.py status | tail -5
python3 scripts_v9/migrate.py up --dry-run
```

`--dry-run` يطبع **كلّ** ما سيُطبَّق. اقرأ القائمة كاملةً: إن ظهر فيها غير
`v208` فأنت تفتح أكثر ممّا طلبت (حدّ ١أ).

وتأكّد أنّ العمود غير موجود سلفاً:

```sql
SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_name = 'seasons' AND column_name = 'sim_run_id';
```

صفرُ صفوفٍ ⇒ لم يُفتَح بعد.

---

## ٤) الفتح

### ٤أ) المسار المُعتمَد — عبر الأداة

يُستعمَل حين تكون `v208` هي المِهجرة المعلّقة الوحيدة (تأكّد بـ٣):

```bash
python3 scripts_v9/migrate.py up
```

### ٤ب) المسار المُستهدَف — `v208` وحدها

يُستعمَل حين توجد مِهجراتٌ معلّقة أخرى لا تريد فتحها الآن. **يُطبَّق ويُسجَّل
بيده**، فانتبه للخطوة ٦:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -c "SET lock_timeout = '5s';" \
  -f migrations/v208_seasons_sim_run_lineage.sql
```

**ولماذا `lock_timeout` وليس بلا:** `ADD COLUMN` القابل للإفراغ وبلا قيمة
افتراضيّة **لا يُعيد كتابة الجدول** في PostgreSQL ‏11+ — لكنّه يظلّ يطلب
`ACCESS EXCLUSIVE` للحظة. فإن كانت معاملةٌ طويلة تقرأ `seasons`، اصطفّ الـALTER
خلفها **واصطفّ خلفه كلُّ قارئٍ جديد** — فيتحوّل تعديلٌ لحظيّ إلى توقّفٍ عامّ.
والمهلة تجعل الفشل «لم يُفتَح» بدل «تجمّدت القراءات».

فإن انتهت المهلة: ابحث عن المعاملة الطويلة وأعِد المحاولة في نافذةٍ أهدأ.

```sql
SELECT pid, state, now() - xact_start AS age, left(query, 80)
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL AND now() - xact_start > interval '30 s'
 ORDER BY age DESC;
```

---

## ٥) التحقّق بعد الفتح

**العمود موجود وبالخصائص المُعلَنة:**

```sql
SELECT data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_name = 'seasons' AND column_name = 'sim_run_id';
```

المتوقَّع: `uuid` · `YES` · `NULL`. وأيُّ خلافٍ لذلك يعني أنّ ما طُبِّق ليس هذه
المِهجرة.

**والتعليق مكتوب** (وهو ما يجعل العمود قابلاً للقراءة بعد سنة):

```sql
SELECT col_description('public.seasons'::regclass,
         (SELECT ordinal_position FROM information_schema.columns
           WHERE table_name='seasons' AND column_name='sim_run_id')) IS NOT NULL AS has_comment;
```

**والحارس الساكن أخضر:**

```bash
pytest tests_v9/test_historical_season_bridge_static.py -q
```

---

## ٦) التسجيل — الخطوة التي تُنسى

إن فتحتَ بالمسار ٤ب، فـ`schema_migrations` لا تعرف شيئاً. سجّلها بالبصمة نفسها
التي تحسبها الأداة (‏`sha256` مقطوعةً عند ١٦ محرفاً):

```bash
CK=$(python3 -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('migrations/v208_seasons_sim_run_lineage.sql').read_bytes()).hexdigest()[:16])")
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "INSERT INTO schema_migrations(version, checksum)
   VALUES ('v208_seasons_sim_run_lineage.sql', '$CK')
   ON CONFLICT (version) DO NOTHING;"
```

ثمّ `python3 scripts_v9/migrate.py status | grep v208` ⇒ يجب أن يقول `✓ مُطبَّق`
**بلا** «⚠ انجراف checksum». والانجراف يعني أنّ الملفّ تغيّر بعد تطبيقه — وهو
تحقيقٌ مستقلّ لا يُتجاوَز بإعادة التسجيل.

---

## ٧) التحقّق التشغيليّ — أنّ النَّسَب يُكتَب فعلاً

فتحُ العمود لا يعني أنّ أحداً يملؤه. والفرق بينهما هو الفرق بين «مُتاح» و«يعمل».

شغّل محاكاةَ موسمٍ واحدة عبر المسار الطبيعيّ، ثمّ:

```sql
SELECT s.season_id, s.sim_ran_at, s.sim_run_id,
       r.run_id IS NOT NULL AS lineage_resolves
  FROM seasons s
  LEFT JOIN season_simulation_runs r ON r.run_id = s.sim_run_id
 WHERE s.sim_ran_at IS NOT NULL
 ORDER BY s.sim_ran_at DESC
 LIMIT 5;
```

**المتوقَّع للصفوف المكتوبة بعد الفتح:** `sim_run_id` غير فارغ و`lineage_resolves = t`.

**والصفوف الأقدم من الفتح تبقى `NULL` — وهذا صحيح لا عطل:** المِهجرة لا تملأ
بأثرٍ رجعيّ، ولا سبيل إلى ذلك أصلاً لأنّ التشغيل الذي أنتجها لم يُسجَّل. وأيُّ
«ملءٍ رجعيّ» بتخمينٍ يُنتِج نَسَباً كاذباً — وهو أسوأ من `NULL` صادق.

**ولا يفرض شيءٌ في قاعدة البيانات صحّة هذه الإشارة:** لا مفتاح أجنبيّ. فالسلامة
مضمونةٌ بالمعاملة في الشيفرة (الإدراج ثمّ التحديث في `conn.transaction()` واحدة)
وبالحارس الساكن — لا بالمخطَّط. ومن يكتب في `seasons` من خارج ذلك المسار يستطيع
وضع UUID لا يقابله صفّ.

---

## ٨) ماذا لو فشل الفتح

| العَرَض | التشخيص | العلاج |
|---|---|---|
| `canceling statement due to lock_timeout` | معاملةٌ طويلة تحتجز `seasons` | استعلام §٤ب، ثمّ أعِد في نافذةٍ أهدأ |
| `must be owner of table seasons` | الدور ليس **مالك** الجدول — و`ALTER` يشترط الملكيّة لا صلاحيّة الكتابة | استعمل `sahool_user` (§٢) — **لا تُرقِّ دوراً آخر ولا تنقل الملكيّة** |
| `permission denied for table seasons` | لا صلاحيّة أصلاً على الجدول | صحّح `DATABASE_URL` |
| `status` يقول «غير مُطبَّق» والعمود موجود | نافذة حدّ ١ج | §٦ (‏`ON CONFLICT DO NOTHING` تجعلها آمنة) |
| «⚠ انجراف checksum» | الملفّ تغيّر بعد تطبيقه | **توقّف** — قارِن بالمستودع قبل أيّ شيء |
| `v207_present = f` | المِهجرة السابقة غير مفتوحة | افتح `v207` أوّلاً |

---

## ٩) ما لا يفعله هذا الدليل

- **لا يفتح `v206`.** ترتيب `MANIFEST` يجعل `v206` آخِرَ مدخل عمداً؛ وإن فتحتَ
  المِهجرات كلّها بـ`up` فسيُفتَح معها — وهو خارج نطاق هذا الدليل.
- **لا يعد بتراجع.** حدّ ١ب.
- **لا يشهد على بيئةٍ حيّة.** كلّ ما فيه مشتقٌّ من الشجرة: المِهجرة، الأداة،
  الكاتب، الحارس. ولم يُنفَّذ شيءٌ منه على قاعدةٍ حيّة أثناء كتابته — والتحقّق في
  §٥ و§٧ هو ما يُنتِج الشهادة، لا هذا النصّ.
