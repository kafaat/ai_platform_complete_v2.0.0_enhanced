-- v201: SEASON-RECORD-01 — ترقيم المواسم الورقيّة (سجلّ الموسم المُدار).
--
-- بيانات الدفاتر = سجلّ موسم مُدار كامل (عمليّات + مدخلات + حصاد + تكاليف) — أغنى بنيويّاً من «ملاحظة
-- ميدانيّة» (external_submissions/v197). لذا **جداول مستقلّة** (قرار المواصفة ①)، لكن **يملكها
-- scout-ingest-service القائم** (قرار المراجعة Q1): نفس بوّابة الثقة (untrusted→accepted، مراجعة بشريّة)
-- ونفس انضباط append-only (**لا DELETE أبداً**؛ التصحيح = إصدار جديد مُبطِل). لا خدمة جديدة (درس #180).
--
-- **المبدأ الحاكم: لا بيانات مُخترَعة** — الحقول الناقصة تُصرَّح ``NULL`` ولا تُملأ. الكمّيّة الغائبة
-- تُوسَم ``low_confidence=true`` صراحةً لا تُخمَّن.
--
-- **الهندسة ليست هنا:** الحقل يُنشأ أوّلاً (polygon) عبر مسار تسجيل الحقول القائم، ثمّ يُربط الموسم بـ
-- ``field_id`` (قرار ③). لا عمود هندسة في جداول المواسم — الهندسة ملك سجلّ الحقول وحده (كاتب واحد).
--
-- **العزل:** RLS + FORCE على الجداول الخمسة كلّها بسياسة ``tenant_id = current_setting('app.current_tenant')``
-- (نمط v197/v199 المُثبَت حيّاً). **لا DELETE:** يُنزَع في كلا المُشغّلَين (bootstrap/apply) — برهان سلبيّ.
--
-- **calibration_eligible مُشتقّ لا يدويّ (انحراف مبرَّر عن «عمود مُولَّد»):** الأهليّة تعتمد أعمدة في
-- ثلاثة جداول (وجود season_harvest + season_crop.sowing_precision='day' + season_harvest.harvest_precision='day')
-- — والعمود المُولَّد (GENERATED) لا يعبر الجداول. فالتعبير الصحيح **VIEW مُشتقّ** (غير قابل للتحرير اليدويّ
-- = نفس نيّة المواصفة: لا يُحرَّر يدويّاً)، لا عمود مخزَّن قد يُحقَن كذباً.

-- ════════════════════════════════════════════════════════════════════════════
-- ١) season_records — رأس الموسم (بوّابة الثقة)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS season_records (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL,
    field_id           TEXT NOT NULL,                          -- مرجع الحقل (اقتران فضفاض عبر-خدمات، نمط الشقيق v199؛ لا FK صارم: fields ملك المنصّة وPKها VARCHAR field_id لا UUID id). لا هندسة هنا.
    season_label       TEXT,                                   -- "شتاء 2022/2023" (وصف حرّ)
    observed_at_from   DATE NOT NULL,                          -- أقدم تاريخ في الدفتر
    observed_at_to     DATE NOT NULL,                          -- أحدث تاريخ
    submitted_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source             TEXT NOT NULL DEFAULT 'manual_logbook',
    logbook_image_ref  TEXT,                                   -- مرفق صورة الصفحة (إلزاميّ للقبول — يُفرَض بالتطبيق)
    trust_status       TEXT NOT NULL DEFAULT 'untrusted'
                       CHECK (trust_status IN ('untrusted', 'accepted', 'quarantined')),
    accepted_by        TEXT,                                   -- مُراجِع بشريّ — إلزاميّ عند accepted (يُفرَض بالتطبيق)
    accepted_at        TIMESTAMPTZ,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- قيد النزاهة ١: لا ملاحظات «في المستقبل»
    CONSTRAINT season_records_no_future CHECK (observed_at_to <= submitted_at::date),
    -- المدى الزمنيّ متّسق
    CONSTRAINT season_records_range CHECK (observed_at_from <= observed_at_to)
);
CREATE INDEX IF NOT EXISTS ix_season_records_tenant_field ON season_records (tenant_id, field_id);

-- ════════════════════════════════════════════════════════════════════════════
-- ٢) season_crop — المحصول (1:1 مع الموسم)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS season_crop (
    season_id          UUID PRIMARY KEY REFERENCES season_records(id),
    tenant_id          UUID NOT NULL,
    variety_name       TEXT NOT NULL,                          -- نصّ حرّ + ربط اختياريّ بسجلّ المحاصيل
    crop_registry_ref  TEXT,                                   -- wheat|barley|potato|NULL
    sowing_date        DATE NOT NULL,
    sowing_precision   TEXT NOT NULL DEFAULT 'day'
                       CHECK (sowing_precision IN ('day', 'month', 'season')),
    seed_rate_kg_ha    NUMERIC CHECK (seed_rate_kg_ha IS NULL OR seed_rate_kg_ha > 0)
);

-- ════════════════════════════════════════════════════════════════════════════
-- ٣) season_events — العمليّات والمدخلات (1:N)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS season_events (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id          UUID NOT NULL REFERENCES season_records(id),
    tenant_id          UUID NOT NULL,
    event_type         TEXT NOT NULL CHECK (event_type IN
                       ('tillage', 'land_prep', 'irrigation', 'fert_organic', 'fert_chemical',
                        'pesticide', 'energy', 'other')),
    event_date         DATE NOT NULL,
    date_precision     TEXT NOT NULL DEFAULT 'day'
                       CHECK (date_precision IN ('day', 'month', 'season')),
    growth_stage       TEXT,                                   -- المرحلة النمائيّة (اختياريّ)
    amount_kg_ha       NUMERIC,                                -- للأسمدة/المبيدات
    amount_mm          NUMERIC,                                -- للريّ — NULL مسموح صراحةً
    duration_hours     NUMERIC,                                -- بديل الريّ عند غياب الكمّيّة
    machinery_hours    NUMERIC,                                -- ساعات عمل المعدّة — NULL إن لم تُسجَّل
    fuel_liters        NUMERIC,                                -- للطاقة: ديزل
    energy_kwh         NUMERIC,                                -- للطاقة: كهرباء (مضخّات)
    low_confidence     BOOLEAN NOT NULL DEFAULT false,         -- يُضبط عند غياب الكمّيّة والمدّة
    npk_composition    TEXT,                                   -- للسماد الكيميائيّ
    active_ingredient  TEXT,                                   -- للمبيدات
    description        TEXT,
    -- قيد ٤ج: ساعات المعدّة لا تكون سالبة/صفريّة إن سُجِّلت
    CONSTRAINT season_events_machinery_positive
        CHECK (machinery_hours IS NULL OR machinery_hours > 0),
    -- قيد ٤ب: حدث energy يتطلّب fuel_liters أو energy_kwh، أو دقّة 'season' مع وصف (فاتورة مجمّعة — لا تفكيك مُختلَق)
    CONSTRAINT season_events_energy_evidence CHECK (
        event_type <> 'energy'
        OR fuel_liters IS NOT NULL
        OR energy_kwh IS NOT NULL
        OR (date_precision = 'season' AND description IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_season_events_season ON season_events (season_id);

-- ════════════════════════════════════════════════════════════════════════════
-- ٤) season_harvest — الحصاد (1:1 — نقطة المعايرة الذهبيّة)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS season_harvest (
    season_id          UUID PRIMARY KEY REFERENCES season_records(id),
    tenant_id          UUID NOT NULL,
    harvest_date       DATE NOT NULL,
    harvest_precision  TEXT NOT NULL DEFAULT 'day'
                       CHECK (harvest_precision IN ('day', 'month', 'season')),
    yield_kg_ha        NUMERIC CHECK (yield_kg_ha IS NULL OR yield_kg_ha >= 0)
);

-- قيد النزاهة ٣: harvest_date > sowing_date (يعبر جدولين ⇒ trigger لا CHECK)
CREATE OR REPLACE FUNCTION season_harvest_after_sowing() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_sowing DATE;
BEGIN
  SELECT sowing_date INTO v_sowing FROM season_crop WHERE season_id = NEW.season_id;
  IF v_sowing IS NOT NULL AND NEW.harvest_date <= v_sowing THEN
    RAISE EXCEPTION 'season_harvest: harvest_date (%) must be after sowing_date (%)', NEW.harvest_date, v_sowing;
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_season_harvest_after_sowing ON season_harvest;
CREATE TRIGGER trg_season_harvest_after_sowing
  BEFORE INSERT OR UPDATE ON season_harvest
  FOR EACH ROW EXECUTE FUNCTION season_harvest_after_sowing();

-- ════════════════════════════════════════════════════════════════════════════
-- ٥) season_cost_items — التكاليف (1:N) — تعدّد عملات آمن (Q4)
-- ════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS season_cost_items (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id          UUID NOT NULL REFERENCES season_records(id),
    tenant_id          UUID NOT NULL,
    item_label         TEXT NOT NULL,
    amount             NUMERIC NOT NULL CHECK (amount >= 0),
    -- تعدّد عملات على مستوى السطر: YER افتراضيّة، ISO 4217. لا تحويل صامت — التجميع عبر عملتين
    -- يتطلّب سعر صرف مُعلَناً من المستخدم (يُفرَض في طبقة التقارير لا هنا). امتداد قاعدة «لا تحويل وحدات صامت».
    currency           TEXT NOT NULL DEFAULT 'YER' CHECK (currency ~ '^[A-Z]{3}$'),
    cost_date          DATE,
    linked_event_id    UUID REFERENCES season_events(id)       -- التكلفة العائمة (NULL) مقبولة صراحةً — لا ربط مُختلَق
);
CREATE INDEX IF NOT EXISTS ix_season_cost_items_season ON season_cost_items (season_id);

-- ════════════════════════════════════════════════════════════════════════════
-- RLS + FORCE على الجداول الخمسة (عزل المستأجِر، نمط v197/v199)
-- ════════════════════════════════════════════════════════════════════════════
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['season_records', 'season_crop', 'season_events', 'season_harvest', 'season_cost_items']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I '
      'USING (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), '''')) '
      'WITH CHECK (tenant_id::text = NULLIF(current_setting(''app.current_tenant'', true), ''''))',
      t);
  END LOOP;
END $$;

-- ════════════════════════════════════════════════════════════════════════════
-- calibration_eligible — VIEW مُشتقّ (غير قابل للتحرير اليدويّ؛ يعبر ثلاثة جداول)
-- الأهليّة: وجود حصاد + دقّة زراعة 'day' + دقّة حصاد 'day' + الموسم مقبول (accepted).
--
-- ⚠ ``security_invoker = true`` إلزاميّ (PG15+): الـVIEW افتراضاً يعمل بصلاحيّات مالكه فيتخطّى RLS على
-- الجداول الثلاثة ويسرّب الأهليّة عبر المستأجرين (نفس فخّ DEFINER/RLS المحلول في v198). مع security_invoker
-- تُطبَّق RLS بصلاحيّات القارئ ⇒ المستأجِر B يرى صفر صفوف لمواسم المستأجِر A (برهان سلبيّ).
-- ════════════════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW season_calibration_eligibility
WITH (security_invoker = true) AS
SELECT
    sr.id                                 AS season_id,
    sr.tenant_id,
    sr.field_id,
    (
        h.season_id IS NOT NULL
        AND sr.trust_status = 'accepted'
        AND c.sowing_precision = 'day'
        AND h.harvest_precision = 'day'
        AND h.yield_kg_ha IS NOT NULL
    )                                     AS calibration_eligible,
    h.yield_kg_ha
FROM season_records sr
LEFT JOIN season_crop c    ON c.season_id = sr.id
LEFT JOIN season_harvest h ON h.season_id = sr.id;

COMMENT ON VIEW season_calibration_eligibility IS
  'SEASON-RECORD-01: الأهليّة للمعايرة (SIM-GOLDEN) مُشتقّة لا يدويّة — موسم مقبول بحصاد مؤكّد ودقّة يوميّة. '
  'لا عمود مخزَّن (يعبر ثلاثة جداول) فلا يُحقَن كذباً.';

COMMENT ON TABLE season_records IS
  'SEASON-RECORD-01: رأس سجلّ الموسم المُدار (بوّابة ثقة untrusted→accepted، append-only، لا DELETE). '
  'مالك: scout-ingest-service. الهندسة ملك سجلّ الحقول (field_id مرجع نصّيّ لا polygon هنا).';
COMMENT ON TABLE season_harvest IS
  'SEASON-RECORD-01: نقطة المعايرة الذهبيّة (yield_kg_ha) — تُغذّي SIM-GOLDEN-01 عند توفّر مواسم مؤهَّلة.';
