// ═══════════════════════════════════════════════════════════════
// SAHOOL — PortfolioPage (توزيع ماء المزرعة عبر الحقول)
// يستهلك /api/v1/field-portfolio/allocate: ماء آبار محدودة يُوزَّع على حقول
// متعدّدة وفق الأولويّة والحدّ الأدنى لكلّ حقل ⇒ يُظهر أيّ حقل مَحميّ وأيّها
// مُجهَد/غير مُلبّى. قرار محفظة لا حقل واحد: مَن يُسقى أوّلاً حين لا يكفي الماء؟
// صدق: ما يُعلنه الخادم غير معاير (calibrated=false) يُبرَز ببانر كهرمانيّ.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Layers, Droplets, AlertTriangle, ShieldCheck, Plus, Trash2 } from 'lucide-react';
import { computePortfolioAllocation } from '../services/api';
import type {
  PortfolioAllocInput, PortfolioAllocResult,
  PortfolioFieldInput, PortfolioSourceInput,
} from '../services/api';
import { ErrorState } from '../components/StateViews';
import { useFieldOptions } from '../hooks/useFieldOptions';

// صفوف الإدخال القابلة للتحرير (نصوص ليسهل التحرير، تُحوَّل لأرقام عند الإرسال).
type FieldRow = {
  field_id: string; expected_margin: string; water_demand_m3: string;
  priority: string; min_water_fraction: string; source_ids: string;
};
type SourceRow = { source_id: string; capacity_m3: string };

const DEFAULT_FIELDS: FieldRow[] = [
  { field_id: '', expected_margin: '', water_demand_m3: '', priority: '1', min_water_fraction: '0.2', source_ids: 'بئر-1' },
];
const DEFAULT_SOURCES: SourceRow[] = [
  { source_id: 'بئر-1', capacity_m3: '2000' },
];

const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

export default function PortfolioPage() {
  const fieldOptionsQ = useFieldOptions();
  const fieldOptions = fieldOptionsQ.options;
  const [fields, setFields] = useState<FieldRow[]>(DEFAULT_FIELDS);
  const [sources, setSources] = useState<SourceRow[]>(DEFAULT_SOURCES);
  const [res, setRes] = useState<PortfolioAllocResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(false);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };

  const setField = (i: number, key: keyof FieldRow, v: string) =>
    setFields(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const setSource = (i: number, key: keyof SourceRow, v: string) =>
    setSources(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));

  const addField = () => setFields(rows => [...rows, {
    field_id: '', expected_margin: '', water_demand_m3: '',
    priority: '1', min_water_fraction: '0.2', source_ids: sources[0]?.source_id ?? '',
  }]);
  const removeField = (i: number) => setFields(rows => rows.filter((_, j) => j !== i));
  const addSource = () => setSources(rows => [...rows, { source_id: `بئر-${rows.length + 1}`, capacity_m3: '1000' }]);
  const removeSource = (i: number) => setSources(rows => rows.filter((_, j) => j !== i));

  const buildPayload = (): PortfolioAllocInput => {
    const f: PortfolioFieldInput[] = fields.filter(r => r.field_id.trim()).map(r => ({
      field_id: r.field_id.trim(),
      expected_margin: numOr(r.expected_margin, 0),
      water_demand_m3: numOr(r.water_demand_m3, 0),
      priority: Math.round(numOr(r.priority, 1)),
      min_water_fraction: numOr(r.min_water_fraction, 0),
      source_ids: r.source_ids.split(',').map(s => s.trim()).filter(Boolean),
    }));
    const s: PortfolioSourceInput[] = sources.map(r => ({
      source_id: r.source_id.trim() || '—',
      capacity_m3: numOr(r.capacity_m3, 0),
    }));
    return { fields: f, sources: s };
  };

  const onAllocate = () => {
    setLoading(true); setErr(false);
    computePortfolioAllocation(buildPayload())
      .then(r => setRes(r))
      .catch(() => { setRes(null); setErr(true); })
      .finally(() => setLoading(false));
  };

  // الحالة من الحقل المنظَّم في الخادم: full | partial | protected_min | unmet (+ stressed).
  const statusView = (st: string, stressed: boolean): { label: string; cls: string } => {
    if (st === 'unmet') return { label: 'غير مُلبّى', cls: 'text-red-300' };
    if (st === 'protected_min') return { label: 'محميّ (حدّ أدنى)', cls: 'text-emerald-300' };
    if (st === 'full') return { label: stressed ? 'كامل' : 'كامل', cls: 'text-emerald-300' };
    if (st === 'partial' || stressed) return { label: 'مُجهَد', cls: 'text-orange-300' };
    return { label: st || '—', cls: 'text-slate-300' };
  };
  const rowBg = (st: string, stressed: boolean): string | undefined => {
    if (st === 'unmet') return '#2a0d0d';
    if (st === 'protected_min') return '#0c2a1a';
    if (st === 'partial' || stressed) return '#2a1a00';
    return undefined;
  };

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Layers className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">توزيع ماء المزرعة</h2>
      </div>
      <p className="text-sm text-slate-400">
        حين لا يكفي ماء الآبار كلّ الحقول، مَن يُسقى أوّلاً؟ يوزّع المحرّك السعة المحدودة وفق
        <span className="text-slate-300"> الأولويّة والهامش المتوقّع والحدّ الأدنى لكلّ حقل</span>،
        فيُظهر الحقول <span className="text-emerald-300">المحميّة</span> مقابل
        <span className="text-orange-300"> المُجهَدة</span> و<span className="text-red-300">غير المُلبّاة</span>.
        كلّ القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>.
      </p>

      {/* Sources form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Droplets className="w-4 h-4 text-sky-400" /> مصادر الماء (الآبار)
          </div>
          <button onClick={addSource}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs"
            style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف بئراً
          </button>
        </div>
        {sources.map((s, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف المصدر</span>
              <input value={s.source_id} onChange={e => setSource(i, 'source_id', e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">السعة (م³)</span>
              <input type="number" inputMode="decimal" step="any" value={s.capacity_m3}
                onChange={e => setSource(i, 'capacity_m3', e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
            </label>
            <button onClick={() => removeSource(i)} disabled={sources.length <= 1}
              title="حذف المصدر" className="p-2 rounded-lg text-slate-500 hover:text-red-400 disabled:opacity-40"
              style={inputStyle}>
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      {/* Fields form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Layers className="w-4 h-4 text-sky-400" /> الحقول
          </div>
          <button onClick={addField}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs"
            style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف حقلاً
          </button>
        </div>
        {fields.map((f, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-2" style={{ borderColor: '#25303f' }}>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">حقل {i + 1}</span>
              <button onClick={() => removeField(i)} disabled={fields.length <= 1}
                title="حذف الحقل" className="p-1 rounded text-slate-500 hover:text-red-400 disabled:opacity-40">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المعرّف</span>
                <select value={f.field_id} onChange={e => setField(i, 'field_id', e.target.value)}
                  disabled={fieldOptionsQ.isLoading || fieldOptionsQ.isError || fieldOptions.length === 0}
                  className="px-3 py-2 rounded-lg text-sm disabled:opacity-60" style={inputStyle}>
                  <option value="">اختر الحقل</option>
                  {fieldOptions.map((opt) => <option key={opt.id} value={opt.id}>{opt.name}{opt.crop && opt.crop !== '—' ? ` · ${opt.crop}` : ''}</option>)}
                </select>
              </label>
              {[
                { k: 'priority' as const, label: 'الأولويّة (أعلى = أهمّ)' },
                { k: 'water_demand_m3' as const, label: 'الطلب على الماء (م³)' },
                { k: 'min_water_fraction' as const, label: 'الحدّ الأدنى (نسبة 0–1)' },
                { k: 'expected_margin' as const, label: 'الهامش المتوقّع' },
              ].map(fld => (
                <label key={fld.k} className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">{fld.label}</span>
                  <input type="number" inputMode="decimal" step="any" value={f[fld.k]}
                    onChange={e => setField(i, fld.k, e.target.value)}
                    className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                </label>
              ))}
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المصادر (افصل بفاصلة)</span>
                <input value={f.source_ids} onChange={e => setField(i, 'source_ids', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
            </div>
          </div>
        ))}
        <div className="flex justify-end">
          <button onClick={onAllocate} disabled={loading || !fields.some((r) => r.field_id.trim())}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Droplets className="w-4 h-4" />
            {loading ? 'جارٍ التوزيع…' : 'وزّع الماء'}
          </button>
        </div>
      </div>

      {err && <ErrorState title="تعذّر توزيع الماء" onRetry={onAllocate} />}

      {res && (
        <div className="space-y-4">
          {/* Uncalibrated / warnings banner */}
          {(!res.calibrated || res.warnings_ar.length > 0) && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                {!res.calibrated && (
                  <div className="text-sm font-semibold text-amber-200">🟡 توزيع غير مُعاير — قيم تقديريّة لا قاطعة.</div>
                )}
                {res.warnings_ar.map((w, i) => (
                  <div key={i} className="text-[11px] text-amber-300/80">• {w}</div>
                ))}
              </div>
            </div>
          )}

          {/* Totals */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'إجمالي الهامش المُحقَّق', v: res.total_expected_margin.toFixed(0) },
              { label: 'إجمالي الماء المُوزَّع (م³)', v: res.total_allocated_m3.toFixed(0) },
              { label: 'حقول محميّة', v: String(res.protected_fields.length) },
              { label: 'حقول مُجهَدة/غير مُلبّاة', v: String(res.stressed_fields.length + res.unmet_fields.length) },
            ].map((x, i) => (
              <div key={i} className="rounded-xl p-3 border text-center" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1">{x.label}</div>
                <div className="text-lg font-bold text-slate-100">{x.v}</div>
              </div>
            ))}
          </div>

          {/* Per-field table */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Layers className="w-4 h-4 text-sky-400" /> توزيع الماء على الحقول
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                    <th className="px-3 py-2 text-right font-medium">الحقل</th>
                    <th className="px-3 py-2 text-right font-medium">الأولويّة</th>
                    <th className="px-3 py-2 text-right font-medium">الطلب (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">المُوزَّع (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">النسبة</th>
                    <th className="px-3 py-2 text-right font-medium">الهامش المُحقَّق</th>
                    <th className="px-3 py-2 text-right font-medium">المصادر</th>
                    <th className="px-3 py-2 text-right font-medium">الحالة</th>
                  </tr>
                </thead>
                <tbody>
                  {res.fields.map((f, i) => {
                    const sv = statusView(f.status, f.stressed);
                    return (
                      <tr key={i} className="text-slate-300"
                        style={{ borderBottom: '1px solid #25303f', background: rowBg(f.status, f.stressed) }}>
                        <td className="px-3 py-1.5 font-medium text-slate-100">{f.field_id}</td>
                        <td className="px-3 py-1.5">{f.priority}</td>
                        <td className="px-3 py-1.5">{f.water_demand_m3.toFixed(0)}</td>
                        <td className="px-3 py-1.5 font-semibold text-slate-100">{f.allocated_m3.toFixed(0)}</td>
                        <td className="px-3 py-1.5">{(f.fraction * 100).toFixed(0)}٪</td>
                        <td className="px-3 py-1.5">{f.expected_margin_captured.toFixed(0)}</td>
                        <td className="px-3 py-1.5 text-xs text-slate-400">{Object.keys(f.sources_used).length ? Object.keys(f.sources_used).join('، ') : '—'}</td>
                        <td className="px-3 py-1.5 text-xs">
                          <span className={`font-semibold inline-flex items-center gap-1 ${sv.cls}`}>
                            {f.status === 'protected_min' && <ShieldCheck className="w-3.5 h-3.5" />}
                            {sv.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Per-source usage */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Droplets className="w-4 h-4 text-sky-400" /> استخدام المصادر
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                  <th className="px-3 py-2 text-right font-medium">المصدر</th>
                  <th className="px-3 py-2 text-right font-medium">السعة (م³)</th>
                  <th className="px-3 py-2 text-right font-medium">المُستخدَم (م³)</th>
                  <th className="px-3 py-2 text-right font-medium">المتبقّي (م³)</th>
                  <th className="px-3 py-2 text-right font-medium">نسبة الاستخدام</th>
                </tr>
              </thead>
              <tbody>
                {res.sources.map((s, i) => {
                  const pct = s.capacity_m3 > 0 ? (s.used_m3 / s.capacity_m3) * 100 : 0;
                  return (
                    <tr key={i} className="text-slate-300" style={{ borderBottom: '1px solid #25303f' }}>
                      <td className="px-3 py-1.5 font-medium text-slate-100">{s.source_id}</td>
                      <td className="px-3 py-1.5">{s.capacity_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-semibold text-slate-100">{s.used_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5">{s.remaining_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5">
                        <div className="flex items-center gap-2">
                          <div className="h-2 rounded-full overflow-hidden flex-1" style={{ background: '#0f1117', minWidth: 60 }}>
                            <div className="h-full rounded-full" style={{
                              width: `${Math.max(0, Math.min(100, pct))}%`,
                              background: pct > 95 ? '#ef4444' : pct > 80 ? '#f59e0b' : '#10b981',
                            }} />
                          </div>
                          <span className="text-[11px] text-slate-400">{pct.toFixed(0)}٪</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
