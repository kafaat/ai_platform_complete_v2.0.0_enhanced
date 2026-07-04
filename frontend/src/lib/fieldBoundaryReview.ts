// FieldView Boundary Review — يعكس حوكمة الحدود المُخزَّنة (boundary/score التهديف
// الحتميّ + field_boundary_graph شبكة الجوار) على الحقل النشط. صدق: توصية المراجعة
// review_recommended تأتي من عتبة الخادم (لا إعادة حكم في الواجهة)، والعوامل تُعرَض
// كما رجعت (name_ar + delta)، والجيران بطول الحافّة المشتركة الحقيقيّ.

export interface BoundaryScoreFactor {
  name_ar: string;
  delta: number;
}

export interface BoundaryScoreResult {
  confidence: number;
  factors: BoundaryScoreFactor[];
  review_recommended: boolean;
  /** الخصائص المُشتقّة خادميّاً من geom (شفافيّة #15) — قد تغيب عند إرسال props صراحةً. */
  derived_props?: {
    is_valid?: boolean;
    vertex_count?: number;
    area_ha?: number;
    ring_count?: number;
    self_intersections?: number;
  };
}

export interface BoundaryNeighbor {
  neighbor_field_id: string;
  relation_type: string | null;
  shared_edge_length_m: number | null;
}

export interface BoundaryGraphResponse {
  field_id: string;
  neighbors: BoundaryNeighbor[];
}

/** أسوأ العقوبات (delta الأكثر سلبيّة أوّلاً) — لعرض «لماذا انخفضت الثقة». */
export function topPenalties(factors: BoundaryScoreFactor[] | null | undefined, limit = 3): BoundaryScoreFactor[] {
  if (!Array.isArray(factors)) return [];
  return factors
    .filter((f) => typeof f.delta === 'number' && f.delta < 0)
    .sort((a, b) => a.delta - b.delta)
    .slice(0, limit);
}

/** لون العرض من قرار الخادم لا من عتبة واجهة موازية. */
export function confidenceTone(result: BoundaryScoreResult | null | undefined): 'good' | 'review' | 'unknown' {
  if (!result || typeof result.confidence !== 'number') return 'unknown';
  return result.review_recommended ? 'review' : 'good';
}

export interface NeighborsSummary {
  count: number;
  /** أطول ٣ حوافّ مشتركة (م) — للجيران الفعليّين فقط. */
  top: BoundaryNeighbor[];
}

export function summarizeNeighbors(graph: BoundaryGraphResponse | null | undefined, limit = 3): NeighborsSummary {
  const neighbors = graph?.neighbors ?? [];
  return { count: neighbors.length, top: neighbors.slice(0, limit) };
}

/** تنسيق نسبة الثقة: 0..1 ⇒ «87٪»؛ غير الرقم ⇒ «—». */
export function confidencePct(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return '—';
  return `${Math.round(confidence * 100)}٪`;
}

// ── كتابات الحوكمة: اعتماد المراجعة + التنظيف الطوبولوجيّ الحتميّ ──

export type BoundaryReviewStatus = 'approved' | 'rejected' | 'needs_edit';

export interface BoundaryReviewResult {
  field_id: string;
  review_status: BoundaryReviewStatus | string;
}

export interface BoundaryCleanResult {
  field_id: string;
  vertex_count_before: number | null;
  vertex_count_after: number | null;
  is_valid_before: boolean | null;
  is_valid_after: boolean | null;
  tolerance_m: number;
}

/** ملخّص عربيّ صادق لنتيجة التنظيف — من أرقام الخادم قبل/بعد، لا ادّعاء تحسّن. */
export function summarizeClean(r: BoundaryCleanResult | null | undefined): string {
  if (!r) return '—';
  const before = r.vertex_count_before;
  const after = r.vertex_count_after;
  const verts = before != null && after != null
    ? (before === after ? `الرؤوس ثابتة (${after})` : `الرؤوس ${before} ⇒ ${after}`)
    : 'عدد الرؤوس غير معروف';
  const validity = r.is_valid_after === true
    ? 'هندسة صالحة'
    : r.is_valid_after === false
      ? 'ما زالت غير صالحة'
      : 'صلاحيّة غير معروفة';
  return `${verts} · ${validity} (سماحيّة ${r.tolerance_m} م)`;
}

const REVIEW_STATUS_AR: Record<string, string> = {
  approved: 'مُعتمَد',
  rejected: 'مرفوض',
  needs_edit: 'يحتاج تعديلاً',
};

export function reviewStatusLabel(status: string | null | undefined): string {
  return status ? (REVIEW_STATUS_AR[status] ?? status) : '—';
}
