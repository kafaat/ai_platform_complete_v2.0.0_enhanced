import { Beaker, CheckCircle2, Layers3, XCircle } from 'lucide-react';

export interface ProductivityZoneProposal {
  zone_id?: string;
  productivity_class?: 'high' | 'medium' | 'low' | string;
  label_ar?: string;
  score?: number;
  confidence?: number;
  area_ha?: number;
  drivers?: string[];
  recommended_use?: string;
}

export interface ProductivityZonesPanelProps {
  zones: ProductivityZoneProposal[];
  basis?: string;
  onAccept?: (zones: ProductivityZoneProposal[]) => void;
  onReject?: () => void;
  onPlanSoilSampling?: (zones: ProductivityZoneProposal[]) => void;
}

const classLabel: Record<string, string> = {
  high: 'مرتفعة',
  medium: 'متوسطة',
  low: 'منخفضة',
};

export function ProductivityZonesPanel({
  zones,
  basis = 'multi_index',
  onAccept,
  onReject,
  onPlanSoilSampling,
}: ProductivityZonesPanelProps) {
  if (!zones.length) return null;
  return (
    <div className="rounded-2xl border border-amber-100 bg-white/95 p-3 shadow-sm" data-testid="productivity-zones-panel">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-800">
            <Layers3 className="h-4 w-4" /> مناطق إنتاجية مقترحة
          </div>
          <div className="text-xs text-slate-500">الأساس: {basis} · لا تُحفَظ إلا بعد التأكيد</div>
        </div>
        <span className="rounded-full border border-amber-100 bg-amber-50 px-2 py-1 text-xs text-amber-700">
          V60 zones
        </span>
      </div>
      <div className="space-y-2">
        {zones.slice(0, 5).map((z, i) => (
          <div key={z.zone_id ?? i} className="rounded-xl border border-slate-100 bg-slate-50 p-2" data-testid="productivity-zone-card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
              <span data-testid="productivity-zone-class">الإنتاجية: {z.label_ar ?? classLabel[z.productivity_class ?? ''] ?? z.productivity_class}</span>
              {typeof z.score === 'number' && <span>الدرجة: {Math.round(z.score * 100)}٪</span>}
              {typeof z.confidence === 'number' && <span>الثقة: {Math.round(z.confidence * 100)}٪</span>}
              {typeof z.area_ha === 'number' && <span>المساحة: {z.area_ha.toFixed(2)} هـ</span>}
            </div>
            {!!z.drivers?.length && <div className="mt-1 text-[11px] text-slate-400">الدوافع: {z.drivers.slice(0, 4).join(' · ')}</div>}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1">
        <button type="button" data-testid="productivity-zones-accept" onClick={() => onAccept?.(zones)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50">
          <CheckCircle2 className="h-3 w-3" /> اعتماد المناطق
        </button>
        <button type="button" data-testid="productivity-zones-soil-sampling" onClick={() => onPlanSoilSampling?.(zones)} className="inline-flex items-center gap-1 rounded-lg border border-sky-200 bg-white px-2 py-1 text-xs text-sky-700 hover:bg-sky-50">
          <Beaker className="h-3 w-3" /> خطط عينات التربة
        </button>
        <button type="button" data-testid="productivity-zones-reject" onClick={onReject} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">
          <XCircle className="h-3 w-3" /> رفض
        </button>
      </div>
    </div>
  );
}
