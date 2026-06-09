"""
storage.lite_store
==================
الطبقة الخفيفة القابلة للتطوّر — ذاكرة المنصة.

قرار معماري (يتبع إجماع النقدين): SQLite لا Qdrant/Kafka/PostgreSQL الآن.
"بناء كوخ متين ثم توسعته" — لا "كاتدرائية لقرية صغيرة".
SQLite كافٍ حتى ~100 مزرعة. الترقية لـ PostgreSQL/TimescaleDB لاحقاً عند الحاجة.

ثلاثة جداول فقط (الحد الأدنى القابل للتعلّم):
  observations    — قراءات المراصد الحية (مرتبطة بالمصفوفة)
  yield_records   — الحصاد الفعلي (مصدر الحقيقة G1)
  recommendations — التوصيات + نتائجها (الذاكرة التي تُمكّن التعلّم)
  knowledge_snippets — معرفة عربية مهيكلة (بديل RAG البسيط، بحث بالكلمات)

لا embeddings، لا GPU. بحث نصي بسيط في knowledge_snippets.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "sahool.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    district_id   TEXT NOT NULL,
    zone_id     TEXT,
    observable_id TEXT NOT NULL,      -- links to observation_matrix (C1, S3...)
    value       REAL,
    value_text  TEXT,                 -- for categorical (O1, I6...)
    unit        TEXT,
    measured_at TEXT NOT NULL,        -- ISO date
    source      TEXT                  -- sensor / lab / manual / model / imported
        CHECK (source IS NULL OR source IN ('sensor','lab','manual','model','imported')),
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_obs_tenant ON observations(tenant_id, observable_id);
CREATE INDEX IF NOT EXISTS idx_obs_temporal ON observations(tenant_id, observable_id, measured_at);

CREATE TABLE IF NOT EXISTS yield_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL,
    district_id    TEXT NOT NULL,
    zone_id      TEXT,
    crop         TEXT NOT NULL,
    variety      TEXT,
    season_year  INTEGER NOT NULL,
    planting_date TEXT,
    harvest_date  TEXT,
    yield_t_ha   REAL NOT NULL,       -- ground truth (G1)
    verified     INTEGER DEFAULT 0,   -- weighed & confirmed
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_yield_district ON yield_records(district_id, crop);

CREATE TABLE IF NOT EXISTS recommendations (
    rec_id       TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    district_id    TEXT NOT NULL,
    zone_id      TEXT,
    crop         TEXT,
    issued_date  TEXT NOT NULL,
    recommendation_ar TEXT,
    quality_grade TEXT,               -- HIGH/MEDIUM/LOW/BLOCKED
    predicted_yield_t_ha REAL,        -- NULL if pending calibration
    confidence   TEXT,
    actual_yield_t_ha REAL,           -- filled after harvest
    error_pct    REAL,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id    TEXT,                -- NULL = applies everywhere
    crop         TEXT,                -- NULL = all crops
    topic        TEXT NOT NULL,       -- salinity / irrigation / pest...
    content_ar   TEXT NOT NULL,
    citation     TEXT NOT NULL,       -- source — no claim without source
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_know_topic ON knowledge_snippets(topic, district_id);

CREATE TABLE IF NOT EXISTS farmer_knowledge (
    knowledge_id TEXT PRIMARY KEY,
    knowledge_type TEXT NOT NULL,     -- spatial/temporal/varietal/practice/causal
    content_ar   TEXT NOT NULL,
    tenant_id    TEXT NOT NULL,
    district_id    TEXT NOT NULL,
    spatial_scope TEXT,               -- field / zone / specific spot
    farmer_confidence TEXT,           -- the farmer's own confidence
    mechanism_ar TEXT,                -- proposed physical mechanism
    verification_method TEXT,         -- ndvi / lab / trial
    verification_status TEXT DEFAULT 'pending',
    data_agreement INTEGER,           -- NULL unknown, 1 agrees, 0 contradicts
    review_year  INTEGER,             -- climate-drift review date
    source_ar    TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fk_district ON farmer_knowledge(district_id, knowledge_type);

CREATE TABLE IF NOT EXISTS variety_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL,
    district_id    TEXT NOT NULL,
    variety_ar   TEXT NOT NULL,       -- العلس / الحميري / سخا
    crop         TEXT NOT NULL,
    trait_tested TEXT,                -- drought / salinity / yield
    season_year  INTEGER,
    result_ar    TEXT,                -- what the trial showed
    verified_by  TEXT,               -- farmer_obs / lab / dna / yield_record
    dna_verified INTEGER DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now'))
);

-- ── الفجوة #6: تخزين حالة الحقل (لا حسابها فقط) ──
CREATE TABLE IF NOT EXISTS field_state (
    field_id     TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,           -- عزل المستخدمين (multi-tenant)
    quality_state TEXT NOT NULL DEFAULT 'blocked'
        CHECK (quality_state IN ('blocked','limited','pending_lab','ready')),
    soil_choice  TEXT,                    -- provided / skip / request_lab
    soil_skip_reason TEXT,                -- سبب التخطّي (مراجعة #6): تكلفة / لاحقاً...
    supervisor_id TEXT,                   -- المسؤول (مراجعة #2)
    supervisor_role TEXT                  -- observer / manager / owner
        CHECK (supervisor_role IS NULL OR supervisor_role IN ('observer','manager','owner')),
    completeness INTEGER DEFAULT 0,       -- 0-100 (data_completeness)
    updated_at   TEXT DEFAULT (datetime('now'))
);

-- ── مراجعة #1: إعداد نظام الري (الفجوة الأكبر) ──
CREATE TABLE IF NOT EXISTS irrigation_configs (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id     TEXT NOT NULL,
    tenant_id    TEXT NOT NULL,
    method       TEXT CHECK (method IN ('pivot','drip','sprinkler','flood','subsurface','none')),
    pivot_length_m  REAL,
    pivot_radius_m  REAL,
    flow_rate_lps   REAL,                 -- لتر/ثانية
    schedule_json   TEXT,                 -- {"mon":"06:00-08:00",...}
    water_source    TEXT,                 -- groundwater / surface / mixed
    created_at   TEXT DEFAULT (datetime('now'))
);

-- ── مراجعة #5: جدول المستخدمين المبسّط (توضيح آلية الحسابات) ──
-- tenant_id = معرّف المزرعة/المستخدم · district_id = المديرية (al_jawf...)
CREATE TABLE IF NOT EXISTS users (
    tenant_id    TEXT PRIMARY KEY,        -- = معرّف المزرعة (unique per farm)
    display_name TEXT,
    phone        TEXT,
    district_id  TEXT,                    -- المديرية التي تتبعها المزرعة
    role         TEXT DEFAULT 'owner'
        CHECK (role IN ('observer','manager','owner')),
    created_at   TEXT DEFAULT (datetime('now'))
);

-- ── الفجوة #9: طلبات المعمل + حدث استلام النتائج ──
CREATE TABLE IF NOT EXISTS lab_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id     TEXT NOT NULL,
    tenant_id    TEXT NOT NULL,
    requested_at TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'pending'
        CHECK (status IN ('pending','received','cancelled')),
    received_at  TEXT,                    -- يُملأ عند LAB_RESULTS_RECEIVED
    notified     INTEGER DEFAULT 0,       -- أُرسل إشعار "النتائج جاهزة"؟
    lon          REAL,                    -- موقع أخذ العيّنة (Geo-tag، 2026-05-27)
    lat          REAL,                    -- مفيد لخريطة العيّنات + قرار المعمل
    sample_purpose TEXT                   -- nutrient / salinity / texture / ph
);

-- ── سلسلة زمنية للـraster (timeline في الواجهة، 2026-05-27) ──
-- نحفظ مرجعاً (path في tenants/<id>/rasters/) لا الـblob نفسه:
--  • GeoTIFF خام كبير (MB-GB) — في الملفات، يجلبه الموصل عند الحاجة
--  • PNG معالَج (KB) — يُحفظ كـblob اختيارياً لـoffline-first
-- هذا يدعم شريط الـtimeline بدون تضخّم DB.
CREATE TABLE IF NOT EXISTS raster_snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    field_id     TEXT NOT NULL,
    indicator    TEXT NOT NULL,          -- ndvi / ndmi / bivariate
    captured_at  TEXT NOT NULL,          -- تاريخ الاستشعار (لا التخزين)
    source       TEXT NOT NULL           -- sentinel2 / landsat / planet / drone
        CHECK (source IN ('sentinel2','landsat','planet','drone','manual')),
    cloud_pct    REAL,                   -- نسبة السحاب (تأثير الجودة)
    bounds_json  TEXT NOT NULL,          -- {south,west,north,east} JSON
    width_px     INTEGER,
    height_px    INTEGER,
    geotiff_path TEXT,                   -- مسار GeoTIFF الخام في tenants/
    png_blob     BLOB,                   -- PNG معالَج (للعرض السريع/offline)
    coverage_pct REAL,                   -- % بكسل معروف (الصدق البصري)
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snap_field_time
    ON raster_snapshots(tenant_id, field_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_snap_indicator
    ON raster_snapshots(tenant_id, indicator, captured_at);

-- ── الفجوة #1: تسجيل الموافقة (مبسّط — لا INET/SAR مبالغ) ──
CREATE TABLE IF NOT EXISTS user_consent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL,
    consent_type TEXT NOT NULL,           -- data_governance / terms / privacy
    version      TEXT NOT NULL,
    accepted_at  TEXT DEFAULT (datetime('now')),
    withdrawn_at TEXT
);

-- ── سجلّ أنشطة المزرعة (مستلهَم من farmOS Log entity، 2026-05-27) ──
-- يحلّ فجوة الحلقة المغلقة: توصية → مهمّة → تنفيذ → سجلّ → تعلّم.
-- observations يحفظ القياسات (NDVI=0.5)؛ هذا يحفظ الأنشطة ("رويت 20مم").
-- يربط بـrecommendations عبر rec_id (اختياري) لتغذية implementation_verification.
CREATE TABLE IF NOT EXISTS activity_log (
    activity_id  TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL,
    field_id     TEXT NOT NULL,
    rec_id       TEXT,                    -- اختياري: ربط بالتوصية
    activity_type TEXT NOT NULL
        CHECK (activity_type IN
            ('irrigation','fertilization','pesticide','seeding','harvest',
             'pruning','weeding','observation','other')),
    status       TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','in_progress','completed','cancelled','skipped')),
    planned_date TEXT,                    -- متى يجب أن يحدث
    completed_date TEXT,                  -- متى حدث فعلاً (يُملأ عند completed)
    quantity     REAL,                    -- مم للري، كغ/هـ للسماد...
    unit         TEXT,                    -- mm, kg/ha, L/ha, doses
    notes_ar     TEXT,                    -- ملاحظة المزارع
    skip_reason  TEXT,                    -- إن status=skipped (يغذّي farmer_agency)
    lon          REAL,                    -- إحداثي اختياري (Geo-tag للنشاط)
    lat          REAL,                    -- مفيد لتنفيذ في زاوية الحقل لا كلّه
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (rec_id) REFERENCES recommendations(rec_id)
);
CREATE INDEX IF NOT EXISTS idx_activity_tenant_field
    ON activity_log(tenant_id, field_id, planned_date);
CREATE INDEX IF NOT EXISTS idx_activity_status
    ON activity_log(tenant_id, status, planned_date);

-- مراجعة v9.1 #16: تحديث updated_at تلقائياً (بدل التحديث اليدوي)
CREATE TRIGGER IF NOT EXISTS trg_field_state_updated
AFTER UPDATE ON field_state
FOR EACH ROW
BEGIN
    UPDATE field_state SET updated_at = datetime('now') WHERE field_id = NEW.field_id;
END;

-- تحديث updated_at لـactivity_log أيضاً
CREATE TRIGGER IF NOT EXISTS trg_activity_updated
AFTER UPDATE ON activity_log
FOR EACH ROW
BEGIN
    UPDATE activity_log SET updated_at = datetime('now') WHERE activity_id = NEW.activity_id;
END;
"""


@contextmanager
def connect(db_path: Path = DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # مراجعة v9.1 #2 + #14: تفعيل المفاتيح الأجنبية ومهلة التزامن.
    # (ملاحظتان صحيحتان من المراجعة — تنطبقان على كودنا فعلاً)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")  # 5 ثوانٍ — يمنع أخطاء القفل
    # WAL mode (مراجعة 2026-05-27): يُحسّن التزامن جذرياً، يسمح بقراءة
    # متزامنة مع كتابة واحدة (بدل قفل قاعدة كاملة). حيوي عند الذروة
    # (عدة مزارعين/إشعارات في آنٍ واحد). يُكتب مرّة في bootstrap لكن
    # نضبطه هنا أيضاً (idempotent) لضمان التطبيق.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")   # مع WAL آمن وأسرع
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


# ── observations ─────────────────────────────────────────────
# المعرّفات الصالحة من مصفوفة المشاهدات (تحقّق اختياري — مراجعة #6)
_VALID_OBSERVABLES: set[str] | None = None


def _load_valid_observables() -> set[str]:
    """يحمّل المعرّفات الصالحة (C1, S3...) من observation_matrix.yaml مرّة واحدة."""
    global _VALID_OBSERVABLES
    if _VALID_OBSERVABLES is None:
        import yaml
        mpath = Path(__file__).parent.parent / "core" / "observation_matrix.yaml"
        try:
            m = yaml.safe_load(open(mpath, encoding="utf-8"))
            obs = m.get("observables", {})
            _VALID_OBSERVABLES = set(obs.keys() if isinstance(obs, dict)
                                     else (o["id"] for o in obs))
        except Exception:
            _VALID_OBSERVABLES = set()  # غياب الملف لا يكسر — التحقّق يُتخطّى
    return _VALID_OBSERVABLES


def add_observation(tenant_id, district_id, observable_id, measured_at,
                    value=None, value_text=None, unit=None, source=None,
                    zone_id=None, validate=True, db_path: Path = DEFAULT_DB) -> None:
    """يضيف مشاهدة. مراجعة #6: يتحقّق أن observable_id معرّف في المصفوفة
    (يمنع 'S99' الخاطئ) — قابل للإيقاف بـ validate=False."""
    if validate:
        valid = _load_valid_observables()
        if valid and observable_id not in valid:
            raise ValueError(f"observable_id غير معرّف في المصفوفة: {observable_id!r}")
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO observations
               (tenant_id, district_id, zone_id, observable_id, value, value_text,
                unit, measured_at, source)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (tenant_id, district_id, zone_id, observable_id, value, value_text,
             unit, measured_at, source),
        )


def get_observations(tenant_id=None, observable_id=None, district_id=None,
                     since=None, db_path: Path = DEFAULT_DB) -> list[dict]:
    """يقرأ المشاهدات بمرشّحات اختيارية. الدالة المفقودة (كان add فقط)."""
    sql = "SELECT * FROM observations WHERE 1=1"
    params = []
    if tenant_id is not None:
        sql += " AND tenant_id = ?"; params.append(tenant_id)
    if observable_id is not None:
        sql += " AND observable_id = ?"; params.append(observable_id)
    if district_id is not None:
        sql += " AND district_id = ?"; params.append(district_id)
    if since is not None:
        sql += " AND measured_at >= ?"; params.append(since)
    sql += " ORDER BY measured_at DESC"
    with connect(db_path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ── yield records (ground truth) ─────────────────────────────
def add_yield(tenant_id, district_id, crop, season_year, yield_t_ha,
             variety=None, zone_id=None, planting_date=None, harvest_date=None,
             verified=True, db_path: Path = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO yield_records
               (tenant_id, district_id, zone_id, crop, variety, season_year,
                planting_date, harvest_date, yield_t_ha, verified)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, district_id, zone_id, crop, variety, season_year,
             planting_date, harvest_date, yield_t_ha, 1 if verified else 0),
        )


def yields_for_district(district_id, crop=None, db_path: Path = DEFAULT_DB) -> list[dict]:
    with connect(db_path) as conn:
        q = "SELECT * FROM yield_records WHERE district_id=? AND verified=1"
        params = [district_id]
        if crop:
            q += " AND crop=?"; params.append(crop)
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def independent_units(district_id, crop=None, db_path: Path = DEFAULT_DB) -> dict:
    """Count farms x seasons — the honest effective sample size."""
    rows = yields_for_district(district_id, crop, db_path)
    farms = len({r["tenant_id"] for r in rows})
    seasons = len({r["season_year"] for r in rows})
    return {"records": len(rows), "farms": farms, "seasons": seasons}


# ── knowledge snippets (simple keyword search, no embeddings) ─
def add_snippet(topic, content_ar, citation, district_id=None, crop=None,
               db_path: Path = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO knowledge_snippets
               (district_id, crop, topic, content_ar, citation)
               VALUES (?,?,?,?,?)""",
            (district_id, crop, topic, content_ar, citation),
        )


def search_snippets(topic=None, district_id=None, crop=None,
                   db_path: Path = DEFAULT_DB) -> list[dict]:
    """Simple structured retrieval — no GPU, no embeddings. Region/crop
    NULL in a snippet means it applies broadly."""
    with connect(db_path) as conn:
        q = "SELECT * FROM knowledge_snippets WHERE 1=1"
        params = []
        if topic:
            q += " AND topic=?"; params.append(topic)
        if district_id:
            q += " AND (district_id=? OR district_id IS NULL)"; params.append(district_id)
        if crop:
            q += " AND (crop=? OR crop IS NULL)"; params.append(crop)
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ── farmer knowledge (structured local knowledge) ────────────
def add_farmer_knowledge(fk_dict: dict, db_path: Path = DEFAULT_DB) -> None:
    """Store a structured FarmerKnowledge.to_dict() record."""
    cols = ["knowledge_id", "knowledge_type", "content_ar", "tenant_id",
            "district_id", "spatial_scope", "farmer_confidence", "mechanism_ar",
            "verification_method", "verification_status", "data_agreement",
            "review_year", "source_ar"]
    vals = []
    for c in cols:
        v = fk_dict.get(c)
        if c == "data_agreement" and v is not None:
            v = 1 if v else 0
        vals.append(v)
    with connect(db_path) as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO farmer_knowledge ({','.join(cols)}) "
            f"VALUES ({','.join('?'*len(cols))})", vals)


def get_farmer_knowledge(district_id=None, knowledge_type=None,
                        status=None, db_path: Path = DEFAULT_DB) -> list[dict]:
    with connect(db_path) as conn:
        q = "SELECT * FROM farmer_knowledge WHERE 1=1"
        params = []
        if district_id:
            q += " AND district_id=?"; params.append(district_id)
        if knowledge_type:
            q += " AND knowledge_type=?"; params.append(knowledge_type)
        if status:
            q += " AND verification_status=?"; params.append(status)
        return [dict(r) for r in conn.execute(q, params).fetchall()]


# ── variety trials (accumulated varietal experience) ─────────
def add_variety_trial(tenant_id, district_id, variety_ar, crop, trait_tested,
                     result_ar, season_year=None, verified_by="farmer_obs",
                     dna_verified=False, db_path: Path = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO variety_trials
               (tenant_id, district_id, variety_ar, crop, trait_tested,
                season_year, result_ar, verified_by, dna_verified)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (tenant_id, district_id, variety_ar, crop, trait_tested,
             season_year, result_ar, verified_by, 1 if dna_verified else 0))


def get_variety_trials(district_id=None, crop=None, variety_ar=None,
                      db_path: Path = DEFAULT_DB) -> list[dict]:
    with connect(db_path) as conn:
        q = "SELECT * FROM variety_trials WHERE 1=1"
        params = []
        if district_id:
            q += " AND district_id=?"; params.append(district_id)
        if crop:
            q += " AND crop=?"; params.append(crop)
        if variety_ar:
            q += " AND variety_ar=?"; params.append(variety_ar)
        return [dict(r) for r in conn.execute(q, params).fetchall()]

# ════════════════════════════════════════════════════════════
# الفجوات الحقيقية من مراجعة v9.1.0 (على SQLite، لا PostgreSQL)
# ════════════════════════════════════════════════════════════

def save_field_state(field_id, tenant_id, quality_state, soil_choice=None,
                     completeness=0, soil_skip_reason=None, supervisor_id=None,
                     supervisor_role=None, db_path: Path = DEFAULT_DB):
    """الفجوة #6: تخزين حالة الحقل (لا حسابها فقط).
    + المسؤول (مراجعة #2) + سبب التخطّي (مراجعة #6)."""
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO field_state (field_id, tenant_id, quality_state, soil_choice,
                completeness, soil_skip_reason, supervisor_id, supervisor_role, updated_at)
            VALUES (?,?,?,?,?,?,?,?,datetime('now'))
            ON CONFLICT(field_id) DO UPDATE SET
                quality_state=excluded.quality_state, soil_choice=excluded.soil_choice,
                completeness=excluded.completeness, soil_skip_reason=excluded.soil_skip_reason,
                supervisor_id=excluded.supervisor_id, supervisor_role=excluded.supervisor_role,
                updated_at=datetime('now')
        """, (field_id, tenant_id, quality_state, soil_choice, completeness,
              soil_skip_reason, supervisor_id, supervisor_role))


def save_irrigation_config(field_id, tenant_id, method, pivot_length_m=None,
                           pivot_radius_m=None, flow_rate_lps=None, schedule_json=None,
                           water_source=None, db_path: Path = DEFAULT_DB) -> int:
    """مراجعة #1: حفظ إعداد نظام الري (الفجوة الأكبر بين التدفّق والكود)."""
    with connect(db_path) as conn:
        cur = conn.execute("""
            INSERT INTO irrigation_configs (field_id, tenant_id, method, pivot_length_m,
                pivot_radius_m, flow_rate_lps, schedule_json, water_source)
            VALUES (?,?,?,?,?,?,?,?)
        """, (field_id, tenant_id, method, pivot_length_m, pivot_radius_m,
              flow_rate_lps, schedule_json, water_source))
        return cur.lastrowid


def get_irrigation_config(field_id, db_path: Path = DEFAULT_DB) -> dict | None:
    with connect(db_path) as conn:
        r = conn.execute(
            "SELECT * FROM irrigation_configs WHERE field_id=? ORDER BY config_id DESC LIMIT 1",
            (field_id,)).fetchone()
        return dict(r) if r else None


def upsert_user(tenant_id, display_name=None, phone=None, district_id=None,
                role="owner", db_path: Path = DEFAULT_DB):
    """مراجعة #5: إدارة المستخدمين المبسّطة.
    tenant_id = معرّف المزرعة · district_id = المديرية."""
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO users (tenant_id, display_name, phone, district_id, role)
            VALUES (?,?,?,?,?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                display_name=excluded.display_name, phone=excluded.phone,
                district_id=excluded.district_id, role=excluded.role
        """, (tenant_id, display_name, phone, district_id, role))


def get_field_state(field_id, db_path: Path = DEFAULT_DB) -> dict | None:
    with connect(db_path) as conn:
        r = conn.execute("SELECT * FROM field_state WHERE field_id=?", (field_id,)).fetchone()
        return dict(r) if r else None


def create_lab_request(field_id, tenant_id, db_path: Path = DEFAULT_DB) -> int:
    """الفجوة #9: إنشاء طلب معمل → الحقل يصبح pending_lab."""
    with connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO lab_requests (field_id, tenant_id) VALUES (?,?)",
            (field_id, tenant_id))
        return cur.lastrowid


def receive_lab_results(field_id, db_path: Path = DEFAULT_DB) -> dict:
    """الفجوة #9: حدث LAB_RESULTS_RECEIVED — pending_lab → ready.
    يُعلّم الطلب مستلَماً ويرقّي حالة الحقل. يُرجع ما يكفي لإرسال إشعار."""
    with connect(db_path) as conn:
        conn.execute("""
            UPDATE lab_requests SET status='received', received_at=datetime('now')
            WHERE field_id=? AND status='pending'
        """, (field_id,))
        # ترقية حالة الحقل إن وُجد
        conn.execute("""
            UPDATE field_state SET quality_state='ready', updated_at=datetime('now')
            WHERE field_id=?
        """, (field_id,))
        row = conn.execute(
            "SELECT field_id, tenant_id FROM field_state WHERE field_id=?",
            (field_id,)).fetchone()
        return {"field_id": field_id, "new_state": "ready",
                "notify": True, "tenant_id": row["tenant_id"] if row else None}


def record_consent(tenant_id, consent_type, version, db_path: Path = DEFAULT_DB):
    """الفجوة #1: تسجيل الموافقة (مبسّط)."""
    with connect(db_path) as conn:
        conn.execute("""
            INSERT INTO user_consent (tenant_id, consent_type, version)
            VALUES (?,?,?)
        """, (tenant_id, consent_type, version))


# ── مراجعة v9.1 #12: نسخة احتياطية بسيطة (مناسبة لـ 50 مزرعة) ──
def backup_db(db_path: Path = DEFAULT_DB, backup_dir: str = "backups") -> str:
    """ينسخ قاعدة البيانات بطابع زمني. بسيط — لا S3/MinIO الآن (مبكر).
    يُستدعى دورياً (cron) أو قبل الترقيات."""
    import shutil
    from datetime import datetime
    bdir = Path(backup_dir)
    bdir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = bdir / f"sahool_{stamp}.db"
    shutil.copy2(db_path, dst)
    return str(dst)


# ── مراجعة v9.1 #1 (مبسّط): تعقيم المعرّفات حيث تُستخدم في مسارات ──
def sanitize_id(raw: str) -> str:
    """يعقّم معرّفاً (tenant/district) قبل استخدامه في أي مسار ملف.
    دفاع وقائي: حتى لو لم نبنِ المسار من tenant_id حالياً، نمنع المستقبل."""
    import re
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", raw or "")
    if not safe or safe != raw:
        raise ValueError(f"معرّف غير صالح: {raw!r}")
    return safe
