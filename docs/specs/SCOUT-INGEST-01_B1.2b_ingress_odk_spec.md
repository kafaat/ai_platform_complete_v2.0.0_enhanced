# مواصفة SCOUT-INGEST-01 · B1.2b — المدخل + الاعتماد لكلّ مصدر + محوّل ODK

- **الحالة:** ⏳ مسودّة للمراجعة (لم تُنفَّذ) · **الهجرة:** v198 · **الراية:** `SCOUT_INGEST_ENABLED` (افتراضيّ off).
- **يسبقه:** B1.0 (العقد `1ac3411`) · B1.1 (التحقّق السباعي `0712a9b`) · B1.2a (v197 + resolver + برهان حيّ `20cfaa7`، CI أخضر #4247).

## 0 · النطاق والحدود
سطح ingress خارجيّ يحوّل إدخال ODK إلى صفّ `external_submissions` (B1.2a) عبر: **اعتماد لكلّ مصدر → EnvelopeV1 → التحقّق السباعي → resolve_dedup → تخزين بحالته**.
**لا إسقاط domain** (B1.3) · **لا Kobo** (B1.4) · **لا واجهة تسجيل**. خلف الراية.

## 1 · الهجرة v198 — `external_ingest_sources` (سجلّ تعيين control-plane)
يربط `(provider, server, form_id) → tenant_id` ويحمل **اعتماد كلّ مصدر** (hash فقط).

```sql
-- migrations/v198_external_ingest_sources.sql
CREATE TABLE IF NOT EXISTS external_ingest_sources (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    provider           TEXT NOT NULL,
    server             TEXT NOT NULL,
    form_id            TEXT NOT NULL,
    token_hash         TEXT NOT NULL,          -- sha256(scout_ingest_token) — لا التوكن نفسه أبداً
    mapping_version    TEXT NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT true,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, server, form_id)
);
CREATE INDEX IF NOT EXISTS ix_external_ingest_sources_token ON external_ingest_sources (token_hash);

-- كتابة إداريّة مقيَّدة بالمستأجِر (مالك المستأجِر يسجّل مصدره فقط): RLS FORCE + WITH CHECK.
ALTER TABLE external_ingest_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_ingest_sources FORCE ROW LEVEL SECURITY;   -- مسافة واحدة (درس CI #179)
DO $$ BEGIN
  EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON external_ingest_sources';
  EXECUTE 'CREATE POLICY tenant_isolation ON external_ingest_sources '
    'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
    'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))';
END $$;

-- **قرار (أ) — resolver آمن:** SECURITY DEFINER يحلّ token_hash → المستأجِر دون منح قراءة الجدول كاملاً.
-- يعيد **الصفّ المطابق المُفعَّل فقط** ⇒ المدخل يحلّ توكناً يملكه، ولا يُعدّد التعيينات.
CREATE OR REPLACE FUNCTION resolve_ingest_source(p_token_hash TEXT)
RETURNS TABLE(tenant_id UUID, provider TEXT, server TEXT, form_id TEXT, mapping_version TEXT)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT tenant_id, provider, server, form_id, mapping_version
    FROM external_ingest_sources
   WHERE token_hash = p_token_hash AND enabled = true
   LIMIT 1;
$$;
REVOKE ALL ON FUNCTION resolve_ingest_source(TEXT) FROM PUBLIC;   -- المنح للدور المقيَّد فقط (role setup)
```
**لماذا SECURITY DEFINER لا RLS-off:** لو مُنح `sahool_app` قراءةً كاملة على الجدول، لأمكنه تعداد كلّ تعيينات
المستأجرين. الدالّة تُقيّد الكشف إلى «توكن تملكه ⇒ مستأجرك» — والتوكن نفسه لا يُخزَّن (hash). `enabled=false` ⇒ لا صفّ ⇒ 403.

### 1.1 · مالك الدالّة (الحسم المانع — تفاعل SECURITY DEFINER مع FORCE RLS)
**المعضلة:** `FORCE ROW LEVEL SECURITY` يسري على مالك الجدول أيضاً؛ وSECURITY DEFINER يعمل بصلاحية **مالكها**.
والدالّة تُستدعى **قبل** ضبط `app.current_tenant` (غرضها). فلو كان مالكها خاضعاً لـFORCE ⇒ `NULLIF('','')=NULL` ⇒
صفر صفوف ⇒ كلّ توكن 403 = **سطح ميت (fail-closed لكن مكسور)**.

**الحسم:** دور تحكّم مخصّص **`sahool_ingest_resolver`** — `NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS` — يملك الدالّة
**فقط**، وله `SELECT` على `external_ingest_sources` **وحده** (SELECT ليس DML؛ وهو الحدّ الأدنى الذي تحتاجه الدالّة).
لا LOGIN (لا يتّصل)، لا superuser (لا تصعيد)، لا DML، لا جداول أخرى. هذا يُبقي:
- `sahool_app` على `NOBYPASSRLS` (لا نكسر ما صُدِّق حيّاً في IRR-F01 Gate A / NOINHERIT)،
- الدالّة تعمل قبل ضبط السياق (BYPASSRLS للمالك يتجاوز FORCE)،
- سطح التصعيد محصوراً في **دالّة SELECT واحدة محدّدة الأعمدة** يملكها دور لا يتّصل ولا يملك سوى SELECT على جدول واحد.

**موضع الإنشاء (يحترم عرف «لا إشارة أدوار في الهجرات» — الأدوار تُنشأ بعد الهجرات):**
- **v198** يُنشئ الدالّة SECURITY DEFINER + `REVOKE ALL ON FUNCTION resolve_ingest_source(TEXT) FROM PUBLIC` (بلا إشارة دور).
- **bootstrap** (`bootstrap_postgres.sh` + `apply_in_compose.sh`، حيث تُنشأ الأدوار) يضيف — بعد إنشاء الجدول والهجرات:
  ```sql
  CREATE ROLE sahool_ingest_resolver NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS NOCREATEDB NOCREATEROLE;  -- مشروط \gexec
  GRANT USAGE ON SCHEMA public TO sahool_ingest_resolver;
  GRANT SELECT ON external_ingest_sources TO sahool_ingest_resolver;   -- SELECT على الجدول الواحد فقط
  ALTER FUNCTION resolve_ingest_source(TEXT) OWNER TO sahool_ingest_resolver;
  ```
- **منح التنفيذ لـsahool_app (note #1، مثبَّت):** `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sahool_app`
  القائم في bootstrap (`:125`) يشمل `resolve_ingest_source` (bootstrap بعد الهجرات ⇒ الدالّة موجودة). نُبقيه صريحاً
  في bootstrap كي لا تُولَد الدالّة REVOKEدة-من-PUBLIC بلا ممنوح (⇒ 500 عند أوّل نداء).

**البرهان الحيّ (يحسم القرار لا يكتشفه CI):** بمالك `sahool_ingest_resolver` (BYPASSRLS) وبـ`app.current_tenant=''`،
`resolve_ingest_source(hash)` يعيد الصفّ المطابق؛ وبمالك خاضع لـFORCE (غير bypass) يعيد صفراً. كلاهما مُصادَق على PG16 أصليّ.

## 2 · المدخل (ingress) — اعتماد لكلّ مصدر (لا SAHOOL_AGENT_TOKEN المشترك)
راوتر جديد `api/routers/ingest.py`: `POST /internal/ingest/submissions/odk` (نمط `routers/internal_service.py`).
**لا** يستخدم `service_token_auth._require_service_token` (ذاك التوكن المشترك — خرقه يعرّض الجميع). بدلاً:
1. اقرأ ترويسة `X-Scout-Ingest-Token` — غائبة ⇒ **401**.
2. `token_hash = sha256(token)` → `SELECT * FROM resolve_ingest_source(token_hash)` — لا صفّ (غير معروف/معطَّل) ⇒ **403**.
3. المستأجِر + provider/server/form **من السجلّ لا من المُرسِل** (الهويّة لا تُقبل من المُرسِل).
4. محوّل ODK (`§3`) → `ExternalSubmissionEnvelopeV1`؛ `content_hash=sha256(raw)`؛ `idempotency_key=derive_dedup_key(...)`.
5. `set_config('app.current_tenant', <resolved>, false)` (session-scoped، درس raster-service) في نفس المعاملة.
6. استعلم الصفّ الموجود بـ`(tenant, idempotency_key)` → `existing_content_hash` → `resolve_dedup(...)` (B1.2a):
   - `insert_new` ⇒ شغّل التحقّق السباعي (B1.1، `is_duplicate=False`) ⇒ `trust_status=accepted` إن اجتاز، وإلّا `quarantined`+أسبابه ⇒ INSERT.
   - `idempotent_replay` ⇒ 200 (نفس `submission_id`)، لا تخزين مكرّر.
   - `quarantine_divergent` ⇒ INSERT بمفتاح مشتقّ + `quarantined` + `duplicate_key_divergent_payload`.
7. خلف `SCOUT_INGEST_ENABLED` (off ⇒ 404).

**قرار (حسم B1.2a): كاتب accepted** = اجتياز السبعة ⇒ `accepted` عند الإدراج (B1.3 يقرأ المقبول فقط).

## 3 · محوّل ODK Central
`api/ingest/odk_adapter.py`: ODK submission (JSON) → `ExternalSubmissionEnvelopeV1`. `raw_payload`=الخامّ كما وصل؛
`mapping_version` من السجلّ؛ التعيين (حقول الاستمارة → حمولة رصد مطبَّعة، محاذاة العنقود 4/ADR-0034) **مُصدَّر بنسخة**
(ملفّ mapping قابل للمراجعة — لا تعيين مُضمَّن سحريّ). دالّة نقيّة قابلة للاختبار (envelope in/out).

## 4 · التسجيل الإداريّ (مالك المستأجِر يسجّل مصدره)
توليد `scout_ingest_token` مرّة، عرضه مرّة، تخزين `sha256` فقط (نمط مفاتيح API). آليّة التسجيل:
- **قرار (ج):** نقطة إداريّة رفيعة `POST /api/v1/ingest/sources` (صلاحية مالك المستأجِر، تحت سياقه ⇒ RLS WITH CHECK يمنع تسجيله لمستأجِر آخر) — أو أداة ops. **توصية:** نقطة رفيعة الآن (فعل إداريّ بصلاحية، لا استنتاج تشغيليّ).

## 5 · الحُرّاس والبراهين
**ساكنة (unit):**
1. **المدخل بلا التوكن المشترك:** حارس أنّ `routers/ingest.py` لا يستورد `_require_service_token` ولا يقرأ `SAHOOL_AGENT_TOKEN` (يمنع انزلاق السطح للتوكن المشترك).
2. **session-GUC `false`** على كتابة المدخل (نمط `test_tenant_guc_session_scope_guard`).
3. **v198 RLS حرفيّ** + `resolve_ingest_source` = SECURITY DEFINER (حارس ساكن) + تزامن المُشغّلَين + db_ownership.
4. محوّل ODK نقيّ: اختبار envelope-in/out + mapping_version مثبَّت.

**حيّة (integration، على PG16 أصليّ — الأداة متاحة):**
5. **برهان الاعتماد المنفصل (المطلوب):** سجّل مصدرَي (tenant A، tenant B)؛ **عطّل A ⇒ توكن A يعيد 403، توكن B يعمل**؛ توكن مجهول ⇒ 403؛ بلا توكن ⇒ 401. (إبطال مصدر = سطر، لا يمسّ غيره.)
6. المسار الكامل: توكن صحيح ⇒ صفّ `accepted` تحت المستأجِر الصحيح؛ divergent ⇒ `quarantined`؛ RLS يبقى fail-closed بسياق فارغ.

## 6 · بوّابات الالتزام (مع درسَي CI)
`ruff` · **`pytest -m unit` الكامل** (درس #179 — لا الملفّات الجديدة وحدها؛ يمسح كلّ الهجرات + حُرّاس RLS المتقاطعة) ·
**تسجيل كلّ `.py` جديد تحت `services/sahool-platform/` في `platform_python_module_baseline.json`** (درس #178) ·
`production_validation_gate.sh` (migration) · `build_release_bundle`+`validate` · regen inventory · تحديث الدماغ.

## 7 · ما ليس في B1.2b
لا إسقاط domain (B1.3) · لا Kobo (B1.4) · لا واجهة. مدخل + اعتماد لكلّ مصدر + محوّل + تخزين بحالته، خلف راية.

## نقاط القرار للمراجعة (ثلاث)
- **(أ)** `external_ingest_sources`: RLS إداريّة + `resolve_ingest_source` SECURITY DEFINER (لا يعدّد التعيينات) — **توصية**، مقابل جدول control-plane مكشوف القراءة.
- **(ب)** ترويسة `X-Scout-Ingest-Token` (لكلّ مصدر) بدل `X-Agent-Token` المشترك.
- **(ج)** التسجيل عبر نقطة إداريّة رفيعة بصلاحية المالك (تحت سياقه) — **توصية** — مقابل أداة ops فقط.
