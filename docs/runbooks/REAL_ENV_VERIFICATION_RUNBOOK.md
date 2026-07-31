# REAL_ENV_VERIFICATION_RUNBOOK — التحقّق الحيّ لمنصّة سهول

دليل تشغيليّ للتحقّق الحيّ الكامل، مقسوم إلى **ما يُثبَت بطبقة البيانات وحدها** (يعمل في أيّ بيئة
فيها PostgreSQL أصليّ، بلا سِجِلّ حاويات) و**ما يحتاج mesh الخدمات الكامل** (Redis/NATS/HTTP —
بيئة المالك). حُدِّث بنتائج جلسة 2026-07-18 (`main` عند `fe17b73`).

---

## القسم أ — طبقة البيانات (يعمل بلا Docker Hub) — **مُصادَق حيّاً ✅**

> **لماذا أصليّ لا حاوية:** بعض البيئات تحجب سِجِلّ الحاويات (Docker Hub 403 عند CONNECT).
> `postgresql-16` + `postgresql-16-postgis-3` الأصليّان يكفيان لكلّ تحقّقات الـDB بلا أيّ صورة.

### أ.0 — رفع cluster أصليّ + المخطّط الكامل + الأدوار المقيّدة
```bash
# cluster أصليّ (Ubuntu ينشئ 16/main تلقائيّاً)
pg_ctlcluster 16 main start
sudo -u postgres createdb -O postgres sahool   # أو sahool_user كمالك

# طبّق كلّ الهجرات بترتيب MANIFEST (لا أبجديّ)
while IFS= read -r f; do
  f="$(echo "$f" | sed 's/#.*//' | xargs)"; [ -z "$f" ] && continue
  sudo -u postgres psql -v ON_ERROR_STOP=1 -q -d sahool -f "migrations/$f"
done < migrations/MANIFEST.txt

# دور التطبيق المقيَّد (RLS فعّال) + دور المهامّ (BYPASSRLS مقصود)
sudo -u postgres psql -d sahool -c "
  CREATE ROLE sahool_app LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS PASSWORD 'sahool_app_pw';
  GRANT USAGE ON SCHEMA public TO sahool_app; REVOKE CREATE ON SCHEMA public FROM sahool_app;
  GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO sahool_app;
  GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO sahool_app;
  GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app;
  CREATE ROLE sahool_jobs LOGIN NOSUPERUSER BYPASSRLS PASSWORD 'sahool_jobs_pw';
  GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO sahool_jobs;"
```
**نتيجة الجلسة:** 202 هجرة **0-خطأ** على المخطّط الإنتاجيّ الكامل (**304 جدول**) — تماسك السلسلة حيّ.

### أ.1 — عقد الأدوار (يجب أن يطابق)
```bash
sudo -u postgres psql -d sahool -c \
 "SELECT rolname,rolsuper,rolbypassrls,rolinherit FROM pg_roles WHERE rolname LIKE 'sahool_%' ORDER BY 1;"
```
**متوقَّع/مُصادَق:** `sahool_app` = super=f, bypassrls=f, **inherit=f** (IRR-F01) · `sahool_jobs` bypassrls=t (بالتصميم).

### أ.2 — FII RLS fail-closed حيّ (البرهان الأثمن)
```bash
PGPASSWORD=sahool_app_pw psql -h 127.0.0.1 -U sahool_app -d sahool -c "
  SELECT set_config('app.current_tenant','',false);
  INSERT INTO recommendations (tenant_id) VALUES ('00000000-0000-0000-0000-000000000001');"
```
**متوقَّع/مُصادَق:** `ERROR: new row violates row-level security policy for table "recommendations"`
(دور NOSUPERUSER/NOBYPASSRLS + سياق فارغ ⇒ رفض الكتابة). v192/v194 مُبرهنتان.

### أ.3 — AUTH-E2E تحت الدور المقيَّد — **مُغلَق live-certified 10/10 ✅**
```bash
export DATABASE_URL='postgresql://sahool_app:sahool_app_pw@127.0.0.1:5432/sahool'
export JOBS_DATABASE_URL='postgresql://sahool_jobs:sahool_jobs_pw@127.0.0.1:5432/sahool'
export JWT_SECRET='<سرّ ≥32 حرف>'  SAHOOL_AGENT_TOKEN='<توكن>'
python3 -m pytest tests_v9/test_auth_e2e.py -q     # يتخطّى نظيفاً بلا DB (integration)
```
**متوقَّع/مُصادَق:** register 201 (المُسجِّل = **owner** مؤسِّس مؤسّسته، لا farmer) · login 200 · /v1/auth/me 200 ·
كلمة مرور خاطئة 401 · تكرار بريد 409. (الاختبار يعمل تحت `sahool_app` عبر سياق admin على كلّ اتّصال pool.)

---

## القسم ب — mesh الخدمات الكامل (يحتاج بيئة المالك) — ⏳ محجوب هنا بمنع سِجِلّ الحاويات

> يتطلّب رفع الصور (Redis/NATS/PostGIS + بناء ~15 صورة خدمة). في بيئة بلا حجب سِجِلّ:

### ب.0 — الرفع
```bash
cp .env.example .env        # املأ الإلزاميّة: JWT_SECRET · SAHOOL_AGENT_TOKEN · REDIS_PASSWORD …
python scripts/runtime/env_doctor.py --mode preflight --format text   # يجب: ready
./scripts/production_validation_gate.sh
# البناء عبر المُغلِّف: TESTED_SHA تُشتقّ من HEAD (40 محرفاً) ويُرفض العمل المتّسخ.
# `.env.example` لم يعد يحمل قيمة TESTED_SHA — لا قيمة مُختلَقة، فالبناء المباشر
# بـ`up --build` سيفشل عند الاستيفاء وهذا مقصود.
make build-immutable            # أو: ./scripts/build-immutable.sh   (ويندوز: scripts/build-immutable.ps1)
docker compose -f docker-compose.v9.yml up -d
BASE_URL=http://localhost python scripts/runtime/env_doctor.py --mode runtime --format text
```

### ب.③ — تسليم reservation-dispatch عبر NATS (Gate B-d2-live)
عامل التتابُع (delivery-only، default-off، محاكاة-حتى-staging). فعّل الراية + راقب `decision_reservation_dispatch_inbox`
ينتقل pending→delivered عبر NATS. (المنطق مُصادَق وحدةً؛ الـE2E يحتاج NATS.)

### ب.④ — جسور sim-until-staging
water-deficit-bridge · lexicographic-mpc-bridge · reservation-dispatch — كلّها توصية-فقط، default-off.
شغّلها على staging وتحقّق من انتشار النَّسَب (content_digest/idempotency_key) عبر PostgreSQL/السلسلة.

### ب.⑤ — SoR flip (الجداول interim-bridge الخمسة)
`decision_record · dispatch_decisions · outcome_record · recommendation_outcomes · online_learning_updates`
حاليّاً platform-owned + mirror:decision-service. اتبع:
`docs/runbooks/DECISION_SERVICE_SOR_CUTOVER_RUNBOOK.md` (+ staging-probe + production-promotion).
بعد القلب: حدّث `db_ownership.yml` (owner=decision-service) — فحص `LOOP_TABLES⊆ownership` يبقى أخضر (بند mirror يصير redundant).

### ب.⑦ — أقمار 4/5 (satellite_cdse + raster)
تحقّق من مسار CDSE→backfill→raster_assets→validated product→`/vegetation/v1/ndvi/current` بمستأجِر حقيقيّ
(يحتاج SH_CLIENT_ID/SECRET + raster-service + object store).

---

## ملاحظات صدق
- **القسم أ مُصادَق حيّاً بالكامل** في جلسة 2026-07-18 على PG16+PostGIS أصليّ (لا محاكاة).
- **القسم ب محجوب في بيئة الجلسة** بسبب سياسة شبكة تمنع سِجِلّ الحاويات (Docker Hub 403) — لا بتقاعس.
  يُنفَّذ في بيئة المالك بلا حجب.
- المفاتيح/الأسرار من env فقط (لا قيَم حرفيّة في git). `ACTIVATION_EVIDENCE_SIGNING_KEY` يجب أن يكون
  سرّاً متمايزاً عن JWT_SECRET/SAHOOL_AGENT_TOKEN (ledger #3، محروس).
