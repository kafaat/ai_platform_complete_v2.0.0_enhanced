import { Beaker, CheckCircle2, ClipboardList, MapPin, XCircle } from 'lucide-react';

export interface SoilSamplePoint {
  sample_id?: string;
  zone_id?: string;
  productivity_class?: 'high' | 'medium' | 'low' | string;
  priority?: 'high' | 'normal' | string;
  depth_cm?: number[];
  lab_panel?: string;
  analytes?: string[];
  instructions_ar?: string;
}

export interface SoilSamplingPlan {
  plan_id?: string;
  lab_panel?: string;
  analytes?: string[];
  total_samples?: number;
  estimated_field_hours?: number;
  strata?: Array<{ zone_id?: string; productivity_class?: string; sample_count?: number; area_ha?: number }>;
}

export interface SoilSamplingPlannerPanelProps {
  plan?: SoilSamplingPlan | null;
  samplePoints: SoilSamplePoint[];
  onAccept?: (plan: SoilSamplingPlan | null, samplePoints: SoilSamplePoint[]) => void;
  onReject?: () => void;
  onContinueToVra?: (plan: SoilSamplingPlan | null) => void;
}

const classLabel: Record<string, string> = {
  high: 'إنتاجية مرتفعة',
  medium: 'إنتاجية متوسطة',
  low: 'إنتاجية منخفضة',
};

export function SoilSamplingPlannerPanel({
  plan,
  samplePoints,
  onAccept,
  onReject,
  onContinueToVra,
}: SoilSamplingPlannerPanelProps) {
  if (!plan || !samplePoints.length) return null;
  return (
    <div className="rounded-2xl border border-sky-100 bg-white/95 p-3 shadow-sm" data-testid="soil-sampling-planner-panel">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-800">
            <Beaker className="h-4 w-4" /> خطة عينات تربة مقترحة
          </div>
          <div className="text-xs text-slate-500">مبنية على مناطق الإنتاجية · لا تُحفَظ ولا تتحول إلى مهام إلا بعد التأكيد</div>
        </div>
        <span className="rounded-full border border-sky-100 bg-sky-50 px-2 py-1 text-xs text-sky-700">
          V61 sampling
        </span>
      </div>

      <div className="mb-2 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
        <div className="rounded-xl bg-slate-50 p-2"><ClipboardList className="mb-1 h-3 w-3" /> العينات: {plan.total_samples ?? samplePoints.length}</div>
        <div className="rounded-xl bg-slate-50 p-2">المختبر: {plan.lab_panel ?? 'standard'}</div>
        <div className="rounded-xl bg-slate-50 p-2">الساعات: {plan.estimated_field_hours ?? '—'}</div>
        <div className="rounded-xl bg-slate-50 p-2">الطبقات: {plan.strata?.length ?? 0}</div>
      </div>

      <div className="space-y-2">
        {samplePoints.slice(0, 8).map((p, i) => (
          <div key={p.sample_id ?? i} className="rounded-xl border border-slate-100 bg-slate-50 p-2" data-testid="soil-sample-point-card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
              <span><MapPin className="inline h-3 w-3" /> {p.sample_id ?? `sample-${i + 1}`}</span>
              <span>المنطقة: {p.zone_id ?? '—'}</span>
              <span>{classLabel[p.productivity_class ?? ''] ?? p.productivity_class}</span>
              <span>الأولوية: {p.priority ?? 'normal'}</span>
              {!!p.depth_cm?.length && <span>العمق: {p.depth_cm.join('–')} سم</span>}
            </div>
            {!!p.analytes?.length && <div className="mt-1 text-[11px] text-slate-400">التحاليل: {p.analytes.slice(0, 8).join(' · ')}</div>}
            {p.instructions_ar && <div className="mt-1 text-[11px] text-slate-500">{p.instructions_ar}</div>}
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        <button type="button" data-testid="soil-sampling-accept" onClick={() => onAccept?.(plan, samplePoints)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50">
          <CheckCircle2 className="h-3 w-3" /> اعتماد خطة العينات
        </button>
        <button type="button" data-testid="soil-sampling-vra-next" onClick={() => onContinueToVra?.(plan)} className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-white px-2 py-1 text-xs text-amber-700 hover:bg-amber-50">
          إلى وصفات VRA
        </button>
        <button type="button" data-testid="soil-sampling-reject" onClick={onReject} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">
          <XCircle className="h-3 w-3" /> رفض
        </button>
      </div>
    </div>
  );
}
