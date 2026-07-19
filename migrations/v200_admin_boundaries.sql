-- v200: A7 — طبقة الحدود الإداريّة اليمنيّة (admin1 محافظات + admin2 مديريّات) كمرجع مشترك.
--
-- **أوّل جدول مرجع مشترك (shared-reference) مُعلَن في المنصّة:** طبقة خريطة عامّة يقرؤها كلّ المستأجرين
-- **لا بيانات مستأجِر** — فلا عمود ``tenant_id`` ولا RLS-مستأجِر (لا معنى لها). العزل هنا **قراءة-عامّة/
-- كتابة-محمِّل**: sahool_app يُمنَح SELECT فقط (تُنزَع INSERT/UPDATE/DELETE في bootstrap)؛ الكتابة عبر
-- المُحمِّل الموثَّق (مشغّل، صلاحية إداريّة). سابقة الجدول العالميّ: ``weather_automation_locations``
-- (tests_v9/test_rls_fk_isolated_tables.py). المالك: gis-workflow-service (db_ownership.yml).
--
-- **لا حدّ بلا مصدر:** كلّ صفّ يشير إلى ``admin_boundaries_source`` (source/version/license/url/retrieved_at).
-- **سلامة الهندسة كسمة:** trigger يرفض هندسة غير صالحة (المُحمِّل يُصلِح بـST_MakeValid ويسجّل العدد) —
-- هندسة مكسورة في مرجع تلوّث كلّ ST_AsSVG وjoin مكانيّ downstream. يتطلّب PostGIS (geometry).

-- ── سجلّ مرجعيّة المصدر (provenance، صفّ لكلّ مستوى إداريّ لكلّ تحميل) ──
CREATE TABLE IF NOT EXISTS admin_boundaries_source (
    source_id              BIGSERIAL PRIMARY KEY,
    admin_level            SMALLINT NOT NULL CHECK (admin_level IN (1, 2)),
    source                 TEXT NOT NULL,               -- مثلاً "HDX/OCHA Yemen COD-AB"
    dataset_version        TEXT NOT NULL,               -- إصدار مجموعة HDX كما لحظة الجلب
    license_title          TEXT NOT NULL,               -- عنوان الرخصة كما في صفحة HDX (قد يتغيّر بين الإصدارات)
    license_url            TEXT NOT NULL,
    url                    TEXT NOT NULL,               -- رابط HDX المصدر
    retrieved_at           TIMESTAMPTZ NOT NULL,        -- لحظة الجلب الفعليّة
    feature_count          INTEGER NOT NULL DEFAULT 0,
    invalid_geometry_fixed INTEGER NOT NULL DEFAULT 0,  -- عدد الهندسات المُصلَّحة بـST_MakeValid (شفافيّة)
    loaded_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── طبقة الحدود (مرجع مشترك، بلا tenant_id) ──
CREATE TABLE IF NOT EXISTS admin_boundaries (
    id             BIGSERIAL PRIMARY KEY,
    admin_level    SMALLINT NOT NULL CHECK (admin_level IN (1, 2)),  -- 1=محافظة، 2=مديريّة
    admin_code     TEXT NOT NULL,                       -- رمز HDX (pcode) — هويّة مستقرّة
    admin_name_ar  TEXT,
    admin_name_en  TEXT,
    parent_code    TEXT,                                -- admin2 → admin1 pcode (سياق التسلسل)
    geom           geometry(MultiPolygon, 4326) NOT NULL,
    source_id      BIGINT NOT NULL REFERENCES admin_boundaries_source(source_id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (admin_level, admin_code)                    -- تحميل idempotent (ON CONFLICT)
);
CREATE INDEX IF NOT EXISTS gix_admin_boundaries_geom ON admin_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_admin_boundaries_level_parent
    ON admin_boundaries (admin_level, parent_code);

-- سلامة الهندسة كسمة بنيويّة: يُرفَض إدراج/تحديث هندسة غير صالحة (المُحمِّل يُصلِح مسبقاً).
CREATE OR REPLACE FUNCTION admin_boundaries_require_valid_geom() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.geom IS NULL OR NOT ST_IsValid(NEW.geom) THEN
    RAISE EXCEPTION 'admin_boundaries: invalid geometry rejected (fix with ST_MakeValid in the loader)';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_admin_boundaries_valid_geom ON admin_boundaries;
CREATE TRIGGER trg_admin_boundaries_valid_geom
  BEFORE INSERT OR UPDATE ON admin_boundaries
  FOR EACH ROW EXECUTE FUNCTION admin_boundaries_require_valid_geom();

COMMENT ON TABLE admin_boundaries IS
  'A7 shared-reference: Yemen admin1/admin2 boundaries (public read for all tenants, no tenant_id). '
  'Loader-only writes; app role is SELECT-only (bootstrap revoke). Owner: gis-workflow-service. v200.';
COMMENT ON TABLE admin_boundaries_source IS
  'A7 provenance for admin_boundaries — no boundary without source/version/license/url. v200.';
