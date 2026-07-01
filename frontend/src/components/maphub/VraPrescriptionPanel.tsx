import { CheckCircle2, FileDown, Gauge, Layers3, ShieldAlert, XCircle } from 'lucide-react';

export interface VraPrescriptionZone {
  zone_id?: string;
  productivity_class?: string;
  area_ha?: number;
  rate?: number;
  unit?: string;
  product_type?: string;
  confidence?: number;
  evidence_level?: string;
  rationale_ar?: string;
}

export interface VraPrescription {
  prescription_id?: string;
  product_type?: string;
  crop?: string;
  base_rate?: number;
  average_rate?: number;
  unit?: string;
  total_area_ha?: number;
  confidence?: number;
  readiness_status?: string;
  requires_agronomist_review?: boolean;
}

export interface VraPrescriptionPanelProps {
  prescription?: VraPrescription | null;
  zones: VraPrescriptionZone[];
  warnings?: string[];
  readinessStatus?: string;
  onApprove?: (prescription: VraPrescription | null, zones: VraPrescriptionZone[]) => void;
  onRefine?: () => void;
  onReject?: () => void;
}

const classLabel: Record<string, string> = {
  high: 'مرتفعة',
  medium: 'متوسطة',
  low: 'منخفضة',
};

export function VraPrescriptionPanel({
  prescription,
  zones,
  warnings = [],
  readinessStatus,
  onApprove,
  onRefine,
  onReject,
}: VraPrescriptionPanelProps) {
  if (!prescription || !zones.length) return null;
  const status = readinessStatus || prescription.readiness_status || 'proposal_only';
  return (
    <div className="rounded-2xl border border-violet-100 bg-white/95 p-3 shadow-sm" data-testid="vra-prescription-panel">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-800">
            <Gauge className="h-4 w-4" /> وصفة VRA مقترحة
          </div>
          <div className="text-xs text-slate-500">Map-based · لا تُحفظ ولا تُصدّر للآلة إلا بعد الموافقة والمراجعة</div>
        </div>
        <span className="rounded-full border border-violet-100 bg-violet-50 px-2 py-1 text-xs text-violet-700">
          V62 VRA
        </span>
      </div>

      <div className="mb-2 grid grid-cols-2 gap-2 text-xs text-slate-600 sm:grid-cols-4">
        <div className="rounded-xl bg-slate-50 p-2"><Layers3 className="mb-1 h-3 w-3" /> المناطق: {zones.length}</div>
        <div className="rounded-xl bg-slate-50 p-2">المنتج: {prescription.product_type ?? 'fertilizer'}</div>
        <div className="rounded-xl bg-slate-50 p-2">المتوسط: {prescription.average_rate ?? '—'} {prescription.unit ?? ''}</div>
        <div className="rounded-xl bg-slate-50 p-2">الثقة: {typeof prescription.confidence === 'number' ? `${Math.round(prescription.confidence * 100)}٪` : '—'}</div>
      </div>

      {warnings.length > 0 && (
        <div className="mb-2 rounded-xl border border-amber-100 bg-amber-50 p-2 text-[11px] text-amber-700" data-testid="vra-warning-box">
          <div className="mb-1 flex items-center gap-1 font-semibold"><ShieldAlert className="h-3 w-3" /> تنبيهات قبل الاعتماد</div>
          <ul className="list-disc space-y-1 pr-4">
            {warnings.slice(0, 3).map((w, i) => <li key={`${w}-${i}`}>{w}</li>)}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        {zones.slice(0, 8).map((z, i) => (
          <div key={z.zone_id ?? i} className="rounded-xl border border-slate-100 bg-slate-50 p-2" data-testid="vra-zone-card">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
              <span>المنطقة: {z.zone_id ?? `zone-${i + 1}`}</span>
              <span>الإنتاجية: {classLabel[z.productivity_class ?? ''] ?? z.productivity_class ?? '—'}</span>
              {typeof z.rate === 'number' && <span data-testid="vra-rate">المعدل: {z.rate} {z.unit ?? prescription.unit ?? ''}</span>}
              {typeof z.area_ha === 'number' && <span>{z.area_ha.toFixed(2)} هـ</span>}
            </div>
            {z.rationale_ar && <div className="mt-1 text-[11px] text-slate-500">{z.rationale_ar}</div>}
            {z.evidence_level && <div className="mt-1 text-[11px] text-slate-400">الدليل: {z.evidence_level}</div>}
          </div>
        ))}
      </div>

      <div className="mt-2 text-[11px] text-slate-400" data-testid="vra-readiness-status">الحالة: {status}</div>
      <div className="mt-3 flex flex-wrap gap-1">
        <button type="button" data-testid="vra-approve" onClick={() => onApprove?.(prescription, zones)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50">
          <CheckCircle2 className="h-3 w-3" /> طلب اعتماد الوصفة
        </button>
        <button type="button" data-testid="vra-export-disabled" disabled className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-400">
          <FileDown className="h-3 w-3" /> تصدير آلة بعد الموافقة فقط
        </button>
        <button type="button" data-testid="vra-refine" onClick={onRefine} className="inline-flex items-center gap-1 rounded-lg border border-violet-200 bg-white px-2 py-1 text-xs text-violet-700 hover:bg-violet-50">
          تحسين بالتحاليل
        </button>
        <button type="button" data-testid="vra-reject" onClick={onReject} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">
          <XCircle className="h-3 w-3" /> رفض
        </button>
      </div>
    </div>
  );
}
