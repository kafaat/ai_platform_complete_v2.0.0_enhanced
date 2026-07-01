import { CheckCircle2, Edit3, XCircle } from 'lucide-react';

export interface FieldBoundaryProposal {
  geometry?: { type?: string; coordinates?: unknown };
  confidence?: number;
  area_ha?: number;
  method?: string;
}

export interface FieldBoundaryProposalPanelProps {
  proposals: FieldBoundaryProposal[];
  source?: string;
  onAccept?: (proposal: FieldBoundaryProposal) => void;
  onEdit?: (proposal: FieldBoundaryProposal) => void;
  onReject?: (proposal: FieldBoundaryProposal) => void;
}

export function FieldBoundaryProposalPanel({
  proposals,
  source = 'truecolor',
  onAccept,
  onEdit,
  onReject,
}: FieldBoundaryProposalPanelProps) {
  if (!proposals.length) return null;
  return (
    <div className="rounded-2xl border border-emerald-100 bg-white/95 p-3 shadow-sm" data-testid="field-boundary-proposal-panel">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-800">حدود حقل مقترحة</div>
          <div className="text-xs text-slate-500">المصدر: {source} · لا تُحفَظ إلا بعد التأكيد</div>
        </div>
        <span className="rounded-full border border-emerald-100 bg-emerald-50 px-2 py-1 text-xs text-emerald-700">
          AI proposal
        </span>
      </div>
      <div className="space-y-2">
        {proposals.slice(0, 3).map((p, i) => (
          <div key={i} className="rounded-xl border border-slate-100 bg-slate-50 p-2" data-testid="field-boundary-proposal-card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
              <span>الثقة: {Math.round((p.confidence ?? 0) * 100)}٪</span>
              {typeof p.area_ha === 'number' && <span>المساحة: {p.area_ha.toFixed(2)} هـ</span>}
              {p.method && <span className="text-slate-400">{p.method}</span>}
            </div>
            <div className="mt-2 flex gap-1">
              <button type="button" data-testid="field-boundary-accept" onClick={() => onAccept?.(p)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50">
                <CheckCircle2 className="h-3 w-3" /> قبول الحدود
              </button>
              <button type="button" data-testid="field-boundary-edit" onClick={() => onEdit?.(p)} className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-white px-2 py-1 text-xs text-sky-700 hover:bg-sky-50">
                <Edit3 className="h-3 w-3" /> تعديل
              </button>
              <button type="button" data-testid="field-boundary-reject" onClick={() => onReject?.(p)} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">
                <XCircle className="h-3 w-3" /> رفض
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
