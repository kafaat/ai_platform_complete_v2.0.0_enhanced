# مواصفة SCOUT-INGEST-01 · B1.2 — migration + عقد RLS + مدخل ingress + محوّل ODK

- **الحالة:** ⏳ مسودّة للمراجعة (لم تُنفَّذ) · **الهجرة:** v197 · **الراية:** `SCOUT_INGEST_ENABLED` (افتراضيّ off) حتى التحقّق التكامليّ.
- **يسبقه:** B1.0 (العقد المحايد، `1ac3411`) · B1.1 (التحقّق السباعي، `0712a9b`).

## 0 · النطاق والحدود
يضيف **تخزين الإدخال الخارجيّ (خامّ محفوظ) + RLS + مدخل ingress + محوّل ODK Central**. **لا إسقاط domain** (ذاك B1.3).
تدفّق B1.2: `external submission → ODK adapter → EnvelopeV1 (B1.0) → validate السبعة (B1.1) → صفّ في external_submissions بحالته`.

## 1 · الهجرة v197 (جدول واحد + حالة)
**قرار تصميميّ (أ):** جدول **واحد** `external_submissions` يحمل `trust_status` + `quarantine_reasons`، بدل جدول quarantine منفصل —
الخامّ يبقى **في مكانه** (raw محفوظ) والحالة سمة لا كيان.

```sql
-- migrations/v197_external_submissions_ingest.sql
CREATE TABLE IF NOT EXISTS external_submissions (
    id                 BIGSERIAL PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    submission_id      TEXT NOT NULL,
    provider           TEXT NOT NULL,
    server             TEXT NOT NULL,
    form_id            TEXT NOT NULL,
    instance_id        TEXT NOT NULL,
    content_hash       TEXT NOT NULL,               -- sha256 للخامّ
    idempotency_key    TEXT NOT NULL,               -- = derive_dedup_key (B1.0)
    submitted_at       TIMESTAMPTZ NOT NULL,
    received_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_ref            TEXT NOT NULL,
    raw_payload        JSONB NOT NULL,              -- الخامّ محفوظ (الوصول ≠ الثقة)
    mapping_version    TEXT NOT NULL,               -- mapping مُصدَّر
    normalized_payload JSONB NOT NULL,              -- محاذاة العنقود 4 (ADR-0034)
    trust_status       TEXT NOT NULL DEFAULT 'untrusted'
                       CHECK (trust_status IN ('untrusted','accepted','quarantined')),
    quarantine_reasons TEXT[] NOT NULL DEFAULT '{}',  -- check_ids الفاشلة (B1.1)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- dedup بنيويّ مقيّد بالمستأجِر (يتّسق مع RLS):
CREATE UNIQUE INDEX IF NOT EXISTS ux_external_submissions_dedup
    ON external_submissions (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS ix_external_submissions_accepted
    ON external_submissions (tenant_id, trust_status) WHERE trust_status = 'accepted';

-- عقد RLS (نمط v155/v192 الحرفيّ: FORCE + USING + WITH CHECK):
ALTER TABLE external_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_submissions FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON external_submissions
    USING      (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- الأدوار المقيَّدة: كتابة/قراءة بلا حذف (الخامّ غير قابل للمحو):
GRANT SELECT, INSERT, UPDATE ON external_submissions TO sahool_app;
GRANT USAGE, SELECT ON SEQUENCE external_submissions_id_seq TO sahool_app;
-- (لا GRANT DELETE — raw immutable)
```

## 2 · التزامن الإلزاميّ للمُشغّلَين
- `migrations/MANIFEST.txt`: أضِف `v197_external_submissions_ingest.sql`.
- `scripts_v9/run_migrations.sql`: أضِف الخطوة `203. v197_...` (`\echo` + `\i`).
- حارس `tests_v9/test_migration_runners_in_sync_20260705.py` يبقى أخضر (يلتقطها تلقائيّاً).
- **`bash scripts/production_validation_gate.sh` محليّاً** (مُشغّل main-only — يؤكّد تطابق المُشغّلَين وسلامة السلسلة).

## 3 · مِلكيّة القاعدة
**قرار (ج):** `docs/architecture/db_ownership.yml`: `external_submissions` owner=**platform** (المدخل في المنصّة اليوم).
ملاحظة: ينتقل لخدمة ingest مستقلّة لاحقاً إن لزم.

## 4 · المدخل (ingress) — توكن خدمة لا JWT مستخدم
- نقطة داخليّة `POST /internal/ingest/submissions/odk` (نمط `service_token_auth.py` — لا `get_current_user`).
- **قرار (ب) — ربط المستأجِر (نقطة أمنيّة حرِجة):** المستأجِر لا يأتي من المُرسِل — يُشتقّ من **سجلّ تعيين** يربط
  `(provider, server, form_id) → tenant_id` (هو نفسه فحص `form_mapping_registered`). لا مستأجِر مُستنتَج من الحمولة.
  **من يملأ السجلّ؟** مالك المستأجِر عند تسجيل خادم ODK خاصّته (الوصول ≠ الثقة يمتدّ إلى هويّة المستأجِر).
- idempotent: `INSERT ... ON CONFLICT (tenant_id, idempotency_key) DO NOTHING` ⇒ تكرار = 200 صامت.
- الكتابة تُعيّن `set_config('app.current_tenant', <resolved>, false)` (**session-scoped `false`** — درس raster-service) قبل الإدراج (RLS WITH CHECK).
- خلف `SCOUT_INGEST_ENABLED` (افتراضيّ off).

## 5 · محوّل ODK Central
- `services/.../ingest/odk_adapter.py`: ODK submission (XML/JSON) → `ExternalSubmissionEnvelopeV1`؛ `content_hash=sha256(raw)`؛
  `mapping_version` مثبَّت؛ `raw_payload` = الخامّ كما وصل.
- التعيين **مُصدَّر بنسخة** (ملفّ mapping قابل للمراجعة) — لا تعيين مُضمَّن سحريّ.

## 6 · الحُرّاس (لكلّ بند برهانه)
1. **RLS حرفيّ** (نمط v140/v192): اختبار ساكن يؤكّد `FORCE` + `WITH CHECK` + `current_setting('app.current_tenant')` على `external_submissions`.
2. **تزامن المُشغّلَين**: الحارس القائم (يلتقط v197 في الملفّين).
3. **session-scoped GUC**: حارس ساكن أنّ إدراج المدخل يُعيّن `app.current_tenant` بـ`false` (نمط `test_tenant_guc_session_scope_guard`).
4. **لا حذف**: حارس أنّ الهجرة لا تمنح `DELETE` على `external_submissions` (raw immutable).
5. **مدخل بلا JWT مستخدم**: حارس أنّ نقطة الـingress تستخدم توكن الخدمة لا `get_current_user`.
6. **تكامليّ** (`-m integration`، بعد رفع PG): تحت `sahool_app` بسياق فارغ ⇒ الإدراج **يُرفَض** (RLS fail-closed)؛
   بسياق صحيح ⇒ يُقبَل؛ تكرار ⇒ ON CONFLICT صامت؛ إدخال يفشل فحصاً ⇒ صفّ `trust_status='quarantined'` بأسبابه، **بلا إسقاط**.

## 7 · بوّابات الالتزام
`pytest -m unit` · ruff · `build_release_bundle`+`validate` · **`production_validation_gate.sh` محليّاً** (migration) · regen inventory · تحديث الدماغ.

## 8 · ما ليس في B1.2
لا إسقاط إلى `scouting_pins`/`observations` (B1.3) · لا Kobo (B1.4) · لا واجهة. **تخزين + تحقّق + quarantine فقط، خلف راية.**

## نقاط القرار للمراجعة (ثلاث)
- **(أ)** جدول واحد بحالة مقابل جدولَي submissions+quarantine — **توصية: الواحد** (الخامّ في مكانه، الحالة سمة لا كيان).
- **(ب)** ربط المستأجِر عبر سجلّ تعيين `(provider,server,form)→tenant` — لا مستأجِر من المُرسِل. **يملؤه مالك المستأجِر عند تسجيل خادم ODK**.
- **(ج)** مِلكيّة platform الآن مقابل خدمة ingest مستقلّة لاحقاً — **توصية: platform الآن، ترحيل مؤجَّل**.
