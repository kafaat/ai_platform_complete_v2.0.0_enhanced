# شهادة PostgreSQL الحيّة — Runbook قابل للنسخ

**ما يملؤه هذا الدليل:** وصفةُ وظيفة CI *Live PG Proofs* لتُشغَّل محلّيّاً — وهي غيرُ موصوفةٍ في أيّ
runbook قائم. قِيس ذلك قبل كتابته: `postgis/postgis:16-3.4` و`apply_migration_manifest.sh`
و`RLS_ISOLATION_CERTIFICATION_REQUIRED` و`HIL_CERTIFICATION_REQUIRED` و`run_hil_drawing_pg.sh`
والمنفذ `5435` — **صفرُ ورودٍ** في `docs/runbooks/*.md` قبل هذا الملفّ.

**وما لا يكرّره** (اذهب إليها، فهي المرجع):

| الحاجة | المرجع |
|---|---|
| إقلاع المكدّس مرحليّاً و`.env` وأسرارُه | [`LOCAL_ENVIRONMENT_RUNBOOK.md`](LOCAL_ENVIRONMENT_RUNBOOK.md) |
| معايير القبول الحيّة وإغلاق الفجوات على الخادم | [`LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md`](LIVE_GAP_CLOSURE_AGENT_RUNBOOK.md) |
| سُلَّم البوّابات قبل الدفع | [`CI_GATES_AND_PRE_PUSH_PROTOCOL.md`](CI_GATES_AND_PRE_PUSH_PROTOCOL.md) |
| ما يفرضه كلُّ حارس وأين يحجب | [`GUARD_CATALOGUE.md`](GUARD_CATALOGUE.md) |

**مصدر الوصفة:** `.github/workflows/ci.yml` — وظيفة *Live PG Proofs*، منقولةٌ حرفيّاً لا معادةَ
صياغة. فما يمرّ هنا يمرّ هناك بالسبب نفسِه.

---

## ⚠ حدُّ صدقٍ يسبق كلّ أمر

| الكتلة | الحالة |
|---|---|
| (أ) البيئة المعزولة | **مقيسة**: `fastapi 0.136.3` من `tests_v9/requirements-test.txt` |
| (ب) شهادة PostgreSQL | **منقولةٌ من `ci.yml` ولم تُنفَّذ** في بيئة كتابتها — لا Docker ولا PostGIS هناك |
| (ج) مِرقاة المستودع | **لم تُنفَّذ** — تشترط Docker |

قاعدةٌ حاكمة: **«لم يُقَس» لا تُكتب «مرّ».** وعلمٌ من أعلام `*_CERTIFICATION_REQUIRED` غيرُ مضبوطٍ
يعني أنّ الاختبار **تخطّى** ولم ينجح.

---

## ٠) إحاطة الوكيل المحلّيّ

```
أنت تعمل على مستودع sahool على main. اقرأ CLAUDE.md أوّلاً، والتزم:

• لا تدفع قبل: bash scripts/ci/preflight.sh
• سلسلة §3.16 بالترتيب، والحزمة تُبنى آخِراً، وgit add -A قبل كلّ إعادة توليد
• لا تحذف اختباراً ولا تُعطّله ولا ترفع حدّاً لتخضير CI
• لا تُعدّل services/*/phase_runtime_workers.py
• لا تُعدّل .github/workflows/ci.yml لتجاوز بوّابة
• كلّ حارس جديد يلزمه تكذيبٌ بالطفرة:
  python3 scripts/ci/guard_mutation_guard.py --run --only <path>
• طفرةٌ تُسمّي اختباراً يمكن تخطّيه = صمتٌ لا تكذيب (STABLE_WRONG_TEST)
• «لم يُقَس» لا تُكتب «مرّ». أعلِن ما تخطّيته صراحةً.
```

---

## أ) البيئة المعزولة

إصدارُ FastAPI مثبَّت: أيُّ إصدارٍ آخر يُسقط بوّابة اختبارات المنصّة بتعارض التثبيت.

```bash
cd /path/to/ai_platform_complete_v2.0.0_enhanced
git fetch origin && git checkout -B live-evidence origin/main

python3 -m venv .venv-proof
.venv-proof/bin/pip install -q -r tests_v9/requirements-test.txt
.venv-proof/bin/python -c "import fastapi, asyncpg, pytest; print('fastapi', fastapi.__version__)"
# المتوقّع: fastapi 0.136.3
```

---

## ب) الشهادة الحيّة

### ب-١ · القاعدة

PostGIS **إلزاميّ**: `migrations/v9_foundation.sql` ينشئ `postgis` و`pgcrypto` و`uuid-ossp`.
قاعدةٌ عاديّة تُسقط تطبيق الهجرات من أوّله.

```bash
docker run -d --name sahool-pg16 \
  -e POSTGRES_DB=sahool -e POSTGRES_USER=sahool_user -e POSTGRES_PASSWORD=test_password \
  -p 5435:5432 postgis/postgis:16-3.4

for i in $(seq 1 30); do pg_isready -h localhost -p 5435 -U sahool_user && break; sleep 2; done
```

### ب-٢ · الهجرات — ومرّتين عمداً

```bash
export PGPASSWORD=test_password

bash scripts/ci/apply_migration_manifest.sh --port 5435 --user sahool_user --db sahool

# إعادةُ التطبيق تُثبت الـidempotency
bash scripts/ci/apply_migration_manifest.sh --port 5435 --user sahool_user --db sahool
```

### ب-٣ · دور التطبيق المقيَّد

بدون `NOSUPERUSER NOBYPASSRLS` **لا يُفرَض RLS أصلاً** — المالكُ والسوبر يتجاوزانه حتّى مع `FORCE`.
فأيُّ «إثبات عزل» تحت المالك إثباتُ لا شيء.

```bash
psql -h localhost -p 5435 -U sahool_user -d sahool -v ON_ERROR_STOP=1 -c "
  create role sahool_app login password 'test_password'
    nosuperuser nobypassrls nocreatedb nocreaterole;
  grant usage on schema public to sahool_app;
  grant select, insert, update, delete on all tables in schema public to sahool_app;
  grant usage, select on all sequences in schema public to sahool_app;"
```

### ب-٤ · البراهين — والغيابُ فشلٌ لا تخطٍّ

```bash
export PGHOST=localhost PGPORT=5435 PGPASSWORD=test_password
export SAHOOL_TEST_PGHOST=localhost SAHOOL_TEST_PGPORT=5435
export SAHOOL_TEST_PGDATABASE=sahool SAHOOL_TEST_PGOWNER=sahool_user SAHOOL_TEST_PGROLE=sahool_app
export SAHOOL_REQUIRE_LIVE_PG=1

# العقد المخطّطيّ يُقاس قبل أيّ اختبار
.venv-proof/bin/python scripts/ci/live_pg_evidence_guard.py --schema-only

.venv-proof/bin/python -m pytest tests_v9/test_live_pg_fake_connection_debt.py -v --tb=short \
  -p no:cacheprovider -o addopts= --junitxml=live_pg_evidence.xml

.venv-proof/bin/python scripts/ci/live_pg_evidence_guard.py \
  --junit live_pg_evidence.xml --min-executed 30 --evidence live_pg_evidence.json
```

`live_pg_evidence.json` هو **الشاهد**؛ وبدونه لا تُدَّعى الشهادة.

### ب-٥ · عزل المستأجرين والمراجعة البشريّة

الأعلامُ تُحوّل التخطّي الصامت إلى فشلٍ معلن — وهي جوهرُ هذه الكتلة:

```bash
export TEST_DATABASE_ADMIN_URL="postgresql://sahool_user:test_password@localhost:5435/sahool"
export TEST_DATABASE_URL="postgresql://sahool_app:test_password@localhost:5435/sahool"
export RLS_ISOLATION_CERTIFICATION_REQUIRED=1
export HIL_CERTIFICATION_REQUIRED=1

.venv-proof/bin/python -m pytest \
  tests_v9/test_rls_tenant_isolation_live_pg.py \
  tests_v9/test_db_wiring.py \
  tests_v9/test_live_pg_role_closure_guard.py -v --tb=short
```

### ب-٦ · التنظيف

```bash
docker rm -f sahool-pg16
```

---

## ج) مِرقاة المستودع الجاهزة — بديلٌ أقصر للكتلة (ب)

```bash
bash docs/testing/run_hil_drawing_pg.sh "$PWD" "$PWD/.venv-proof/bin/python"
```

تُنشئ قاعدةً مؤقّتة على المنفذ `65432`، تُطبّق الهجرات مرّتين، تُشغّل شاهدَي HIL والرسم،
وتحذف **حاويتها وحدَها** عند الخروج.

---

## د) نموذج التقرير

لكلّ كتلة:

```
الكتلة  : ب-٤ براهين الدليل الحيّ
الأمر   : <الأمر حرفيّاً>
المخرَج : <آخر ١٠ أسطر حرفيّاً>
الحكم   : نجح / أخفق / لم يُقَس
الشاهد  : live_pg_evidence.json (إن وُجد)
```

وفي الخلاصة أعلِن صراحةً:

- ما **لم يُقَس** ولماذا (صورةٌ ناقصة · منفذٌ مشغول · سرٌّ غائب…).
- ما **تخطّى** بدل أن يفشل — وهو دليلٌ على علمٍ غير مضبوط، لا على نجاح.
- أنّ خضرة CI **ليست** شهادة تشغيل: `runtime_verified` و`production_certified` يبقيان `0`
  حتّى يوجد شاهدٌ حيّ مُودَع.

---

## هـ) ما يُغلقه هذا الدليل — وما لا يُغلقه

| البند | الكتلة |
|---|---|
| تطبيق الهجرات وإعادتها | ب-٢ |
| `FORCE RLS` تحت دورٍ مقيَّد | ب-٣ · ب-٥ |
| القراءة/الكتابة/الموافقة بدور التطبيق | ب-٥ |
| إعادة استخدام الاتّصال بين مستأجرين | ب-٥ |
| شاهدا HIL والرسم | ج |

**ولا يُغلق:** الأدلّةَ الماليّة والمائيّة القانونيّة (`season_water_used_m3_ha` · الإيراد والتكلفة
السنويّان · الاحتياطي النقديّ · كفاءة الريّ). تلك عقودُ بياناتٍ ناقصة لا تُغلقها بيئةٌ حيّة —
والحوكمةُ تحجب لنقص السياق، وهو سلوكٌ صحيح يُبقي **مصدرَ** الدليل عملاً مطلوباً.
