-- v204: GAP-FIELD-FORMS-01 — النماذج الميدانيّة الديناميكية فوق B1 (الشريحة الأولى، خادميّة).
--
-- أربعة جداول جديدة يملكها scout-ingest-service (امتداد قرار SEASON-RECORD — لا مالك جديد).
-- القاعدة الحاكمة: أنبوب واحد — ExternalSubmissionEnvelopeV1 ثمّ تحقّقات النماذج فوق السبعة
-- (§12/§12.1). لا hard delete إطلاقًا على definitions/versions (التقاعد آلية الإزالة الوحيدة، §6).
--
-- FKs مركّبة بالمستأجِر على نمط v201 (§5): UNIQUE(tenant_id, id) على كلّ جدول مُشار إليه +
-- FOREIGN KEY (tenant_id, …) عند كلّ مرجع — تمنع cross-tenant references حتى مع خطأ كاتب مميَّز.
--
-- idempotent (IF NOT EXISTS / DROP IF EXISTS) — آمن لإعادة التطبيق كلّ إقلاع.

-- ── ٠) ممهِّد FK المركّب على external_submissions (PK على id وحده؛ يحتاج UNIQUE(tenant_id,id)) ──
CREATE UNIQUE INDEX IF NOT EXISTS ux_external_submissions_tenant_id
    ON external_submissions (tenant_id, id);

-- ── ١) field_form_definitions — التعريف (لا current_version_id: FK دائريّ + مصدر حقيقة ثانٍ، §5.1) ──
CREATE TABLE IF NOT EXISTS field_form_definitions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    code        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_definitions_tenant_code
    ON field_form_definitions (tenant_id, code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_definitions_tenant_id
    ON field_form_definitions (tenant_id, id);

-- ── ٢) field_form_versions — الإصدارات (immutability بالأعمدة + state machine + تقاعد بنمطين) ──
CREATE TABLE IF NOT EXISTS field_form_versions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    form_definition_id UUID NOT NULL,
    version_number     INT  NOT NULL CHECK (version_number >= 1),
    status             TEXT NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft','published','retired')),
    schema_json        JSONB NOT NULL,
    logic_json         JSONB,
    validation_rules   JSONB,
    localization       JSONB,
    schema_hash        TEXT NOT NULL,
    published_at       TIMESTAMPTZ,
    published_by       TEXT,
    retired_at         TIMESTAMPTZ,
    retired_by         TEXT,
    retirement_reason  TEXT,
    retirement_mode    TEXT CHECK (retirement_mode IN ('superseded','withdrawn')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- اتّساق التقاعد (§5.2 CHECK مكمّل للـtrigger): قبل التقاعد الأربعة NULL؛ بعده NOT NULL
    CHECK (
        (status <> 'retired' AND retirement_mode IS NULL AND retired_at IS NULL
            AND retired_by IS NULL AND retirement_reason IS NULL)
        OR
        (status = 'retired' AND retirement_mode IS NOT NULL AND retired_at IS NOT NULL
            AND retired_by IS NOT NULL AND retirement_reason IS NOT NULL)
    ),
    FOREIGN KEY (tenant_id, form_definition_id)
        REFERENCES field_form_definitions (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_versions_tenant_def_version
    ON field_form_versions (tenant_id, form_definition_id, version_number);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_versions_tenant_id
    ON field_form_versions (tenant_id, id);
-- نسخة منشورة واحدة فعّالة لكلّ تعريف (فهرس فريد جزئيّ — النشر معاملة واحدة: retire+publish)
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_versions_one_published
    ON field_form_versions (tenant_id, form_definition_id) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS ix_field_form_versions_schema_hash
    ON field_form_versions (tenant_id, schema_hash);

-- immutability بدقّة الأعمدة (§5.2) + state machine (§5.2) في trigger واحد:
--   - متى published_at IS NOT NULL: schema_json/logic_json/schema_hash/validation_rules/
--     localization/form_definition_id/version_number محظورة التعديل
--   - الانتقالات المسموحة فقط: draft→published→retired (لا published→draft، لا retired→published)
--   - published_at/by ثابتان بعد أوّل نشر · retired_at/by/reason/mode write-once
CREATE OR REPLACE FUNCTION field_form_versions_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- P0-1 (مراجعة PR #585): الإدخال يمرّ عبر state machine أيضًا — الصفّ يولد draft حصرًا
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'draft' THEN
      RAISE EXCEPTION 'field_form_versions: insert must start as draft (state machine applies to INSERT)';
    END IF;
    IF NEW.published_at IS NOT NULL OR NEW.published_by IS NOT NULL THEN
      RAISE EXCEPTION 'field_form_versions: publish metadata not allowed at insert';
    END IF;
    RETURN NEW;
  END IF;
  -- state machine: الانتقالات القانونيّة فقط
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT (
        (OLD.status = 'draft' AND NEW.status = 'published')
        OR (OLD.status = 'published' AND NEW.status = 'retired')
        OR (OLD.status = NEW.status)
    ) THEN
      RAISE EXCEPTION 'field_form_versions: illegal status transition % -> %', OLD.status, NEW.status;
    END IF;
  END IF;
  -- P0-1: النشر يتطلّب فاعلًا موثَّقًا — لا published بلا published_at/published_by
  IF OLD.status = 'draft' AND NEW.status = 'published' THEN
    IF NEW.published_at IS NULL OR NEW.published_by IS NULL THEN
      RAISE EXCEPTION 'field_form_versions: publish requires published_at and published_by';
    END IF;
  END IF;
  -- immutability بدقّة الأعمدة بعد أوّل نشر
  IF OLD.published_at IS NOT NULL THEN
    IF NEW.schema_json IS DISTINCT FROM OLD.schema_json
       OR NEW.logic_json IS DISTINCT FROM OLD.logic_json
       OR NEW.schema_hash IS DISTINCT FROM OLD.schema_hash
       OR NEW.validation_rules IS DISTINCT FROM OLD.validation_rules
       OR NEW.localization IS DISTINCT FROM OLD.localization
       OR NEW.form_definition_id IS DISTINCT FROM OLD.form_definition_id
       OR NEW.version_number IS DISTINCT FROM OLD.version_number THEN
      RAISE EXCEPTION 'field_form_versions: published content is immutable (column-precise)';
    END IF;
  END IF;
  -- published_at/by ثابتان بعد أوّل نشر
  IF OLD.published_at IS NOT NULL AND NEW.published_at IS DISTINCT FROM OLD.published_at THEN
    RAISE EXCEPTION 'field_form_versions: published_at is immutable after first publish';
  END IF;
  IF OLD.published_by IS NOT NULL AND NEW.published_by IS DISTINCT FROM OLD.published_by THEN
    RAISE EXCEPTION 'field_form_versions: published_by is immutable after first publish';
  END IF;
  -- حقول التقاعد write-once
  IF OLD.retired_at IS NOT NULL AND NEW.retired_at IS DISTINCT FROM OLD.retired_at THEN
    RAISE EXCEPTION 'field_form_versions: retired_at is write-once';
  END IF;
  IF OLD.retired_by IS NOT NULL AND NEW.retired_by IS DISTINCT FROM OLD.retired_by THEN
    RAISE EXCEPTION 'field_form_versions: retired_by is write-once';
  END IF;
  IF OLD.retirement_reason IS NOT NULL AND NEW.retirement_reason IS DISTINCT FROM OLD.retirement_reason THEN
    RAISE EXCEPTION 'field_form_versions: retirement_reason is write-once';
  END IF;
  IF OLD.retirement_mode IS NOT NULL AND NEW.retirement_mode IS DISTINCT FROM OLD.retirement_mode THEN
    RAISE EXCEPTION 'field_form_versions: retirement_mode is write-once';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_field_form_versions_guard ON field_form_versions;
CREATE TRIGGER trg_field_form_versions_guard
  BEFORE INSERT OR UPDATE ON field_form_versions
  FOR EACH ROW EXECUTE FUNCTION field_form_versions_guard();

-- ── ٣) field_form_assignments — الإسناد (revision يمنع الإنقاص؛ الغموض يفشل تطبيقيًّا) ──
-- لا UNIQUE(tenant,field,version,active_from) (وهميّ مع NULL/timezone) ولا exclusion constraint
-- في الشريحة الأولى (§5.3): الغموض عند التنزيل/الإرسال ⇒ ambiguous_active_assignment (fail-closed).
CREATE TABLE IF NOT EXISTS field_form_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    form_version_id UUID NOT NULL,
    field_id        TEXT NOT NULL,
    season_id       TEXT,
    active_from     TIMESTAMPTZ NOT NULL DEFAULT now(),
    active_to       TIMESTAMPTZ,
    revision        BIGINT NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, form_version_id)
        REFERENCES field_form_versions (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_form_assignments_tenant_id
    ON field_form_assignments (tenant_id, id);
CREATE INDEX IF NOT EXISTS ix_field_form_assignments_active
    ON field_form_assignments (tenant_id, field_id, form_version_id) WHERE active_to IS NULL;

CREATE OR REPLACE FUNCTION field_form_assignments_revision_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.revision < OLD.revision THEN
    RAISE EXCEPTION 'field_form_assignments: revision may not decrease';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_field_form_assignments_revision ON field_form_assignments;
CREATE TRIGGER trg_field_form_assignments_revision
  BEFORE UPDATE ON field_form_assignments
  FOR EACH ROW EXECUTE FUNCTION field_form_assignments_revision_guard();

-- ── ٤) field_submissions — الإرسالات (مرجع envelope إلزاميّ NOT NULL؛ §12.1) ──
-- UNIQUE(envelope_id) بسيط (one-to-one مع المظروف) + FK مركّب لأمان العزل (§5.4).
-- لا idempotency_key هنا: نقطة الديدوب الوحيدة في B1 (external_submissions).
-- لا unknown_quarantined في version_resolution_status: الإصدار المجهول لا يُنشئ صفًّا أصلًا (§12.1).
CREATE TABLE IF NOT EXISTS field_submissions (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id                 UUID NOT NULL,
    form_version_id           UUID NOT NULL,
    assignment_id             UUID,
    envelope_id               BIGINT NOT NULL,
    answers_json              JSONB NOT NULL,
    answers_hash              TEXT NOT NULL,
    source_payload_hash       TEXT NOT NULL,
    normalizer_version        TEXT NOT NULL,
    form_validation_status    TEXT NOT NULL
                              CHECK (form_validation_status IN ('valid','invalid','unknown_schema')),
    version_resolution_status TEXT NOT NULL
                              CHECK (version_resolution_status IN
                                  ('current','stale_proven','withdrawn_quarantined','invalid_sync_proof','no_active_assignment')),
    stale_version             BOOLEAN NOT NULL DEFAULT false,
    submitted_by              TEXT,
    submitted_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, envelope_id)
        REFERENCES external_submissions (tenant_id, id),
    FOREIGN KEY (tenant_id, form_version_id)
        REFERENCES field_form_versions (tenant_id, id),
    FOREIGN KEY (tenant_id, assignment_id)
        REFERENCES field_form_assignments (tenant_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_submissions_envelope
    ON field_submissions (envelope_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_field_submissions_tenant_id
    ON field_submissions (tenant_id, id);
CREATE INDEX IF NOT EXISTS ix_field_submissions_version
    ON field_submissions (tenant_id, form_version_id, submitted_at DESC);

-- ── ٥) RLS صريح على الأربعة (ENABLE + FORCE + DROP + CREATE ظاهر حرفيًّا — درس v9_append_only) ──
ALTER TABLE field_form_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_form_definitions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_form_definitions;
CREATE POLICY tenant_isolation ON field_form_definitions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE field_form_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_form_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_form_versions;
CREATE POLICY tenant_isolation ON field_form_versions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE field_form_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_form_assignments FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_form_assignments;
CREATE POLICY tenant_isolation ON field_form_assignments
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

ALTER TABLE field_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE field_submissions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON field_submissions;
CREATE POLICY tenant_isolation ON field_submissions
  USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))
  WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));

-- ── ٦) الصلاحيّات على دور runtime الفعليّ (sahool_ingest — §6/D2) ──
-- لا hard delete إطلاقًا على definitions/versions (التقاعد آلية الإزالة الوحيدة):
-- REVOKE DELETE على الجدولين كليًّا. الحذف يُمنع أيضًا بنيويًّا بـtrigger (دفاع عمق:
-- grants قد تُمنح لاحقًا؛ الـtrigger يمنع بصرف النظر — نمط v197).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sahool_ingest') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON field_form_definitions TO sahool_ingest';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON field_form_versions TO sahool_ingest';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE ON field_form_assignments TO sahool_ingest';
    EXECUTE 'GRANT SELECT, INSERT ON field_submissions TO sahool_ingest';
    EXECUTE 'REVOKE DELETE ON field_form_definitions FROM sahool_ingest';
    EXECUTE 'REVOKE DELETE ON field_form_versions FROM sahool_ingest';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION field_forms_forbid_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'field forms: hard DELETE prohibited — retirement is the only removal mechanism';
END;
$$;
DROP TRIGGER IF EXISTS trg_field_form_definitions_no_delete ON field_form_definitions;
CREATE TRIGGER trg_field_form_definitions_no_delete
  BEFORE DELETE ON field_form_definitions
  FOR EACH ROW EXECUTE FUNCTION field_forms_forbid_delete();
DROP TRIGGER IF EXISTS trg_field_form_versions_no_delete ON field_form_versions;
CREATE TRIGGER trg_field_form_versions_no_delete
  BEFORE DELETE ON field_form_versions
  FOR EACH ROW EXECUTE FUNCTION field_forms_forbid_delete();

COMMENT ON TABLE field_form_definitions IS
  'GAP-FIELD-FORMS-01: تعريفات النماذج الميدانيّة (tenant-RLS، لا current_version_id، لا hard delete). v204.';
COMMENT ON TABLE field_form_versions IS
  'GAP-FIELD-FORMS-01: إصدارات النماذج (immutability بالأعمدة + state machine draft→published→retired + retirement_mode superseded|withdrawn + نسخة منشورة واحدة). v204.';
COMMENT ON TABLE field_form_assignments IS
  'GAP-FIELD-FORMS-01: إسناد نموذج↔حقل (revision مانع للإنقاص؛ الغموض يفشل ambiguous_active_assignment تطبيقيًّا). v204.';
COMMENT ON TABLE field_submissions IS
  'GAP-FIELD-FORMS-01: إرسالات النماذج — envelope_id إلزاميّ UNIQUE (صفّ فقط لإصدار معروف، §12.1) + hashes تدقيقيّة + حالات مفصولة. v204.';
