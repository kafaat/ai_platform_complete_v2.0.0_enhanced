# رنبوك التحقّق المحلّيّ — رفع تجميد GATE-01 على جهازك أوّلاً

**الغرض:** أن تتحقّق بنفسك على جهازك، قبل أيّ قيدٍ أو دمجٍ أو نشر، من منطق الأعمال المجمَّدة ومن
أنّها تعمل. ثمّ تُعيد إليّ ملفّ النتائج (§٩).

**الفرع:** `claude/local-unfreeze-rehearsal-20261102`، مبنيٌّ على `main@210f63827`.
**وهذا الفرع لا يُدمَج.** هو فرع تجربة فقط، وحارس GATE-01 على هذا الفرع **يحمرّ عمداً** (§١٠).

---

## ٠) حدود السلامة — اقرأها قبل أيّ أمر

| لا يلمس | كيف ذلك مضمون |
|---|---|
| Railway وPostgreSQL الإنتاج وstaging | السكربت يرفض أيّ `PGHOST` ليس loopback، ويخرج بالرمز 2 |
| `SAHOOL_MIGRATE_APPLY` | السكربت يرفض العمل إن وجده مضبوطاً `=1` في الصدفة |
| `main` | هذا فرع `claude/*`، وRailway يبني من `main` و`deploy/*` فقط (`docs/architecture/railway_watch_patterns.json`) |
| بياناتٌ حقيقيّة | كلّ البيانات مُركَّبة. القواعد `rehearsal_*` تُنشأ وتُحذف على حاويتك المحلّيّة وحدها |

---

## ١) ما يحمله الفرع (أربع حزم مجمَّدة)

| الحزمة | المصدر | ماذا تُصلح |
|---|---|---|
| **v237 + T3** | `claude/audit-draft-isolation-migrations-on-main-20261101` | T1: الـVIEWs تُقرأ بصلاحيّة القارئ (`security_invoker`). T2: كتابةٌ لمستأجرٍ آخر بلا سياق تُرفض. T7: صفوف `tenant_id IS NULL` وتفضيلات المستخدمين الآخرين تُحجب. T8: رموز الدعوات لا تظهر بلا سياق. T9: `CHECK (btrim(tenant_id) <> '') NOT VALID`. T3: سحب `EXECUTE` من دوالّ DEFINER الخاصّة بالإدخال |
| **Actuator A1–A8** | `claude/audit-draft-actuator-safety-on-main-20261101` | بوّابة تشغيل القواعد، ونطاق موثَّق من السجلّ، ومفردات السلك، وإعادة نشرٍ مستقرّة. الـfirmware: حجم الأمر والمدّة وQoS1. ترحيل JetStream بـack صريح. قالب ACL لـMQTT (غير مُفعَّل) |
| **S5** | `claude/audit-s5-token-revocation-20261101` | إبطال JWT الذي يصدره auth يُحترَم في guardrails وsupervisor وnotification وكلّ خوادم MCP |
| **GUC داخل المعاملة** (جديد هنا) | `phase_runtime_store.py` و`phase_runtime_workers.py` | `set_config(…, true)` كان يُستدعى خارج أيّ معاملة فيضيع قبل الكتابة، فيرفضها `FORCE RLS` تحت الدور المقيَّد. الحلّ: معاملةٌ حول كلّ كتابة. والاختبار الذي كان `xfail(strict)` صار ينجح |

ودمج S5 فوق `main` احتاج إصلاحين:
- **تعارضان نصّيّان** (`market_server.py` و`oauth_middleware.py`) حُلّا اتّحاداً: `require_tenant` ثمّ `require_not_revoked`.
- **تعارضٌ دلاليّ واحد:** اختبار `test_jwt_revocation_same_redis.py` على `main` يرفض أيّ دليلٍ غير مصنَّف يذكر مفتاح الإبطال، فصُنِّف `shared/` مكتبةً، وعقد مستهلكيها في اختبارات S5.

---

## ٢) المتطلّبات

```bash
docker --version                 # أيّ إصدار حديث
psql --version; pg_dump --version   # 16.x أو أحدث (pg_dump يجب ألّا يكون أقدم من الخادم)
python3 --version                # 3.12 موصى به
git --version
```

إن لم يكن `psql`/`pg_dump` موجوداً:
- Ubuntu/Debian: `sudo apt-get install -y postgresql-client-16`
- macOS: `brew install libpq && brew link --force libpq`

---

## ٣) جلب الفرع والتأكّد من هويّته

```bash
cd /path/to/ai_platform_complete_v2.0.0_enhanced
git fetch origin claude/local-unfreeze-rehearsal-20261102
git switch -C local-unfreeze origin/claude/local-unfreeze-rehearsal-20261102
git rev-parse HEAD                       # طابِقه بالـSHA الذي أرسلتُه لك
git status --short                       # يجب أن يكون فارغاً
git log --oneline -1 210f63827           # القاعدة: docs(brain): register the paused SoilGrids REST …
```

---

## ٤) قاعدة PostgreSQL 16 + PostGIS محلّيّة (منفذ 5439)

```bash
docker rm -f sahool-unfreeze-pg 2>/dev/null
docker run -d --name sahool-unfreeze-pg \
  -e POSTGRES_USER=sahool_test -e POSTGRES_PASSWORD=test_password -e POSTGRES_DB=postgres \
  -p 127.0.0.1:5439:5432 postgis/postgis:16-3.4

for i in $(seq 1 30); do pg_isready -h localhost -p 5439 -U sahool_test && break; sleep 2; done
export PGHOST=localhost PGPORT=5439 PGUSER=sahool_test PGPASSWORD=test_password
psql -d postgres -Atc "SHOW server_version_num"        # المتوقّع: 1600xx
unset SAHOOL_MIGRATE_APPLY
```

---

## ٥) بيئة بايثون معزولة

```bash
python3 -m venv .venv-unfreeze
. .venv-unfreeze/bin/activate
pip install -q -r tests_v9/requirements-test.txt
python -c "import asyncpg, pytest, pytest_asyncio, fastapi; print('ok', fastapi.__version__)"
```

---

## ٦) التجربة الكاملة للهجرات — أمرٌ واحد

```bash
OUT="$PWD/.local-rehearsal/run-$(date -u +%Y%m%dT%H%M%SZ)" \
  bash docs/runbooks/local_unfreeze/unfreeze_local_rehearsal.sh
echo "exit=$?"     # 0 = كلّ الفحوص PASS
```

### ما تقيسه كلّ مرحلة

| المعرّف | ما يُقاس | يقابل في `MIGRATION_UNFREEZE_RUNBOOK_20261028.md` |
|---|---|---|
| R0 | هويّة HEAD والخادم، وبصمات sha256 لملفّات v234–v237 وMANIFEST | §٦ الإيصال |
| R1 | خطّ أساسٍ شبيه بالحيّ: MANIFEST حتى ما قبل v234، ثمّ v206 أخيراً (231 ملفّاً) | §٢.١ |
| R2 | بيانات تاريخيّة قبل الترقية: 500×3 صفوف في سلسلة القرار، و200 صفّ تعلّم، وصفٌّ واحد بمستأجر فارغ | §٤.١-٣: «لا اختبار ترقية على بيانات» |
| R3 | v234 ملفّاً واحداً: قيدان `convalidated`، والصفوف القديمة كلّها `unreviewed/false` | §٤.٣ v234 |
| R4 | **حقن فشل v235:** لكلّ k من 1 إلى N−1 تُنسخ القاعدة، وتُطبَّق أوّل k عبارات، ثمّ الملفّ كاملاً، ثمّ تُطابَق التعريفات (`pg_get_indexdef` و`md5(pg_get_functiondef)` و`pg_get_triggerdef` والأعمدة والتعليقات) وبصمة البيانات مع مرجعٍ نظيف | §٤.١-٤ |
| R4.detector | **تكذيب الكاشف:** يُزرع فهرسٌ بالاسم نفسه وتعريفٍ آخر، و`IF NOT EXISTS` يخفيه، فيجب أن تكشفه المقارنة | المعيار تطابق التعريف لا الوجود |
| R5 | v235 تحت كاتبٍ متزامن لمدّة 8 ثوانٍ: عدد الكتابات والأخطاء وأسوأ زمن. ثمّ قبولٌ وظيفيّ: إدراجٌ مشروع ينال `correlation_id` من الخادم، وتغيير `tenant_id` يُرفض، والتحديث العاديّ يُقبل | §٤.١-٣ و§٤.٣ v235 |
| R6 | v236: `RLS + FORCE` | §٤.٣ v236 |
| R7 | v237 ثمّ v206. تقرير `NOT VALID` يسمّي الصفّ ذا المستأجر الفارغ (الخروج 1 هنا متوقَّع، أي «نظِّف قبل VALIDATE») | — |
| R8 | إعادة MANIFEST الفرع كاملاً على قاعدة الترقية (idempotency) | — |
| R9 | `probe_schema_state.sh` قراءةً فقط: `status=PASS first_missing=none` | §٤.٣ للجميع |
| R10 | **الترقية == البناء من الصفر:** `pg_dump -s` مُطبَّعاً لقاعدة الترقية مقابل قاعدةٍ بُنيت من الصفر بتمريرتين | — |
| R11 | دورٌ مقيَّد `sahool_app_test` (`NOSUPERUSER NOBYPASSRLS`) كما في `ci.yml` | — |
| R12 | اختبارات v237 الحيّة على قاعدة **الترقية** لا الفارغة | — |

**الناتج:** `$OUT/RESULTS.tsv` مع سجلّ كلّ مرحلة في المجلّد نفسه.

---

## ٧) البرهان أحمر ← أخضر: الاختبارات تقيس شيئاً فعلاً

اختبارات v237 الحيّة يجب أن **تفشل** على مخطّط `main` وتنجح بعد v237:

```bash
psql -d postgres -qc "DROP DATABASE IF EXISTS rehearsal_main" -c "CREATE DATABASE rehearsal_main"
git show 210f63827:migrations/MANIFEST.txt > /tmp/MANIFEST.main.txt
bash scripts/ci/apply_migration_manifest.sh --port 5439 --user sahool_test --db rehearsal_main \
  --manifest /tmp/MANIFEST.main.txt | tail -1           # applied=234 expected=234
psql -d rehearsal_main -q <<'SQL'
GRANT CONNECT ON DATABASE rehearsal_main TO sahool_app_test;
GRANT USAGE ON SCHEMA public TO sahool_app_test;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sahool_app_test;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app_test;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app_test;
SQL
export TEST_DATABASE_ADMIN_URL=postgresql://sahool_test:test_password@localhost:5439/rehearsal_main
export TEST_DATABASE_URL=postgresql://sahool_app_test:app_test_password@localhost:5439/rehearsal_main
python -m pytest tests_v9/test_v237_tenant_isolation_live_pg.py -q -p no:cacheprovider -o addopts= | tail -1
#   المتوقّع على main:  5 failed      ← التسرّبات T1/T2/T7/T8/T9 قائمة
psql -d rehearsal_main -v ON_ERROR_STOP=1 -qf migrations/v237_tenant_isolation_hardening.sql
python -m pytest tests_v9/test_v237_tenant_isolation_live_pg.py -q -p no:cacheprovider -o addopts= | tail -1
#   المتوقّع بعد v237:  5 passed
```

---

## ٨) اختبارات الشيفرة للحزم الأربع

**(أ) حيّة على PostgreSQL**، على قاعدة `rehearsal_fresh` التي بناها §٦:

```bash
export TEST_DATABASE_ADMIN_URL=postgresql://sahool_test:test_password@localhost:5439/rehearsal_fresh
export TEST_DATABASE_URL=postgresql://sahool_app_test:app_test_password@localhost:5439/rehearsal_fresh
export RLS_ISOLATION_CERTIFICATION_REQUIRED=1
python -m pytest tests_v9/test_rls_tenant_isolation_live_pg.py tests_v9/test_v237_tenant_isolation_live_pg.py \
  tests_v9/test_role_bootstrap_executable.py -q -p no:cacheprovider -o addopts= -rxs | tail -3
#   المتوقّع: 20 passed — ولا xfail (test_phase_runtime_store_persists_under_the_restricted_app_role صار ينجح)
```

**(ب) وحدةٌ لكلّ حزمة.** تُشغَّل كلّ شجرة وحدها، لأنّ أسماء بعض الملفّات تتكرّر بين `tests/` و`tests_v9/`:

```bash
unset TEST_DATABASE_ADMIN_URL TEST_DATABASE_URL
P="python -m pytest -q -p no:cacheprovider -o addopts="
$P services/actuator-service/test_actuator_safety_audit_20261101.py | tail -1          # A1–A5
$P tests/irrigation/test_gate_b_dispatch_relay_worker.py | tail -1                     # A6
$P tests_v9/test_actuation_killswitch_behaviour.py tests_v9/test_firmware_valve_safety.py \
   tests_v9/test_mqtt_acl_template.py tests_v9/test_nats_least_privilege.py | tail -1  # A2 A4 A7 A8
$P tests_v9/test_mcp_token_revocation.py tests_v9/test_token_revocation_consumers.py \
   tests_v9/test_jwt_revocation_same_redis.py | tail -1                                 # S5
$P tests_v9/test_t3_ingest_definer_execute_revoked_static.py \
   tests_v9/test_v237_tenant_isolation_hardening_static.py | tail -1                    # v237 + T3
( cd services/sahool-platform && $P tests -k "phase_runtime or water_ledger" | tail -1 ) # GUC
```

**(ج) الجناح الكامل لاختبارات الوحدة.** اختياريّ، ويستغرق نحو 15 دقيقة:

```bash
python -m pytest -m unit -q -p no:cacheprovider | tail -3
```

---

## ٩) ما تُعيده إليّ

```bash
R=$(ls -d .local-rehearsal/run-* | tail -1)
{ echo "head=$(git rev-parse HEAD)"; echo "os=$(uname -sm)"; docker --version
  psql --version; python --version; echo; cat "$R/RESULTS.tsv"; } > "$R/REPORT.txt"
tar czf unfreeze-report.tgz -C "$R" .
echo "$R/REPORT.txt  +  unfreeze-report.tgz"
```

أرسل `REPORT.txt`، وأضف إليه مخرجات §٧ و§٨ بهذا القالب:

```text
الكتلة  : §٦ / §٧ / §٨-أ / §٨-ب / §٨-ج
الأمر   : <حرفيّاً>
المخرَج : <آخر 3 أسطر حرفيّاً>
الحكم   : نجح / أخفق / لم يُقَس
ملاحظة  : <منفذ مشغول، صورة ناقصة، إصدار مختلف…>
```

**قاعدة:** ما لم يُقَس لا يُكتَب «مرّ». والاختبار الذي تخطّى لم ينجح.

---

## ١٠) حدود هذه التجربة — ما لا تثبته

- **ليست بيانات الإنتاج ولا أحجامه.** البيانات مُركَّبة، وأزمنة الأقفال صغيرة لأنّ الجداول صغيرة. الشرط §٤.١-٣ على **نسخةٍ مستعادة** من الإنتاج يبقى مطلوباً.
- **لا نسخ احتياطيّ ولا استعادة ولا RPO** (§٤.١-١ و§٤.١-٥): قراران للمالك.
- **توافق التطبيق المنشور حاليّاً** مع مشغّلات v235 لم يُقَس هنا. القبول الوظيفيّ في R5 يقيس قاعدة البيانات وحدها.
- **`firmware/*.ino` و`mosquitto/acl.template`** فُحصا بالاختبارات الساكنة وحدها، فلا عتاد هنا ولا وسيط MQTT.
- **حارس GATE-01 يحمرّ على هذا الفرع عمداً**، لأنّه يمسّ المسارات المجمَّدة بلا حكم. فتحها في `main` يحتاج حكماً مستقلّاً لكلّ مسار وفق `docs/runbooks/GATE01_INDEPENDENT_AUTHORITY_AND_IMAGE_SUPPLY_CHAIN.md`.
- **ملاحظة قائمة قبل هذا الفرع** (`R10.fresh_once_vs_twice`): على قاعدة فارغة يختلف المخطّط بعد تمريرة واحدة عن المخطّط بعد تمريرتين. السبب أنّ بعض الفهارس والقيود لا تُنشأ إلّا حين يوجد جدولها من تمريرةٍ سابقة. والمُهاجر يعيد MANIFEST كاملاً في كلّ تشغيل، فالإنتاج أقرب إلى حالة «التمريرتين». لا علاقة لذلك بـv234–v237.

---

## ١١) التنظيف

```bash
docker rm -f sahool-unfreeze-pg
deactivate; rm -rf .venv-unfreeze
git switch -                      # العودة إلى فرعك السابق
```
