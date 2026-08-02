# دليل إغلاق الفجوات الحيّة — أوامر جاهزة للوكيل المحلّيّ على الخادم

> **الاستعمال:** كلّ كتلة أدناه مستقلّة وقابلة للنسخ واللصق في شاشة محادثة الوكيل المحلّيّ.
> نفّذ **مرحلةً مرحلة** بالترتيب: المرحلة 0 إلزاميّة قبل أيّ شيء، ثمّ 1 (طبقة البيانات) قبل 2
> (شبكة الخدمات) قبل 3 (السلسلة الكاملة).
>
> **أساس القياس:** كلّ رقم واسم في هذا الدليل (الجداول والأعمدة وسلوك المصادقة) مقيس على
> `4ad1b1cc`. لم أذكر التزام الفرع لأنّه يتغيّر مع كلّ إعادة تأسيس فيبيت النصّ — والتحقّق
> الصحيح ليس مقارنة رقمين بل أمرٌ تُشغّله أنت:
> `git diff --name-only 4ad1b1cc HEAD -- migrations/ services/` — إن كان فارغاً فالأرقام قائمة،
> وإلّا فأعِد قياس ما مسّه الفرق قبل أن تستعمله. البيئة والرفع موصوفان في
> [`REAL_ENV_VERIFICATION_RUNBOOK.md`](REAL_ENV_VERIFICATION_RUNBOOK.md) — هذا الدليل **لا يكرّره**،
> بل يُضيف ما ينقصه: **برهان إغلاق لكلّ فجوة على حدة، مع حزمة دليل**.

---

## القاعدة الحاكمة — اقرأها قبل أيّ أمر

**لا يُرفَع `runtime_verified` ولا `production_certified` على أيّ فجوة إلّا بحزمة دليل كاملة.**
النجاح على الشاشة ليس إغلاقاً؛ الإغلاق أن يستطيع غيرُك إعادة إنتاج النتيجة. كلّ كتلة تنتهي
بحزمة من **سبعة عناصر**، وأيّ عنصر ناقص ⇒ الفجوة تبقى مفتوحة:

| # | العنصر | لماذا |
|---|---|---|
| 1 | `git rev-parse HEAD` (40 محرفاً) | نتيجة بلا SHA لا تُنسَب إلى شيفرة |
| 2 | `docker compose images` (image digests) | «نفس الوسم» ليس نفس الصورة |
| 3 | حالة الهجرات | نتيجة على مخطّط مجهول لا تُعاد |
| 4 | الأمر المُنفَّذ حرفيّاً | «شغّلت الاختبارات» ليس أمراً |
| 5 | stdout و stderr كاملين | الملخّص يُخفي التخطّي (skip) |
| 6 | طوابع زمنيّة (بدء/انتهاء) | يفصل «مرّ» عن «انتهت مهلته» |
| 7 | تصنيف صريح: `CLOSED_LIVE` / `PARTIAL` / `BLOCKED` + السبب | «تقريباً» ليست حالة |

**وثلاثة محرّمات:**
- **لا تُليّن اختباراً ليمرّ.** فشلٌ صادق أنفع من خضرة مُشتراة. إن فشل، سجّل الفشل وانتقل.
- **لا تُصنّف فشلاً «بيئة» قبل إثباته.** أُثبِت في هذا المستودع أنّ تصنيف «بيئة Windows» كان
  خاطئاً و12 فشلاً كانت عيباً حقيقيّاً في الكود (`TEXT-DECODED-WITH-THE-MACHINES-LOCALE-01`).
  إن ادّعيت «بيئة» فأعِد إنتاج الفشل بطريقة ثانية أو لا تدّعِ.
- **لا تُشغّل شيئاً على الإنتاج** في هذا الدليل كلّه. staging فقط ما لم يُذكر خلاف ذلك صراحةً.

---

## المرحلة 0 — الأساس وحزمة الدليل الابتدائيّة (إلزاميّة)

```bash
# ═══ 0.1 التقط الأساس قبل أيّ تشغيل ═══
mkdir -p evidence/live-$(date -u +%Y%m%dT%H%M%SZ) && cd "$_" && export EV=$PWD && cd -
echo "EVIDENCE DIR = $EV"

git rev-parse HEAD                | tee "$EV/00_head_sha.txt"
git status --porcelain            | tee "$EV/00_tree_state.txt"   # يجب أن يكون فارغاً
date -u +%Y-%m-%dT%H:%M:%SZ       | tee "$EV/00_started_at.txt"
```

**توقّف إن لم يكن `00_tree_state.txt` فارغاً.** شجرة متّسخة تجعل كلّ رقم بعدها غير منسوب.

```bash
# ═══ 0.2 الرفع (تفصيله في REAL_ENV_VERIFICATION_RUNBOOK §ب.0) ═══
cp -n .env.example .env    # ثمّ املأ: JWT_SECRET · SAHOOL_AGENT_TOKEN · REDIS_PASSWORD · ACTIVATION_EVIDENCE_SIGNING_KEY
python scripts/runtime/env_doctor.py --mode preflight --format json --output "$EV/01_preflight.json"
python -c "import json;d=json.load(open('$EV/01_preflight.json'));print(d.get('status'))"   # يجب: ready

make build-immutable
docker compose -f docker-compose.v9.yml up -d
docker compose -f docker-compose.v9.yml images | tee "$EV/02_image_digests.txt"

BASE_URL=http://localhost python scripts/runtime/env_doctor.py --mode runtime \
  --format json --output "$EV/03_runtime.json"
```

```bash
# ═══ 0.3 حالة الهجرات — العنصر ٣ من الحزمة ═══
docker compose -f docker-compose.v9.yml exec -T sahool-postgres \
  psql -U postgres -d sahool -c "\dt" | tee "$EV/04_schema_tables.txt"
docker compose -f docker-compose.v9.yml exec -T sahool-postgres \
  psql -U postgres -d sahool -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
  | tee -a "$EV/04_schema_tables.txt"
```

> **معيار المرور:** `preflight=ready` · `runtime` بلا أخطاء · digests مُلتقَطة · جدول المخطّط غير فارغ.
> **إن فشل الرفع:** لا تُكمل. سجّل `BLOCKED` بسبب مقيس (رفض سِجِلّ الحاويات؟ متغيّر ناقص؟) وأبلغ.

---

## المرحلة 1 — فجوات طبقة البيانات (PostgreSQL وحده، بلا mesh)

> **قبل أيّ استعلام أدناه — اكتشف الأسماء الفعليّة، لا تثق بما هنا.**
> أسماء الجداول في هذا الدليل مقيسة من `migrations/` على `4ad1b1cc`، وقد تتغيّر. الاستعلام على
> جدول غير موجود يُنتِج خطأً يُقرأ خطأً على أنّه «لا بيانات» — وهو أسوأ من الفشل الصريح.
>
> ```bash
> docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
>   SELECT table_name FROM information_schema.tables
>   WHERE table_schema='public'
>     AND table_name ~ '(approval|execution|receipt|outbox|snapshot|decision|reservation)'
>   ORDER BY 1;" | tee "$EV/05_table_names.txt"
> ```
> طابِق ما يظهر مع ما يستعمله كلّ استعلام. إن اختلف اسمٌ، **صحّح الاستعلام وسجّل التصحيح** في
> حزمة الدليل — لا تُشغّل استعلاماً تعرف أنّه على اسم خاطئ.

### ① `AUTH-E2E-UNDER-RESTRICTED-ROLE` — ثغرة CI لا ثغرة كود

الفجوة **مُغلَقة حيّاً** سلفاً (10/10 على `9a3ce99`). الباقي أنّ CI يُشغّل `-m integration` بدور
`sahool_test` (superuser) لا `sahool_app` المقيَّد — فالـRLS **لا يُختبَر فعليّاً في CI**.

```bash
# أعِد الإثبات تحت الدور المقيَّد صراحةً — لا تحت superuser
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('sahool_app','sahool_test');
" | tee "$EV/10_roles.txt"
# يجب: sahool_app  → f | f   (وإلّا فالاختبار التالي لا يُثبت شيئاً)

DATABASE_URL="postgresql://sahool_app:${SAHOOL_APP_PW}@localhost:5432/sahool" \
  pytest -v -m integration tests_v9/test_auth_e2e.py \
  > "$EV/11_auth_e2e_restricted.log" 2>&1; echo "exit=$?" | tee -a "$EV/11_auth_e2e_restricted.log"
```

**معيار الإغلاق:** `rolsuper=f` و`rolbypassrls=f` **و** الاختبارات خضراء. لو مرّت تحت superuser
فهي لا تُثبت RLS — وهذا بالضبط عيب CI القائم.
**التصنيف:** `CLOSED_LIVE` إن تحقّق الشرطان · وإلّا `PARTIAL` مع تسمية الدور المستعمَل.

---

### ② `DECISION-SOR-TRANSITIONAL` — القلب إلى decision-service

```bash
# 2.1 جاهزيّة القلب — النقطة قائمة في decision-service
curl -sS http://localhost:8000/v1/cutover/readiness | tee "$EV/20_cutover_readiness.json"
```

```bash
# 2.2 وضع الكتابة: shadow أوّلاً (لا decision_service_sor مباشرةً)
export SAHOOL_DECISION_WRITE_MODE=shadow
docker compose -f docker-compose.v9.yml up -d sahool-platform sahool-decision-service
pytest -v -m integration tests_v9/test_decision_consistency_auth.py \
       tests_v9/test_dispatch_decisions_integration.py \
  > "$EV/21_sor_shadow.log" 2>&1; echo "exit=$?" | tee -a "$EV/21_sor_shadow.log"
```

```bash
# 2.3 RLS بين مستأجِرَين — البرهان الذي لا يُغني عنه شيء
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U sahool_app -d sahool -c "
  SET app.tenant_id = 'tenant-A';
  SELECT count(*) AS visible_to_A FROM decision_record;
  SET app.tenant_id = 'tenant-B';
  SELECT count(*) AS visible_to_B FROM decision_record;
" | tee "$EV/22_rls_cross_tenant.txt"
```

```bash
# 2.4 idempotency الصندوق الصادر: اقتل العامل بعد commit وتحقّق من نشرة واحدة لا اثنتين
docker compose -f docker-compose.v9.yml kill sahool-phase-runtime-outbox-worker
docker compose -f docker-compose.v9.yml up -d sahool-phase-runtime-outbox-worker
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT idempotency_key, count(*) FROM actuator_command_outbox
  GROUP BY idempotency_key HAVING count(*) > 1;
" | tee "$EV/23_outbox_idempotency.txt"
# يجب أن يكون **فارغاً**: صفر مفتاح مكرّر
```

**الشرط الكامل قبل `decision_service_sor`:** اتبع
[`DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md`](DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md) —
لا تقلب الوضع من هذا الدليل. **`shadow` هنا برهان، والقلب قرار مالك.**
**التصنيف:** `PARTIAL` عند نجاح 2.1–2.4 (القلب لم يُنفَّذ) · `CLOSED_LIVE` بعد القلب المُوثَّق.

---

### ③ `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01` — سياسة الأهليّة على بيانات حقيقيّة

الجذر: خلطٌ بين سؤالين — «هل اللقطة صالحة؟» و«هل الإجراء مأذون؟». المطلوب إثبات أنّ
`policy_version` يتغيّر **ولا يتغيّر** `snapshot_digest`.

```bash
pytest -v -m integration -k "snapshot or eligibility" \
  > "$EV/30_snapshot_eligibility.log" 2>&1; echo "exit=$?" | tee -a "$EV/30_snapshot_eligibility.log"
```

> **تصحيح مقيس قبل أن تستعلم:** بحثتُ في `migrations/` على `4ad1b1cc` فلا يوجد عمود اسمه
> `snapshot_digest` في أيّ جدول، و`policy_version` موجود في `canonical_root_zone_hydraulic_profile`
> وحده (و`selection_policy_version` في التربة). فالثنائيّة «بصمة مقابل نسخة سياسة» **مفهوم في
> الشيفرة** (`services/decision-service/main.py:332`) لا زوج أعمدة جاهز للاستعلام.
>
> لذلك الإثبات هنا **من الخدمة لا من SQL**:

```bash
# اطلب نفس اللقطة مرّتين مع اختلاف نسخة السياسة وحدها، وقارن البصمة المُعادة
for POL in v1 v2; do
  curl -sS -H "Authorization: Bearer $SAHOOL_AGENT_TOKEN" \
       -H "X-Policy-Version: $POL" \
       "http://localhost:8000/api/v1/fields/${FIELD_ID}/canonical-state" \
    | tee "$EV/31_state_policy_$POL.json"
done
python - <<'EOF' | tee "$EV/32_digest_invariance.txt"
import json
a = json.load(open("$EV/31_state_policy_v1.json"))
b = json.load(open("$EV/31_state_policy_v2.json"))
da, db = a.get("state_digest"), b.get("state_digest")
print("digest_v1:", da); print("digest_v2:", db)
print("INVARIANT (matches the contract):" if da == db else "DIGEST MOVED WITH POLICY (gap open):", da == db)
for lvl in ("discover", "diagnose", "propose", "execute"):
    print(lvl, a.get("eligibility", {}).get(lvl, {}).get("allowed"),
               b.get("eligibility", {}).get(lvl, {}).get("allowed"))
EOF
```

**معيار الإغلاق:** البصمة **واحدة** رغم اختلاف نسخة السياسة ⇒ البصمة تُعرّف المُدخَلات لا الحكم.
لو تحرّكت البصمة بتغيّر السياسة فالفجوة **مفتوحة** — وكلّ موافقة مربوطة ببصمة مخزَّنة تنكسر.
**و`execute` يجب أن يبقى `false` دائماً** من هذه البنية: لا إذن ولا توقيع ولا هويّة مُوافِق فيها.

**تنبيه صدق:** المصفوفة الرباعيّة مُغلَقة على **مستوى الإعلانات** فقط في `canonical_field_state`؛
ربط المستأجر/الحقل والمواءمة الزمنيّة والطابع الزمنيّ المستقبليّ **لم تُغلَق** — لا تدّعِ إغلاقها.

---

### ④ `EVIDENCE-ENVELOPE-NOT-GENERALIZED` — نفس الغلاف عبر مجالين

```bash
# مجالان مختلفان حقيقةً: ريّ + طيف/رتسر — لا مجال واحد مرّتين
pytest -v -m integration -k "evidence" \
  > "$EV/40_evidence_envelope.log" 2>&1; echo "exit=$?" | tee -a "$EV/40_evidence_envelope.log"

docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT domain, count(*) FROM evidence_graph_nodes GROUP BY domain ORDER BY 2 DESC;
" | tee "$EV/41_evidence_domains.txt"
```

```bash
# الرفض المُغلَق: بصمة غير مطابقة · مستأجِر مفقود · طابع زمنيّ مستقبليّ · معرّف مكرّر
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  -- يجب أن يفشل كلّ إدراج أدناه؛ نجاح أيّها = فجوة مفتوحة
  INSERT INTO evidence_graph_nodes (evidence_id, tenant_id, observed_at)
  VALUES ('dup-probe', NULL, now());
" 2>&1 | tee "$EV/42_evidence_fail_closed.txt"
```

**معيار الإغلاق:** مجالان مختلفان في `41` **و** كلّ محاولة في `42` مرفوضة.
**إن نجح إدراج بمستأجِر `NULL`** فهذه فجوة أخطر من الأصليّة — سجّلها فوراً بمعرّف جديد.

---

## المرحلة 2 — شبكة الخدمات

### ⑤ `CANONICAL-WEATHER-CONSUMPTION`

```bash
docker compose -f docker-compose.v9.yml up -d sahool-weather-service sahool-platform sahool-redis
sleep 20

# المسار السعيد
curl -sS -H "Authorization: Bearer $SAHOOL_AGENT_TOKEN" \
  "http://localhost:8000/api/v1/fields/${FIELD_ID}/canonical-state" \
  | tee "$EV/50_weather_happy.json"
python -c "
import json;d=json.load(open('$EV/50_weather_happy.json'))
w=d.get('weather');print('weather present:',w is not None)
print('schema_version:',(w or {}).get('schema_version'));print('observed_at:',(w or {}).get('observed_at'))"
```

```bash
# فشل الخدمة ⇒ يجب 503 أو weather_status=unavailable — **لا قيمة مُختلَقة**
docker compose -f docker-compose.v9.yml stop sahool-weather-service
curl -sS -o "$EV/51_weather_down.json" -w "http_code=%{http_code}\n" \
  -H "Authorization: Bearer $SAHOOL_AGENT_TOKEN" \
  "http://localhost:8000/api/v1/fields/${FIELD_ID}/canonical-state" | tee "$EV/51_weather_down_code.txt"
docker compose -f docker-compose.v9.yml start sahool-weather-service
```

**معيار الإغلاق:** المسار السعيد يُعيد `schema_version` و`observed_at` حقيقيَّين · وسقوط الخدمة
يُنتِج **503 أو `unavailable` صراحةً**، لا قيمة افتراضيّة صامتة.
**تنبيه مقيس:** `POST /v1/weather/agro/canonical-state` **حاسبة على مُدخَلات المُستدعي** لا جالبة —
فتغذيتها من المنصّة تجعل المنصّة هي مَن يؤكّد وقائع الطقس. لا تستعملها كبرهان استهلاك.

---

### ⑥ `CANONICAL-SPECTRAL-CONSUMPTION`

```bash
docker compose -f docker-compose.v9.yml up -d sahool-raster-service sahool-minio sahool-titiler \
                                             sahool-vegetation-analysis
sleep 30

# COG حقيقيّ لا تركيبيّ — الراية تمنع الاصطناع
export VEGETATION_REAL_ONLY=1
curl -sS -H "Authorization: Bearer $SAHOOL_AGENT_TOKEN" \
  "http://localhost:8000/v1/ndvi/current/${FIELD_ID}" | tee "$EV/60_ndvi_current.json"
python -c "
import json;d=json.load(open('$EV/60_ndvi_current.json'))
print('real_data:',d.get('real_data'));print('usable:',d.get('usable'))"
```

```bash
# أصل كاذب: بيانات وصفيّة بلا COG ⇒ usable=false لا استنتاج
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT asset_id, usable, quality_status FROM raster_assets ORDER BY created_at DESC LIMIT 10;
" | tee "$EV/61_raster_assets.txt"
docker compose -f docker-compose.v9.yml logs --tail=200 sahool-raster-service > "$EV/62_raster_logs.txt" 2>&1
```

**معيار الإغلاق:** `real_data=true` مع `VEGETATION_REAL_ONLY=1` · وأصلٌ بلا COG يظهر `usable=false`.
**إن رجع `real_data=false` والراية مفعّلة** فهذه خرق عقد — سجّلها `BLOCKED` وأبلغ فوراً.

---

### ⑦ `MCP-PREAUTH-STATUS-01` — مصفوفة الحالات

> **صحّح قبل أن تقيس:** التقرير قال إنّ الموضع يُعيد **400** بدل 401. قراءة الشيفرة على
> `4ad1b1cc` تُظهر `HTTPBearer(auto_error=False)` ⇒ الغياب يصل الدالّة فترفع **401** صراحةً.
> فلا تفترض الرقم — **قِسه**، وسجّل ما تراه لا ما قرأتَه في تقرير.

```bash
docker compose -f docker-compose.v9.yml up -d sahool-weather-mcp sahool-market-mcp sahool-nginx
sleep 15
M=http://localhost:8000/mcp/v1/tools

for case in "no-token:" "malformed:Bearer abc" "expired:Bearer $EXPIRED_JWT" "valid:Bearer $VALID_JWT"; do
  name=${case%%:*}; hdr=${case#*:}
  code=$(curl -sS -o /dev/null -w '%{http_code}' ${hdr:+-H "Authorization: $hdr"} "$M")
  echo "$name -> $code"
done | tee "$EV/70_mcp_preauth_matrix.txt"
```

**المصفوفة المتوقّعة:** بلا توكن ⇒ **401** · مُشوَّه ⇒ 401 · منتهٍ ⇒ 401 · صالح بلا صلاحيّة ⇒ 403 ·
صالح مسموح ⇒ 2xx · طلب مُشوَّه بمصادقة صحيحة ⇒ 400/422.
**التصنيف:** أيّ انحراف = الفجوة مفتوحة، وسجّل الرمز الفعليّ لكلّ حالة.

---

### ⑧ `DEFERRED-IMPORT-UNDECLARED-01` — حاوية نظيفة

الدَّين المُجمَّد ثلاثة: `sahool-platform:sklearn` (أخطرها — استيراد مؤجَّل **عارٍ بلا try/except**) ·
`raster-service:yaml` · `ai_agronomist:redis`.

```bash
# حاوية نظيفة تماماً — لا تستعمل صورة مبنيّة سلفاً
docker run --rm -v "$PWD":/w -w /w python:3.11-slim bash -lc '
  pip install -q -r services/sahool-platform/api/requirements.txt
  python -c "import sklearn" ; echo "sklearn exit=$?"
' 2>&1 | tee "$EV/80_deferred_sklearn.txt"

docker run --rm -v "$PWD":/w -w /w python:3.11-slim bash -lc '
  pip install -q -r services/raster-service/requirements.txt
  python -c "import yaml" ; echo "yaml exit=$?"
' 2>&1 | tee "$EV/81_deferred_yaml.txt"
```

**معيار الإغلاق:** `exit=0` للثلاثة **بعد** إعلانها في `requirements`.
**قاعدة المستودع مُلزِمة:** `CLAUDE.md` يوجب `pip-audit -r <file>` **قبل** أيّ إضافة تبعيّة.
لا تُضِف سطراً بلا فحص:

```bash
pip-audit -r services/sahool-platform/api/requirements.txt \
  --ignore-vuln PYSEC-2026-1325 2>&1 | tee "$EV/82_pip_audit.txt"
```

> `--ignore-vuln PYSEC-2026-1325` استثناء موثَّق (`ecdsa` عبر `python-jose`، والتوقيع عندنا عبر
> `cryptography`). بدونه تظهر نتيجة حمراء كاذبة.

---

### ⑨ `SUPERVISOR-SKILL-BEHAVIORAL-DIVERGENCE` — دخان Docker

```bash
docker compose -f docker-compose.v9.yml up -d sahool-supervisor-agent
sleep 20
docker compose -f docker-compose.v9.yml logs --tail=300 sahool-supervisor-agent \
  > "$EV/90_supervisor_boot.txt" 2>&1
grep -iE "error|traceback|ModuleNotFound|ImportError" "$EV/90_supervisor_boot.txt" || echo "clean boot"
```

```bash
# البرهان: حذف نسخ الجذر الميّتة لا يكسر الإقلاع
git rm -r --cached skills/ 2>/dev/null; mv skills /tmp/skills_probe
docker compose -f docker-compose.v9.yml restart sahool-supervisor-agent && sleep 20
docker compose -f docker-compose.v9.yml logs --tail=100 sahool-supervisor-agent \
  > "$EV/91_supervisor_without_root_skills.txt" 2>&1
mv /tmp/skills_probe skills && git checkout -- skills 2>/dev/null   # استعادة إلزاميّة
```

**معيار الإغلاق:** إقلاع نظيف **مع** غياب نسخ الجذر ⇒ ثبتت موتها سلوكيّاً لا بالقراءة.
**أعِد `skills/` دائماً** قبل أيّ خطوة تالية، وتحقّق بـ`git status --porcelain` أنّها عادت.

---

## المرحلة 3 — السلسلة الكاملة

### ⑩ `APPROVAL-EXECUTION-CONTENT-PIN-UNPROVEN` — سباق TOCTOU

```bash
docker compose -f docker-compose.v9.yml up -d sahool-decision-service sahool-nats sahool-actuator-service
sleep 25

# 1) مرشّح بمحتوى معروف  2) عدّل الخطّة بعد الموافقة  3) نفّذ ⇒ يجب الرفض ببصمة غير مطابقة
pytest -v -m integration tests_v9/test_wx10_11b_execution_delivery_receipt_contract.py \
  > "$EV/A0_toctou.log" 2>&1; echo "exit=$?" | tee -a "$EV/A0_toctou.log"

docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT status, count(*) FROM execution_ledger GROUP BY 1,2;
" | tee "$EV/A1_execution_rejections.txt"
```

**معيار الإغلاق — ثلاثة معاً:** الطلب **مرفوض** بسبب `digest mismatch` · **لا** أمر NATS صدر ·
**لا** إيصال مُشغّل. غياب أيّها يعني أنّ التثبيت غير مُثبَت.

```bash
# لا أمر تسرّب: راقب الموضوع أثناء المحاولة
docker compose -f docker-compose.v9.yml exec -T sahool-nats \
  nats sub 'actuator.>' --count=1 --timeout=30s > "$EV/A2_nats_silence.txt" 2>&1 || echo "no message (expected)"
```

---

### ⑪ `AGENT-TO-ACTUATOR-BYPASS-NOT-GUARDED`

```bash
# تجاوز HTTP مباشر من حاوية وكيل ⇒ يجب أن يفشل بسياسة الشبكة/المصادقة
docker compose -f docker-compose.v9.yml exec -T sahool-ai-agronomist \
  curl -sS -o /dev/null -w 'direct_bypass_http=%{http_code}\n' \
  http://sahool-actuator-service:8000/v1/commands 2>&1 | tee "$EV/B0_http_bypass.txt"
# المقبول: رفض (000 اتّصال محجوب · أو 401/403). أمّا 2xx فهو **تجاوز حقيقيّ**.
```

```bash
# تجاوز NATS بهويّة وكيل ⇒ يجب أن يرفضه الوسيط
docker compose -f docker-compose.v9.yml exec -T sahool-ai-agronomist \
  nats pub 'actuator.command' '{"probe":"bypass"}' 2>&1 | tee "$EV/B1_nats_bypass.txt"

# المسار الصحيح كاملاً يجب أن ينجح — وإلّا فالحجب أعمى لا انتقائيّ
pytest -v -m integration tests_v9/test_actuation_killswitch_v29_5_op.py \
  > "$EV/B2_legit_path.log" 2>&1; echo "exit=$?" | tee -a "$EV/B2_legit_path.log"
```

**معيار الإغلاق:** التجاوزان مرفوضان **والمسار الشرعيّ ناجح**. حجبٌ يمنع الاثنين ليس حراسة بل عطل.

---

### ⑫ `CORRELATION-ID-NOT-BRIDGED-TO-ACTUATOR`

> **حقيقة مقيسة تُغيّر شكل هذا الاختبار:** بحثٌ في `migrations/` على `4ad1b1cc` يُظهر أنّ
> `correlation_id` **غير موجود** في `decision_record` ولا `execution_ledger` ولا
> `as_applied_irrigation_receipts` ولا `approvals`. يوجد في `irrigation_resource_reservations`
> و`irrigation_resource_reservation_events` و`workflow_state`، وكـ`analysis_id` في
> `field_evidence_snapshots`. **أي أنّ الجسر مفقود في المخطّط نفسه** — وهو تأكيد للفجوة لا نفي لها.
>
> فمهمّتك ليست «هل تمرّ السلسلة؟» بل **«إلى أين يصل المعرّف، وأين ينقطع بالضبط؟»**

```bash
export CID="probe-$(date -u +%s)"
curl -sS -X POST -H "Authorization: Bearer $SAHOOL_AGENT_TOKEN" \
     -H "X-Correlation-ID: $CID" -H 'Content-Type: application/json' \
     -d "{\"field_id\":\"${FIELD_ID}\"}" \
     http://localhost:8000/api/v1/irrigation/recommendations | tee "$EV/C0_kickoff.json"
```

```bash
# 1) أيّ جدول يحمل العمود أصلاً — اكتشاف لا افتراض
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT table_name FROM information_schema.columns
  WHERE table_schema='public' AND column_name IN ('correlation_id','analysis_id')
  ORDER BY 1;" | tee "$EV/C1_correlation_columns.txt"

# 2) أين وصل المعرّف فعلاً — نفّذ على ما ظهر في C1 فقط
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT 'reservations' src, count(*) FROM irrigation_resource_reservations   WHERE correlation_id::text='$CID'
  UNION ALL
  SELECT 'reservation_events', count(*) FROM irrigation_resource_reservation_events WHERE correlation_id::text='$CID';
" | tee "$EV/C2_correlation_reach.txt"

# 3) وأين انقطع — تتبّع السجلّات عبر الخدمات بنفس المعرّف
for svc in sahool-platform sahool-decision-service sahool-actuator-service \
           sahool-reservation-dispatch-relay-worker; do
  echo "--- $svc ---"
  docker compose -f docker-compose.v9.yml logs --since=10m "$svc" 2>&1 | grep -c "$CID"
done | tee "$EV/C3_correlation_in_logs.txt"
```

```bash
# فشل جزئيّ: اقتل المُتابِع وأعِد التشغيل ⇒ لا تنفيذ مزدوج
docker compose -f docker-compose.v9.yml kill sahool-reservation-dispatch-relay-worker
docker compose -f docker-compose.v9.yml up -d sahool-reservation-dispatch-relay-worker
sleep 20
docker compose -f docker-compose.v9.yml exec -T sahool-postgres psql -U postgres -d sahool -c "
  SELECT idempotency_key, count(*) FROM actuator_command_outbox
  GROUP BY 1 HAVING count(*) > 1;" | tee "$EV/C4_no_double_execution.txt"   # يجب أن يكون فارغاً
```

**معيار الإغلاق:** المعرّف يصل الحجز **و** يظهر في سجلّات الخدمات الأربع **و** `C4` فارغ.
**والنتيجة المتوقّعة اليوم `PARTIAL` لا `CLOSED_LIVE`** — لأنّ العمود غائب عن جداول القرار
والتنفيذ والإيصال. سجّل **أين انقطع بالضبط**؛ ذلك هو شرط إغلاق الفجوة لاحقاً بهجرة تُضيف العمود.


---

### ⑬ Playbook الريّ المغلق الدورة — أربعة عشر سيناريو فشل

```bash
docker compose -f docker-compose.v9.yml up -d   # الكلّ + محاكي المُشغّل
sleep 60
pytest -v -m integration -k "irrigation or reservation or actuator" \
  > "$EV/D0_irrigation_loop.log" 2>&1; echo "exit=$?" | tee -a "$EV/D0_irrigation_loop.log"
```

ثمّ **كلّ سيناريو على حدة** — لا تدمجها، فالدمج يُخفي أيّها فشل:

| # | السيناريو | كيف تُحدثه | السلوك المطلوب |
|---|---|---|---|
| 1 | weather unavailable | أوقف `sahool-weather-service` | حجب + سبب مُسمّى |
| 2 | weather stale | أزِح `observed_at` للخلف | `weather_stale` |
| 3 | soil missing | احذف منتَج التربة | حجب `diagnose` |
| 4 | capacity unavailable | استهلك السعة | رفض مُغلَق |
| 5 | concurrent reservation | طلبان متزامنان | واحد فقط ينجح |
| 6 | approval expired | قدّم الساعة | رفض |
| 7 | modified plan | عدّل بعد الموافقة | `digest mismatch` |
| 8 | relay crash | اقتل المُتابِع | استئناف بلا ازدواج |
| 9 | duplicate NATS | انشر الرسالة مرّتين | إيصال واحد |
| 10 | valve partial failure | إيصال جزئيّ | لا يُعلَن اكتمالاً |
| 11 | missing sensor samples | احجب العيّنات | لا تُختلَق قيمة |
| 12 | invalid device identity | هويّة مزوّرة | رفض + تدقيق |
| 13 | outcome mismatch | نتيجة مخالفة | يُسجَّل لا يُبتلَع |
| 14 | rollback failure | أفشِل التسوية | حالة صريحة لا صامتة |

```bash
for i in $(seq 1 14); do echo "=== scenario $i ==="; done | tee "$EV/D1_scenarios_index.txt"
# سجّل لكلّ سيناريو: الأمر · stdout/stderr · السلوك المرصود · مطابق/مخالف
```

**التصنيف:** `CLOSED_LIVE` **فقط** إذا مرّ الأربعة عشر. أيّ سيناريو غير مُنفَّذ ⇒ `PARTIAL` مع
تسمية غير المُنفَّذ بالرقم. **لا تُقرِّب**: «13 من 14» ليست إغلاقاً.

---

## المرحلة 4 — حزمة الدليل والتسجيل

```bash
date -u +%Y-%m-%dT%H:%M:%SZ | tee "$EV/99_finished_at.txt"
python scripts/certification/evidence_lab.py 2>&1 | tee "$EV/99_evidence_lab.txt" || true
python scripts/release/validate_release_package.py --root . 2>&1 | tee "$EV/99_release_validation.txt"
tar czf "sahool-live-evidence-$(git rev-parse --short HEAD).tar.gz" -C "$(dirname "$EV")" "$(basename "$EV")"
sha256sum sahool-live-evidence-*.tar.gz | tee "$EV/99_bundle_sha256.txt"
```

### التسجيل في الدماغ المعرفيّ — إلزاميّ

لكلّ فجوة نُفِّذت، أضِف إلى `sahool-brain/gaps/registry.md` تحت معرّفها:

```
- **تحقّق حيّ (YYYY-MM-DD):** SHA `<40>` · digests في `<bundle>` · الأمر: `<حرفيّاً>` ·
  النتيجة: `<PASS/FAIL + الأرقام>` · التصنيف: `CLOSED_LIVE|PARTIAL|BLOCKED` · السبب: `<...>`
```

ثمّ ألحِق سطراً في `sahool-brain/log.md`، وحدّث `sahool-brain/hot.md`.
**قواعد المستودع الصارمة:** لا معلومة بلا مصدر · لا فجوة بلا حالة · لا قرار بلا سبب · لا تحديث
بلا سطر في `log.md`.

> **تحذير على رسالة الالتزام:** `brain_commit_claim_guard` يرفض ذكر معرّف فجوة غير مُسجَّل،
> ونمطه يلتقط **أيّ** عبارة كبيرة موصولة بثلاث شرطات فأكثر. لا تكتب عبارات مثل تلك في نصّ
> الرسالة، وتحقّق من رمز الخروج **قبل** الدفع:

```bash
python scripts/ci/brain_commit_claim_guard.py --base origin/main --head HEAD; echo "guard exit=$?"
# ولا تدفع إلّا إذا كان 0
```

---

## ما لا يُغلقه هذا الدليل — بصراحة

- **`TEMPLATE-WORKFLOW-CAN-COMPLETE`** و**`SILENT-EXCEPTION-HANDLERS-11-01`** مُغلقتان ساكنتين
  بالفعل؛ أيّ تشغيل حيّ لهما **تأكيديّ لا إغلاقيّ**.
- **بقيّة طبقات `CANONICAL-FIELD-STATE-ELIGIBILITY`** (ربط المستأجر/الحقل · نسخة الهندسة ·
  المواءمة الزمنيّة · الطابع الزمنيّ المستقبليّ) تحتاج حقولاً لا تحملها البنية اليوم — لا تُغلقها
  باختبار حيّ.
- **قلب SoR إلى `decision_service_sor`** قرار مالك بستّ بوّابات، لا خطوة في دليل.
- **لا شيء هنا يرفع `runtime_verified` ولا `production_certified`** تلقائيّاً. رفعهما فعلٌ منفصل
  بعد مراجعة الحزمة.
