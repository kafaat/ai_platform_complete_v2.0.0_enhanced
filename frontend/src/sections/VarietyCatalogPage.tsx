// كتالوج الأصناف المرجعيّ (بطاقة الأصناف) — reference_only_not_operational.
//
// أوّل مستهلك واجهيّ لنقطتَي الكتالوج المحكوم (PR #627): أصناف الحبوب اليمنيّة الموثّقة
// المصدر. **قراءة صرفة، للعرض/الخبير فقط** — كلّ ردّ يحمل بوّابة الحوكمة
// decision_engine_use_status=reference_only_not_operational، محجوبٌ عن التنفيذ الآليّ
// (لا يُغذّي محرّك القرار). صدق: قضايا الجودة تُعرَض لا تُخفى، ونَسَب المصدر (صفحات/بصمة
// PDF) ظاهرٌ لكلّ صنف.
import { useEffect, useMemo, useState } from 'react';
import {
  fetchFoodGrainVarieties,
  VARIETY_REFERENCE_ONLY_STATUS,
  type FoodGrainVariety,
  type FoodGrainVarietyCatalog,
} from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

const CROP_LABELS: Record<string, string> = {
  wheat: 'قمح',
  barley: 'شعير',
  sorghum: 'ذرة رفيعة',
  maize: 'ذرة شاميّة',
  millet: 'دُخن',
};

// حقول أغرونوميّة تُعرَض في البطاقة إن توفّرت (لا نختلق: تظهر فقط إن كانت في السِجِلّ).
const FIELD_LABELS: Array<{ key: string; label: string }> = [
  { key: 'seed_rate_kg_per_ha', label: 'كميّة البذور (كغ/هـ)' },
  { key: 'maturity_days', label: 'أيّام النضج' },
  { key: 'yield_t_per_ha', label: 'الغلّة (طن/هـ)' },
  { key: 'plant_height_cm', label: 'ارتفاع النبات (سم)' },
  { key: 'sowing_season', label: 'موسم الزراعة' },
];

function GovernanceBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold"
      style={{ background: '#78350f', color: '#fed7aa', border: '1px solid #f59e0b55' }}
      title="بيانات مرجعيّة موثّقة المصدر — محجوبة عن التنفيذ الآليّ؛ تمرّ عبر المسار المحكوم (مرشّح → موافقة خبير)."
      data-testid="variety-governance-badge"
    >
      مرجعيّ فقط · لا يُغذّي القرار آليّاً
    </span>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') return String(v);
  return String(v);
}

function VarietyCard({ v }: { v: FoodGrainVariety }) {
  const [open, setOpen] = useState(false);
  const rows = FIELD_LABELS.filter((f) => v[f.key] !== undefined && v[f.key] !== null);
  const pages = Array.isArray(v.source_pages) ? (v.source_pages as unknown[]).join('، ') : fmt(v.source_pages);
  return (
    <div
      className="rounded-xl p-3 border flex flex-col gap-2"
      style={{ background: 'var(--card, #1c1917)', borderColor: '#44403c' }}
      data-testid="variety-card"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="font-bold text-sm" style={{ color: '#fafaf9' }}>
          {v.name_ar || v.id}
          {v.crop_code ? (
            <span className="ms-2 text-[11px] font-normal" style={{ color: '#a8a29e' }}>
              · {CROP_LABELS[v.crop_code] ?? v.crop_code}
            </span>
          ) : null}
        </div>
      </div>
      {rows.length > 0 && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]" style={{ color: '#d6d3d1' }}>
          {rows.map((f) => (
            <div key={f.key} className="flex justify-between gap-2">
              <span style={{ color: '#a8a29e' }}>{f.label}</span>
              <span className="font-semibold">{fmt(v[f.key])}</span>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="self-start text-[11px] font-semibold px-2 py-0.5 rounded-md"
        style={{ background: '#292524', border: '1px solid #44403c', color: '#e7e5e4' }}
      >
        {open ? 'إخفاء النَسَب' : 'المصدر والنَسَب'}
      </button>
      {open && (
        <div className="text-[11px] rounded-lg p-2" style={{ background: '#0c0a09', color: '#a8a29e' }}>
          <div>الصفحات: {pages}</div>
          <div>التحقّق: {fmt(v.source_verification)}</div>
          <div>المعرّف: {v.id}</div>
        </div>
      )}
    </div>
  );
}

export default function VarietyCatalogPage() {
  const [catalog, setCatalog] = useState<FoodGrainVarietyCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [crop, setCrop] = useState<string>('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(false);
    fetchFoodGrainVarieties(crop || undefined)
      .then((data) => {
        if (alive) setCatalog(data);
      })
      .catch(() => {
        if (alive) setError(true);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [crop, reloadKey]);

  // أكواد المحاصيل من الميتاداتا/الأصناف (لا نُثبّتها: تُشتقّ من السِجِلّ).
  const cropCodes = useMemo(() => {
    const set = new Set<string>();
    (catalog?.varieties ?? []).forEach((v) => v.crop_code && set.add(String(v.crop_code)));
    return Array.from(set).sort();
  }, [catalog]);

  const pdfSha = catalog?.metadata?.source_pdf_sha256;
  const sourceName = catalog?.metadata?.source_name ?? catalog?.metadata?.source;

  return (
    <div className="p-4 flex flex-col gap-4" data-testid="variety-catalog-page">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold" style={{ color: '#fafaf9' }}>كتالوج الأصناف</h1>
          <GovernanceBadge />
        </div>
        {typeof catalog?.count === 'number' && (
          <span className="text-xs" style={{ color: '#a8a29e' }}>{catalog.count} صنفاً موثّقاً</span>
        )}
      </div>

      {Boolean(sourceName || pdfSha) && (
        <div className="text-[11px] rounded-lg p-2" style={{ background: '#0c0a09', color: '#a8a29e' }}>
          {sourceName ? <div>المصدر: {fmt(sourceName)}</div> : null}
          {pdfSha ? <div className="truncate">بصمة PDF (SHA-256): {fmt(pdfSha)}</div> : null}
        </div>
      )}

      {/* مُرشِّح المحصول — مُشتقّ من السِجِلّ. */}
      <div className="flex flex-wrap items-center gap-1.5" data-testid="variety-crop-filter">
        <button
          type="button"
          onClick={() => setCrop('')}
          className="px-2 py-1 rounded-lg text-[11px] font-semibold border"
          style={{ borderColor: crop === '' ? '#22c55e88' : '#44403c', color: '#e7e5e4', background: crop === '' ? '#14532d' : '#1c1917' }}
        >
          الكلّ
        </button>
        {cropCodes.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCrop(c)}
            className="px-2 py-1 rounded-lg text-[11px] font-semibold border"
            style={{ borderColor: crop === c ? '#22c55e88' : '#44403c', color: '#e7e5e4', background: crop === c ? '#14532d' : '#1c1917' }}
          >
            {CROP_LABELS[c] ?? c}
          </button>
        ))}
      </div>

      {loading && <LoadingState message="جارٍ تحميل كتالوج الأصناف…" />}
      {!loading && error && (
        <ErrorState title="تعذّر تحميل كتالوج الأصناف" onRetry={() => setReloadKey((k) => k + 1)} />
      )}
      {!loading && !error && catalog && catalog.varieties.length === 0 && (
        <EmptyState title="لا أصناف مطابقة" hint="جرّب محصولاً آخر أو «الكلّ»." />
      )}

      {!loading && !error && catalog && catalog.varieties.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="variety-grid">
          {catalog.varieties.map((v) => (
            <VarietyCard key={v.id} v={v} />
          ))}
        </div>
      )}

      {/* قضايا الجودة — شفافيّة، لا تُخفى (صدق). */}
      {!loading && !error && catalog && catalog.quality_issues.length > 0 && (
        <div className="rounded-lg p-3 text-[12px]" style={{ background: '#1c1917', border: '1px solid #44403c', color: '#d6d3d1' }} data-testid="variety-quality-issues">
          <div className="font-bold mb-1" style={{ color: '#fbbf24' }}>قضايا الجودة على السِجِلّ ({catalog.quality_issues.length})</div>
          <ul className="list-disc ps-5 flex flex-col gap-0.5">
            {catalog.quality_issues.map((q, i) => (
              <li key={i}>{fmt((q as Record<string, unknown>).message ?? JSON.stringify(q))}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="text-[11px]" style={{ color: '#78716c' }}>
        الحالة: <code>{VARIETY_REFERENCE_ONLY_STATUS}</code> — بياناتٌ مرجعيّة موثّقة المصدر، محجوبةٌ عن
        التنفيذ الآليّ؛ أيّ استخدام قراريّ يمرّ عبر المسار المحكوم (مرشّح → موافقة خبير).
      </div>
    </div>
  );
}
