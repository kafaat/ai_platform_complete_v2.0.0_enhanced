// evidenceGraph.ts — عقد «رسم أدلّة الحقل» (V74-UI) + مساعِدات عرض نقيّة.
//
// يطابق مخرَج build_evidence_graph في الخلفيّة (يُرفَق في استجابة analyze): عُقَد
// (الحقل + أدلّة حاضرة + توصية) وحوافّ وفجوات معرفة. الواجهة تعرض الأدلّة بمصادرها
// والفجوات بأسبابها صراحةً (لا اختلاق). مساعِدات نقيّة (بلا React) لتُختبَر منفصلةً.

export interface EvidenceNode {
  id: string;
  type: string;
  label: string;
  source?: string;
  field_id?: string | null;
  attrs?: Record<string, unknown>;
}

export interface EvidenceEdge {
  from: string;
  to: string;
  rel: string;
}

export interface KnowledgeGap {
  key: string;
  label: string;
  reason: string;
}

export interface EvidenceGraph {
  schema: string;
  field_id?: string | null;
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
  knowledge_gaps: KnowledgeGap[];
  summary: {
    node_count: number;
    edge_count: number;
    evidence_count: number;
    gap_count: number;
    has_recommendation: boolean;
  };
}

/** عُقَد الأدلّة فقط (باستثناء الحقل والتوصية) — لعرض «ما نعرفه». */
export function evidenceNodes(graph?: EvidenceGraph | null): EvidenceNode[] {
  if (!graph?.nodes) return [];
  return graph.nodes.filter((n) => n.type !== 'field' && n.type !== 'recommendation');
}

/** عدد الأدلّة التي تساند التوصية (حوافّ supports). */
export function supportingEvidenceCount(graph?: EvidenceGraph | null): number {
  if (!graph?.edges) return 0;
  return graph.edges.filter((e) => e.rel === 'supports').length;
}
