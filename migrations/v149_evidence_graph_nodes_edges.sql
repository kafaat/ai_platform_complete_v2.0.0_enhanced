-- migrations/v149_evidence_graph_nodes_edges.sql
--
-- v149: تطبيع رسم الأدلّة (Evidence Graph Phase 2) — عُقَد/حوافّ مُشتقّة من لقطة JSONB.
--
-- المشكلة: ``field_evidence_snapshots.evidence_graph`` (v148) يخزّن الرسم كـJSONB (مصدر
--   الحقيقة) — ممتاز للحفظ لكن الاستعلام التحليليّ عبر الحقول/الزمن (مثلاً «كلّ الحقول التي
--   ساندت توصيتَها أدلّة تضاريس») يتطلّب عمليّات jsonb ثقيلة.
--
-- الحلّ (المرحلة 2): جدولان **مُشتقّان** يُطبِّعان عُقَد/حوافّ كلّ لقطة. **JSONB يبقى مصدر
--   الحقيقة**؛ هذان اشتقاق فقط (كاتب fail-soft: فشله لا يكسر analyze ولا اللقطة). كلّ صفّ
--   يحمل snapshot_id مرجعاً (ON DELETE CASCADE)، وحالة present/missing/inferred + سبب.
-- معزول بالمستأجِر (RLS FORCE، نمط v140/v144/v148). idempotent (UNIQUE per snapshot).

BEGIN;

CREATE TABLE IF NOT EXISTS evidence_graph_nodes (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    snapshot_id BIGINT NOT NULL
        REFERENCES field_evidence_snapshots (id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,  -- "field" / "evidence:soil_baseline" / "recommendation" / "gap:terrain"
    node_type TEXT NOT NULL,  -- field/soil_baseline/terrain/recommendation…
    source TEXT,  -- soilgrids/element84/… (بلا أسرار — يُنقّيها الكاتب)
    status TEXT NOT NULL
        CHECK (status IN ('present', 'missing', 'inferred')),
    reason TEXT,  -- سبب الغياب (لعُقَد missing من knowledge_gaps)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, node_id)  -- لا تكرار عقدة لنفس اللقطة
);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_nodes_tenant_field_time
    ON evidence_graph_nodes (tenant_id, field_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_nodes_snapshot
    ON evidence_graph_nodes (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_nodes_type
    ON evidence_graph_nodes (tenant_id, node_type, status);

CREATE TABLE IF NOT EXISTS evidence_graph_edges (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    field_id VARCHAR(50) NOT NULL,
    snapshot_id BIGINT NOT NULL
        REFERENCES field_evidence_snapshots (id) ON DELETE CASCADE,
    edge_id TEXT NOT NULL,  -- "from->rel->to" (مُصنَّع، فريد لكلّ لقطة)
    edge_type TEXT NOT NULL,  -- has_evidence / supports
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, edge_id)  -- لا تكرار حافّة لنفس اللقطة
);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_edges_tenant_field_time
    ON evidence_graph_edges (tenant_id, field_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_graph_edges_snapshot
    ON evidence_graph_edges (snapshot_id);

-- RLS (نمط v148 الحرفيّ: FORCE + current_setting — الفاحص الساكن يطلبه صراحةً).
ALTER TABLE evidence_graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_graph_nodes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON evidence_graph_nodes;
CREATE POLICY tenant_isolation ON evidence_graph_nodes
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

ALTER TABLE evidence_graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_graph_edges FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON evidence_graph_edges;
CREATE POLICY tenant_isolation ON evidence_graph_edges
    USING (tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), ''))
    WITH CHECK (
        NULLIF(current_setting('app.current_tenant', true), '') IS NULL
        OR tenant_id::TEXT = current_setting('app.current_tenant', true)
    );

COMMIT;
