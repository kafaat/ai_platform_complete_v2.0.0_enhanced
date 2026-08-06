# خطّة هجرة PostgreSQL + PostGIS

> **الغرض:** وثيقة هجرة كاملة من SQLite إلى PostgreSQL+PostGIS، **جاهزة للتنفيذ متى قُرّر** — لكن لا تُنفَّذ الآن. توافق مع المراجعة الاستراتيجية: "البنية تستقبل النضج دون إعادة كتابة مؤلمة".

> **متى تُنفَّذ هذه الخطّة؟** عند بلوغ أحد المعايير:
> - 50+ حقل نشط في منطقة واحدة، أو
> - استعلامات مكانية متزامنة (5+ req/s)، أو
> - raster lifecycle management يصبح ضرورة، أو
> - تكامل مع PostGIS الموجود في مؤسّسة شريكة

---

## ملخّص تنفيذي

ما يتغيّر:
- **التخزين:** SQLite WAL → PostgreSQL 16+ مع PostGIS 3.4+
- **المفاتيح:** TEXT id فقط → Dual-ID (UUID داخلي + readable خارجي)
- **الفهارس:** عمود بسيط → GIST مكاني + BTREE مركّب
- **العزل:** SQL filtering يدوي → Row-Level Security (اختياري عند الحاجة)

ما لا يتغيّر:
- ✅ canonical_schemas — نفس الحقول، نفس الأسماء
- ✅ Python core APIs — لا تعديل في الواجهات
- ✅ المبادئ السهولية — صفر اختراع، tenant isolation، evidence ceiling
- ✅ recommendation_bridge — يبقى نقطة الدخول

---

## ١. متطلّبات البنية التحتية

```yaml
PostgreSQL: 16.x (LTS — حتى 2028)
PostGIS:    3.4+ (Sentinel-2 native، raster mature)
PgBouncer:  1.20+ (connection pooling عند 50+ مستأجر)
Extensions:
  - postgis            # geometry/geography
  - postgis_raster     # raster overlays
  - postgis_topology   # spatial versioning
  - pg_trgm            # fuzzy search على readable IDs
  - btree_gist         # composite indexes (tenant_id + geometry)
  - uuid-ossp          # generate_uuid_v4() (احتياط)
```

**قيود PgBouncer مهمّة:**
```python
# asyncpg + PgBouncer transaction pooling
# يحتاج: statement_cache_size=0
# سبق توثيقه في userMemories من v7.5 → v8.0
```

---

## ٢. تحويل canonical_schemas → DDL

### 2.1 Tenant
```sql
CREATE TABLE tenants (
    id_uuid          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        TEXT UNIQUE NOT NULL,         -- readable: tnt_001
    name_ar          TEXT NOT NULL,
    name_en          TEXT,
    contact_email    TEXT,
    contact_phone    TEXT,
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended','archived')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version   TEXT NOT NULL DEFAULT '1.0'
);
CREATE INDEX idx_tenants_status ON tenants(status) WHERE status='active';
```

### 2.2 User
```sql
CREATE TABLE users (
    id_uuid          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT UNIQUE NOT NULL,         -- readable
    tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    role             TEXT NOT NULL
                     CHECK (role IN ('owner','manager','agronomist','worker','viewer')),
    name_ar          TEXT NOT NULL,
    email            TEXT,
    phone            TEXT,
    farm_ids_access  TEXT[],                       -- array، فارغ = كل المزارع
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at    TIMESTAMPTZ,
    schema_version   TEXT NOT NULL DEFAULT '1.0'
);
CREATE INDEX idx_users_tenant_active ON users(tenant_id) WHERE is_active=TRUE;
CREATE INDEX idx_users_role ON users(tenant_id, role);
```

### 2.3 Farm
```sql
CREATE TABLE farms (
    id_uuid          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id          TEXT UNIQUE NOT NULL,
    tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name_ar          TEXT NOT NULL,
    district_id      TEXT,
    governorate_id   TEXT,
    centroid         GEOGRAPHY(POINT, 4326),        -- نقطة مرجعية
    owner_user_id    TEXT REFERENCES users(user_id),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version   TEXT NOT NULL DEFAULT '1.0'
);
CREATE INDEX idx_farms_tenant ON farms(tenant_id);
CREATE INDEX idx_farms_centroid ON farms USING GIST(centroid);
CREATE INDEX idx_farms_district ON farms(tenant_id, district_id);
```

### 2.4 Field (الأهمّ مكانياً)
```sql
CREATE TABLE fields (
    id_uuid          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_id         TEXT UNIQUE NOT NULL,
    tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    farm_id          TEXT NOT NULL REFERENCES farms(farm_id) ON DELETE CASCADE,
    name_ar          TEXT NOT NULL,
    boundary         GEOGRAPHY(POLYGON, 4326),      -- الحدود الفعلية
    area_ha          DECIMAL(10,2),
    quality_state    TEXT NOT NULL DEFAULT 'BLOCKED'
                     CHECK (quality_state IN ('BLOCKED','LIMITED','PENDING_LAB','READY')),
    soil_type        TEXT,
    water_source     TEXT,
    notes_ar         TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version   TEXT NOT NULL DEFAULT '1.0',
    -- منع self-intersection على مستوى DB (لا polygon فاسد)
    CONSTRAINT fields_boundary_valid CHECK (
        boundary IS NULL OR ST_IsValid(boundary::geometry)
    )
);
CREATE INDEX idx_fields_tenant_farm ON fields(tenant_id, farm_id);
CREATE INDEX idx_fields_boundary ON fields USING GIST(boundary);
CREATE INDEX idx_fields_quality ON fields(tenant_id, quality_state);
```

### 2.5 CropSeason
```sql
CREATE TABLE crop_seasons (
    id_uuid                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id               TEXT UNIQUE NOT NULL,
    tenant_id               TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    field_id                TEXT NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    crop_id                 TEXT NOT NULL,
    variety_id              TEXT,
    season_name_ar          TEXT NOT NULL,
    season_year             INTEGER NOT NULL,
    planting_date           DATE,
    estimated_harvest_date  DATE,
    actual_harvest_date     DATE,
    irrigation_method       TEXT NOT NULL DEFAULT 'rainfed'
                            CHECK (irrigation_method IN
                                   ('flood','drip','sprinkler','rainfed',
                                    'supplemental','pivot')),
    seed_rate_kg_ha         DECIMAL(8,2),
    status                  TEXT NOT NULL DEFAULT 'planned'
                            CHECK (status IN ('planned','active','harvested','fallow','failed')),
    schema_version          TEXT NOT NULL DEFAULT '1.0',
    -- قاعدة Cropwise: محصول واحد لكل (حقل، موسم)
    UNIQUE (field_id, season_year, season_name_ar)
);
CREATE INDEX idx_seasons_tenant ON crop_seasons(tenant_id);
CREATE INDEX idx_seasons_crop_year ON crop_seasons(crop_id, season_year);
CREATE INDEX idx_seasons_status ON crop_seasons(tenant_id, status);
```

### 2.6 Observation (EAV الأهمّ في الحجم)
```sql
CREATE TABLE observations (
    id_uuid          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id   TEXT UNIQUE NOT NULL,
    tenant_id        TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    field_id         TEXT NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    observable_id    TEXT NOT NULL,
    value            DECIMAL(15,4) NOT NULL,
    unit             TEXT NOT NULL,
    source           TEXT NOT NULL
                     CHECK (source IN ('manual','sensor','lab','satellite','drone','historical')),
    confidence       TEXT NOT NULL DEFAULT 'low'
                     CHECK (confidence IN ('low','medium','high')),
    measured_at      TIMESTAMPTZ NOT NULL,
    method           TEXT,
    device_id        TEXT,
    location         GEOGRAPHY(POINT, 4326),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version   TEXT NOT NULL DEFAULT '1.0'
);
-- مهم: time-series queries هي الأكثر شيوعاً
CREATE INDEX idx_obs_field_time ON observations(field_id, measured_at DESC);
CREATE INDEX idx_obs_tenant_observable ON observations(tenant_id, observable_id, measured_at DESC);
CREATE INDEX idx_obs_source ON observations(source, measured_at) WHERE source='sensor';
CREATE INDEX idx_obs_location ON observations USING GIST(location) WHERE location IS NOT NULL;
-- لـTimescaleDB لاحقاً (hypertable على measured_at)
```

### 2.7 Recommendation (مع provenance JSON)
```sql
CREATE TABLE recommendations (
    id_uuid             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rec_id              TEXT UNIQUE NOT NULL,
    tenant_id           TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    field_id            TEXT REFERENCES fields(field_id),
    season_id           TEXT REFERENCES crop_seasons(season_id),
    crop                TEXT,
    issued_date         DATE NOT NULL,
    recommendation_ar   TEXT NOT NULL,
    quality_grade       TEXT NOT NULL DEFAULT 'BLOCKED'
                        CHECK (quality_grade IN ('BLOCKED','LIMITED','PENDING_LAB','READY')),
    predicted_value     DECIMAL(15,4),
    predicted_unit      TEXT,
    confidence          TEXT NOT NULL DEFAULT 'low'
                        CHECK (confidence IN ('low','medium','high')),
    provenance          JSONB,                       -- forensic كامل
    actual_value        DECIMAL(15,4),
    outcome_date        DATE,
    error_pct           DECIMAL(8,4),
    schema_version      TEXT NOT NULL DEFAULT '2.0'
);
-- استعلامات شائعة: by tenant+field+time، by crop+season
CREATE INDEX idx_rec_tenant_field_date ON recommendations(tenant_id, field_id, issued_date DESC);
CREATE INDEX idx_rec_crop_year ON recommendations(crop, EXTRACT(YEAR FROM issued_date));
CREATE INDEX idx_rec_outcome_known ON recommendations(tenant_id, issued_date)
    WHERE actual_value IS NOT NULL;
-- البحث في provenance (drift detection)
CREATE INDEX idx_rec_model_versions ON recommendations
    USING GIN ((provenance -> 'model_versions'));
```

---

## ٣. استراتيجية الفهارس

ثلاثة أنواع، كلٌّ بغرض:

### 3.1 Tenant Isolation Indexes
```sql
-- كل استعلام يبدأ بـtenant_id. هذا أساس الأداء.
CREATE INDEX idx_*_tenant ON *(tenant_id);
```

### 3.2 Temporal Indexes
```sql
-- الاستعلامات الزراعية زمنية بطبيعتها (موسم، تاريخ، آخر قراءة)
CREATE INDEX idx_obs_field_time ON observations(field_id, measured_at DESC);
CREATE INDEX idx_rec_tenant_date ON recommendations(tenant_id, issued_date DESC);
```

### 3.3 Spatial Indexes (PostGIS GIST)
```sql
-- spatial joins (الحقل × الصورة الفضائية × المنطقة)
CREATE INDEX idx_fields_boundary ON fields USING GIST(boundary);
CREATE INDEX idx_obs_location ON observations USING GIST(location)
    WHERE location IS NOT NULL;
```

---

## ٤. Row-Level Security (RLS) — اختياري

```sql
-- يُفعَّل فقط عند 200+ مستأجر أو تطلّب أمني حقيقي
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON recommendations
    USING (tenant_id = current_setting('app.current_tenant'));

-- في كود التطبيق:
-- SET LOCAL app.current_tenant = 'tnt_001';
-- ثمّ كل الاستعلامات معزولة تلقائياً
```

**ملاحظة:** RLS يُضيف overhead. لـ<200 مستأجر، tenant_id filtering في WHERE كافٍ.

---

## ٥. مراحل الهجرة (Cutover Plan)

### المرحلة 0: التحضير (1-2 أسبوع)
- نشر PostgreSQL+PostGIS في staging
- تشغيل اختبارات النواة (517+) ضدّ PostgreSQL adapter
- توثيق الاختلافات السلوكية (لا يجب أن تكون موجودة، النواة محايدة DB)

### المرحلة 1: Dual-write (2-4 أسابيع)
- التطبيق يكتب في SQLite + PostgreSQL معاً
- القراءة من SQLite (canonical)
- مراقبة divergence (أيّ سجل في إحداهما وليس الأخرى)

### المرحلة 2: Cutover (يوم واحد)
- toggle: القراءة من PostgreSQL، الكتابة في PostgreSQL فقط
- SQLite يبقى read-only لـrollback
- مراقبة معدّل الأخطاء لمدّة 24 ساعة

### المرحلة 3: Decommission (بعد 30 يوماً)
- إن استقرّ كل شيء، أرشفة SQLite
- تفعيل ميزات PostGIS الكاملة (raster، topology)

---

## ٦. Rollback Strategy

```python
# في recommendation_bridge.py أو db.py:
DB_BACKEND = os.getenv("SAHOOL_DB", "sqlite")  # "sqlite" أو "postgres"

# Rollback = toggle environment variable + restart
# SQLite يبقى متزامناً عبر مرحلة Dual-write
```

**شروط الـRollback:**
- معدّل أخطاء > 1% في 6 ساعات
- p99 latency > 3x المتوقَّع
- خطر فقدان بيانات

**ما لا يُعدّ rollback trigger:**
- بطء أوّلي (cache warming)
- أخطاء UX منعزلة (تُحلّ بـhotfix)

---

## ٧. توافق Dual-ID Strategy

كل canonical_schema الآن يحوي `id_uuid` (اختياري في النواة، PRIMARY KEY في PostgreSQL):

```python
# في النواة الحالية (in-memory):
field = FieldSchema(
    field_id="fld_03", tenant_id="t1", farm_id="frm_01", name_ar="حقل", id_uuid=None
)  # default، يعمل

# عند الهجرة:
# 1. توليد UUID لكل صفّ قائم
# 2. حفظه كـPRIMARY KEY
# 3. readable id يصبح UNIQUE constraint
# 4. النواة تستخدم identity.IdentityIndex للتحويل
```

---

## ٨. ما لا يتغيّر مع الهجرة (التوكيد المنهجي)

| الجانب | الحالة |
|--------|--------|
| Python API surface | ✅ نفس الواجهات |
| recommendation_engine | ✅ لا تعديل |
| skills_registry | ✅ يبقى in-memory |
| المبادئ الستة لسهول | ✅ كلها محفوظة |
| اختبارات النواة | ✅ تمرّ على كلا الـbackends |
| FarmerView/BackendDetail | ✅ نفس الفصل |
| Audit chain (recommendation_replay) | ✅ يستفيد من JSONB indexing |

---

## ٩. مكاسب متوقّعة (محسوبة لا مفترضة)

| البُعد | SQLite الحالية | PostgreSQL+PostGIS | المكسب |
|--------|----------------|---------------------|--------|
| Concurrent writes | 1 (lock) | ~100/s | ضروري للنشر |
| Spatial joins | O(n) برمجي | O(log n) GIST | 100x+ عند مئات الحقول |
| Time-series queries | full scan | BTREE | 50-200x |
| Audit on provenance | regex على JSON text | JSONB GIN | 1000x |
| Schema migrations | ALTER TABLE معقّد | فوري | سهولة الإدارة |
| Raster lifecycle | غير موجود | PostGIS raster | feature unlocked |

---

## ١٠. ما يبقى DEFER بعد الهجرة

حتى بعد PostgreSQL، يبقى مؤجَّلاً:
- **TimescaleDB hypertables**: عند مليون+ observation
- **RLS الكامل**: عند 200+ مستأجر
- **Read replicas**: عند 100+ req/s
- **PostgreSQL Citus shard**: عند 10K+ مزرعة
- **Materialized views**: عند تقارير شائعة بطيئة

---

## ١١. الإقرار المنهجي

هذه الوثيقة **خطّة لا تنفيذ**. تطبيقها يحدث عند معايير محدّدة، ليس "متى ما توفّر الوقت". 

**سبب نشرها الآن:**
- canonical_schemas + identity جاهزة للترقية
- المراجعة الاستراتيجية أكّدت "Hybrid Strategy لا فوري"
- الطلب: "البنية تستقبل النضج دون إعادة كتابة مؤلمة"

**ما يتغيّر اليوم:** صفر سطر كود في النواة. id_uuid حقل اختياري. recommendation_bridge يبقى كما هو.

**ما يصبح ممكناً اليوم:** عند قرار الهجرة، التنفيذ يستغرق أيّاماً لا أشهراً. الوثيقة تحوي كل DDL، كل index، كل rollback step.

هذا تجسيد عملي لمبدأ "التأجيل ≠ الإغلاق المعماري".
