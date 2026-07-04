import { Hexagon, Share2, ScanSearch } from 'lucide-react';
import { useBoundaryGraph, useScoreBoundary } from '../../hooks/useApi';
import {
  confidencePct,
  confidenceTone,
  summarizeNeighbors,
  topPenalties,
} from '../../lib/fieldBoundaryReview';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

/** مركز مراجعة الحدود: تهديف ثقة حدّ الحقل (حتميّ، يشتقّه الخادم من geom المخزَّنة
 *  ويخزّن النتيجة) + شبكة الجوار بطول الحافّة المشتركة. صدق: توصية المراجعة قرار
 *  الخادم (عتبته)، والعوامل تُعرَض كما رجعت — الواجهة لا تعيد الحكم. */
export default function BoundaryReviewCard({ fieldId, enabled = true }: Props) {
  const graphQ = useBoundaryGraph(fieldId, enabled);
  const scoreM = useScoreBoundary();

  if (!enabled || !fieldId) return null;

  const neighbors = summarizeNeighbors(graphQ.data);
  const result = scoreM.data ?? null;
  const tone = confidenceTone(result);
  const penalties = topPenalties(result?.factors);

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="boundary-review" aria-label="مراجعة الحدود">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Hexagon className="w-4 h-4 text-emerald-300" aria-hidden="true" /> مراجعة حدود الحقل
        </span>
        <button
          type="button"
          onClick={() => fieldId && scoreM.mutate({ fieldId })}
          disabled={scoreM.isPending}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >
          <ScanSearch className="w-3.5 h-3.5" aria-hidden="true" />
          {scoreM.isPending ? 'جارٍ التهديف…' : 'قيّم الحدّ الآن'}
        </button>
      </div>

      {scoreM.isError && (
        <div className="text-[11px] mb-2" role="status" style={{ color: '#fdba74' }}>
          تعذّر التهديف — {`${scoreM.error?.message ?? 'خطأ غير معروف'}`}
        </div>
      )}

      {result ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span
              className="text-lg font-bold"
              style={{ color: tone === 'good' ? '#86efac' : tone === 'review' ? '#fdba74' : T.muted }}
            >
              الثقة {confidencePct(result.confidence)}
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{
                border: `1px solid ${tone === 'review' ? '#7c2d12' : '#14532d'}`,
                color: tone === 'review' ? '#fdba74' : '#86efac',
              }}
            >
              {result.review_recommended ? 'يوصى بمراجعة الحدّ' : 'لا مراجعة مطلوبة'}
            </span>
          </div>
          {penalties.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {penalties.map((f) => (
                <li key={f.name_ar} className="text-[11px]" style={{ color: T.muted }}>
                  − {f.name_ar} <span style={{ color: T.faint }}>({f.delta})</span>
                </li>
              ))}
            </ul>
          )}
          {result.derived_props && (
            <div className="text-[10px]" style={{ color: T.faint }}>
              مُشتقّ من الهندسة المخزَّنة: {result.derived_props.vertex_count ?? '—'} رأساً
              {result.derived_props.area_ha != null ? ` · ${result.derived_props.area_ha.toFixed(1)} هـ` : ''}
              {result.derived_props.ring_count != null && result.derived_props.ring_count > 1 ? ` · ${result.derived_props.ring_count} حلقات` : ''}
            </div>
          )}
        </div>
      ) : (
        <div className="text-[11px]" style={{ color: T.muted }}>
          اضغط «قيّم الحدّ الآن» لتهديف حتميّ من الهندسة المخزَّنة (يُخزَّن كثقة رسميّة للحدّ).
        </div>
      )}

      {/* شبكة الجوار */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
        <Share2 className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" />
        {graphQ.isLoading ? (
          <span style={{ color: T.faint }}>جارٍ قراءة شبكة الجوار…</span>
        ) : neighbors.count === 0 ? (
          <span>لا جيران مُسجَّلين في شبكة الحدود (صالح لحقل معزول).</span>
        ) : (
          <>
            <span className="font-bold" style={{ color: T.ink }}>{neighbors.count} جاراً:</span>
            {neighbors.top.map((n) => (
              <span key={n.neighbor_field_id} className="px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}` }}>
                {n.neighbor_field_id.slice(0, 8)}…
                {n.shared_edge_length_m != null ? ` · ${Math.round(n.shared_edge_length_m)} م` : ''}
              </span>
            ))}
          </>
        )}
      </div>
    </section>
  );
}
