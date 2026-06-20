// ═══════════════════════════════════════════════════════════════
// SAHOOL — PortfolioCommandPage (مركز قيادة المحفظة)
// يستهلك POST /api/v1/portfolio/command: يقارن سياسات ريّ متعدّدة عبر حقول
// المزرعة تحت قيود مصادر الماء (آبار/مضخّات/محاور/شبكة)، فيُراكِب الربح×المخاطرة
// لكلّ سياسة ويُبرِز السياسة الموصى بها — توصية فقط لا تنفيذ ولا حجز ماء.
// صدق: غير المعاير (calibrated=false) يُبرَز ببانر كهرمانيّ؛ warnings_ar تُعرَض كلّها.
// العلم مُطفأً (FEATURE_PORTFOLIO_COMMAND) ⇒ 404 ⇒ رسالة «الميزة غير مُفعَّلة» لا انهيار.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Crosshair, Droplets, Layers, AlertTriangle, Plus, Trash2, Award, ShieldAlert } from 'lucide-react';
import { computePortfolioCommand, asApiError } from '../services/api';
import type {
  PortfolioCommandInput, PortfolioCommandResult,
  PortfolioCommandScenarioInput, PortfolioCommandFieldInput, PortfolioCommandSourceInput,
  PortfolioCommandSourceKind,
} from '../services/api';
import { ErrorState } from '../components/StateViews';

// صفوف الإدخال القابلة للتحرير (نصوص ليسهل التحرير، تُحوَّل لأرقام عند الإرسال).
// الحقول/المصادر مشتركة عبر السياسات؛ الربح/الطلب لكلّ حقل يختلف حسب السياسة.
type FieldRow = {
  field_id: string; priority: string; min_water_fraction: string; source_ids: string;
};
type SourceRow = {
  source_id: string; capacity_m3: string; kind: PortfolioCommandSourceKind;
  max_rate_m3_per_day: string; window_days: string;
};
// لكلّ سياسة: تسمية + قيم (الربح/الطلب) لكلّ حقل بالمعرّف.
type PolicyRow = {
  policy_label: string;
  perField: Record<string, { expected_margin: string; water_demand_m3: string }>;
};

const SOURCE_KINDS: { key: PortfolioCommandSourceKind; label: string }[] = [
  { key: 'well',    label: 'بئر' },
  { key: 'pump',    label: 'مضخّة' },
  { key: 'pivot',   label: 'محور' },
  { key: 'network', label: 'شبكة' },
];

const DEFAULT_FIELDS: FieldRow[] = [
  { field_id: 'حقل-أ', priority: '3', min_water_fraction: '0.4', source_ids: 'بئر-1, مضخّة-1' },
  { field_id: 'حقل-ب', priority: '2', min_water_fraction: '0.3', source_ids: 'بئر-1' },
];
const DEFAULT_SOURCES: SourceRow[] = [
  { source_id: 'بئر-1',   capacity_m3: '1500', kind: 'well', max_rate_m3_per_day: '', window_days: '' },
  { source_id: 'مضخّة-1', capacity_m3: '2000', kind: 'pump', max_rate_m3_per_day: '300', window_days: '5' },
];
// سياستان مبدئيّتان: أقصى ربح (هوامش/طلب أعلى) مقابل توفير الماء (طلب أقلّ).
const DEFAULT_POLICIES: PolicyRow[] = [
  {
    policy_label: 'أقصى ربح',
    perField: {
      'حقل-أ': { expected_margin: '3200', water_demand_m3: '1200' },
      'حقل-ب': { expected_margin: '1800', water_demand_m3: '900' },
    },
  },
  {
    policy_label: 'توفير الماء',
    perField: {
      'حقل-أ': { expected_margin: '2600', water_demand_m3: '800' },
      'حقل-ب': { expected_margin: '1500', water_demand_m3: '600' },
    },
  },
];

const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

export default function PortfolioCommandPage() {
  const [fields, setFields] = useState<FieldRow[]>(DEFAULT_FIELDS);
  const [sources, setSources] = useState<SourceRow[]>(DEFAULT_SOURCES);
  const [policies, setPolicies] = useState<PolicyRow[]>(DEFAULT_POLICIES);
  const [riskAversion, setRiskAversion] = useState('1.0');
  const [res, setRes] = useState<PortfolioCommandResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(false);
  const [featureOff, setFeatureOff] = useState(false);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => (s.trim() === '' ? null : numOr(s, 0));

  // ── محرّرات الحقول/المصادر ──
  const setField = (i: number, key: keyof FieldRow, v: string) =>
    setFields(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const setSource = (i: number, key: keyof SourceRow, v: string) =>
    setSources(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const setPolicyLabel = (i: number, v: string) =>
    setPolicies(rows => rows.map((r, j) => (j === i ? { ...r, policy_label: v } : r)));
  const setPolicyField = (pi: number, fieldId: string, key: 'expected_margin' | 'water_demand_m3', v: string) =>
    setPolicies(rows => rows.map((r, j) => {
      if (j !== pi) return r;
      const cur = r.perField[fieldId] ?? { expected_margin: '0', water_demand_m3: '0' };
      return { ...r, perField: { ...r.perField, [fieldId]: { ...cur, [key]: v } } };
    }));

  const addField = () => setFields(rows => [...rows, {
    field_id: `حقل-${rows.length + 1}`, priority: '1', min_water_fraction: '0.2',
    source_ids: sources[0]?.source_id ?? '',
  }]);
  const removeField = (i: number) => setFields(rows => rows.filter((_, j) => j !== i));
  const addSource = () => setSources(rows => [...rows, {
    source_id: `مصدر-${rows.length + 1}`, capacity_m3: '1000', kind: 'well',
    max_rate_m3_per_day: '', window_days: '',
  }]);
  const removeSource = (i: number) => setSources(rows => rows.filter((_, j) => j !== i));
  const addPolicy = () => setPolicies(rows => [...rows, {
    policy_label: `سياسة-${rows.length + 1}`,
    perField: Object.fromEntries(fields.map(f => [f.field_id, { expected_margin: '1000', water_demand_m3: '500' }])),
  }]);
  const removePolicy = (i: number) => setPolicies(rows => rows.filter((_, j) => j !== i));

  const buildPayload = (): PortfolioCommandInput => {
    const sourceInputs: PortfolioCommandSourceInput[] = sources.map(s => ({
      source_id: s.source_id.trim() || '—',
      capacity_m3: numOr(s.capacity_m3, 0),
      kind: s.kind,
      max_rate_m3_per_day: s.kind === 'pump' ? optNum(s.max_rate_m3_per_day) : null,
      window_days: s.kind === 'pump' ? optNum(s.window_days) : null,
    }));
    const scenarios: PortfolioCommandScenarioInput[] = policies.map(p => {
      const fieldInputs: PortfolioCommandFieldInput[] = fields.map(f => {
        const fid = f.field_id.trim() || '—';
        const pf = p.perField[f.field_id] ?? { expected_margin: '0', water_demand_m3: '0' };
        return {
          field_id: fid,
          expected_margin: numOr(pf.expected_margin, 0),
          water_demand_m3: numOr(pf.water_demand_m3, 0),
          priority: Math.round(numOr(f.priority, 1)),
          min_water_fraction: numOr(f.min_water_fraction, 0),
          source_ids: f.source_ids.split(',').map(x => x.trim()).filter(Boolean),
        };
      });
      return { policy_label: p.policy_label.trim() || '—', fields: fieldInputs, sources: sourceInputs };
    });
    return { scenarios, risk_aversion: numOr(riskAversion, 1.0) };
  };

  const onCompare = () => {
    setLoading(true); setErr(false); setFeatureOff(false);
    computePortfolioCommand(buildPayload())
      .then(r => setRes(r))
      .catch(e => {
        setRes(null);
        // 404 ⇒ العلم مُطفأ (الميزة غير مُفعَّلة) — رسالة ودودة لا حالة خطأ.
        if (asApiError(e).response?.status === 404) setFeatureOff(true);
        else setErr(true);
      })
      .finally(() => setLoading(false));
  };

  // لون درجة المخاطرة: أخضر <0.2، كهرمانيّ <0.5، أحمر ≥0.5.
  const riskColor = (r: number): string => (r < 0.2 ? 'text-emerald-300' : r < 0.5 ? 'text-amber-300' : 'text-red-300');

  const fmt = (n: number | null | undefined): string => (n == null ? '—' : n.toFixed(0));

  // قيود المصدر المُقيَّد بالتدفّق للسياسة الموصى بها (للوحة القيود).
  const recommended = res?.policies.find(p => p.policy === res.recommended_policy) ?? null;
  const boundConstraints = (recommended?.constraints ?? []).filter(c => c.throughput_bound);

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Crosshair className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">مركز قيادة المحفظة</h2>
      </div>
      <p className="text-sm text-slate-400">
        يقارن <span className="text-slate-300">سياسات ريّ متعدّدة</span> عبر حقول المزرعة تحت قيود مصادر الماء
        (آبار/مضخّات/محاور/شبكة)، فيُراكِب <span className="text-slate-300">الربح × المخاطرة</span> لكلّ سياسة ويوصي بأفضلها.
        <span className="text-amber-300"> توصية فقط — لا تنفيذ ولا حجز ماء.</span> كلّ القيم
        <span className="text-amber-300"> تقديريّة غير معايَرة</span>.
      </p>

      {/* Risk aversion */}
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 max-w-xs">
          <span className="text-xs text-slate-400">نُفور المخاطرة (٠ = ربح صرف، أعلى = نُفور أكبر)</span>
          <input type="number" inputMode="decimal" step="any" value={riskAversion}
            onChange={e => setRiskAversion(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
        </label>
      </div>

      {/* Sources form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Droplets className="w-4 h-4 text-sky-400" /> مصادر الماء
          </div>
          <button onClick={addSource} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs" style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف مصدراً
          </button>
        </div>
        {sources.map((s, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-2" style={{ borderColor: '#25303f' }}>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">مصدر {i + 1}</span>
              <button onClick={() => removeSource(i)} disabled={sources.length <= 1}
                title="حذف المصدر" className="p-1 rounded text-slate-500 hover:text-red-400 disabled:opacity-40">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المعرّف</span>
                <input value={s.source_id} onChange={e => setSource(i, 'source_id', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">السعة (م³)</span>
                <input type="number" inputMode="decimal" step="any" value={s.capacity_m3}
                  onChange={e => setSource(i, 'capacity_m3', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">النوع</span>
                <select value={s.kind} onChange={e => setSource(i, 'kind', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle}>
                  {SOURCE_KINDS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              </label>
              {s.kind === 'pump' && (
                <>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">أقصى تدفّق (م³/يوم)</span>
                    <input type="number" inputMode="decimal" step="any" value={s.max_rate_m3_per_day}
                      onChange={e => setSource(i, 'max_rate_m3_per_day', e.target.value)}
                      className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-xs text-slate-400">نافذة التشغيل (أيّام)</span>
                    <input type="number" inputMode="decimal" step="any" value={s.window_days}
                      onChange={e => setSource(i, 'window_days', e.target.value)}
                      className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                  </label>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Fields form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Layers className="w-4 h-4 text-sky-400" /> الحقول (مشتركة عبر السياسات)
          </div>
          <button onClick={addField} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs" style={inputStyle}>
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
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المعرّف</span>
                <input value={f.field_id} onChange={e => setField(i, 'field_id', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">الأولويّة (أعلى = أهمّ)</span>
                <input type="number" inputMode="decimal" step="any" value={f.priority}
                  onChange={e => setField(i, 'priority', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">الحدّ الأدنى (نسبة 0–1)</span>
                <input type="number" inputMode="decimal" step="any" value={f.min_water_fraction}
                  onChange={e => setField(i, 'min_water_fraction', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المصادر (افصل بفاصلة، فارغة = الكلّ)</span>
                <input value={f.source_ids} onChange={e => setField(i, 'source_ids', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
            </div>
          </div>
        ))}
      </div>

      {/* Policies form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Crosshair className="w-4 h-4 text-sky-400" /> السياسات (الربح/الطلب لكلّ حقل)
          </div>
          <button onClick={addPolicy} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs" style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف سياسة
          </button>
        </div>
        {policies.map((p, pi) => (
          <div key={pi} className="rounded-lg border p-3 space-y-2" style={{ borderColor: '#25303f' }}>
            <div className="flex items-center justify-between gap-2">
              <label className="flex flex-col gap-1 flex-1">
                <span className="text-xs text-slate-400">اسم السياسة</span>
                <input value={p.policy_label} onChange={e => setPolicyLabel(pi, e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <button onClick={() => removePolicy(pi)} disabled={policies.length <= 1}
                title="حذف السياسة" className="p-1 mt-5 rounded text-slate-500 hover:text-red-400 disabled:opacity-40">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="space-y-2">
              {fields.map((f, fi) => {
                const pf = p.perField[f.field_id] ?? { expected_margin: '', water_demand_m3: '' };
                return (
                  <div key={fi} className="grid grid-cols-[1fr_1fr_1fr] gap-2 items-end">
                    <div className="text-xs text-slate-300 pb-2">{f.field_id || `حقل ${fi + 1}`}</div>
                    <label className="flex flex-col gap-1">
                      <span className="text-[11px] text-slate-500">الهامش المتوقّع</span>
                      <input type="number" inputMode="decimal" step="any" value={pf.expected_margin}
                        onChange={e => setPolicyField(pi, f.field_id, 'expected_margin', e.target.value)}
                        className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </label>
                    <label className="flex flex-col gap-1">
                      <span className="text-[11px] text-slate-500">الطلب (م³)</span>
                      <input type="number" inputMode="decimal" step="any" value={pf.water_demand_m3}
                        onChange={e => setPolicyField(pi, f.field_id, 'water_demand_m3', e.target.value)}
                        className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </label>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
        <div className="flex justify-end">
          <button onClick={onCompare} disabled={loading}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Crosshair className="w-4 h-4" />
            {loading ? 'جارٍ المقارنة…' : 'قارن السياسات'}
          </button>
        </div>
      </div>

      {/* الميزة غير مُفعَّلة (404 — العلم مُطفأ) */}
      {featureOff && (
        <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <ShieldAlert className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-slate-200">الميزة غير مُفعَّلة</div>
            <div className="text-[12px] text-slate-400">
              مركز قيادة المحفظة خلف علم تشغيل (FEATURE_PORTFOLIO_COMMAND) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {err && <ErrorState title="تعذّرت مقارنة السياسات" onRetry={onCompare} />}

      {res && (
        <div className="space-y-4">
          {/* توصية فقط — لا تنفيذ (بانر بارز) */}
          <div className="rounded-xl border p-3 flex items-center gap-2" style={{ background: '#1a1400', borderColor: '#f59e0b55' }}>
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span className="text-sm font-semibold text-amber-200">توصية فقط — لا تنفيذ ولا حجز ماء.</span>
          </div>

          {/* Uncalibrated / warnings banner */}
          {(!res.calibrated || res.warnings_ar.length > 0) && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                {!res.calibrated && (
                  <div className="text-sm font-semibold text-amber-200">🟡 تقديريّ غير معايَر — قيم لا قاطعة.</div>
                )}
                {res.warnings_ar.map((w, i) => (
                  <div key={i} className="text-[11px] text-amber-300/80">• {w}</div>
                ))}
              </div>
            </div>
          )}

          {/* Profit × Risk comparison table */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Crosshair className="w-4 h-4 text-sky-400" /> مقارنة الربح × المخاطرة لكلّ سياسة
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                    <th className="px-3 py-2 text-right font-medium">السياسة</th>
                    <th className="px-3 py-2 text-right font-medium">الهامش الإجماليّ</th>
                    <th className="px-3 py-2 text-right font-medium">درجة المخاطرة</th>
                    <th className="px-3 py-2 text-right font-medium">نسبة التلبية</th>
                    <th className="px-3 py-2 text-right font-medium">مُجهَدة</th>
                    <th className="px-3 py-2 text-right font-medium">غير مُلبّاة</th>
                    <th className="px-3 py-2 text-right font-medium">درجة الهدف</th>
                  </tr>
                </thead>
                <tbody>
                  {res.policies.map((p, i) => {
                    const isRec = p.policy === res.recommended_policy;
                    return (
                      <tr key={i} className="text-slate-300"
                        style={{ borderBottom: '1px solid #25303f', background: isRec ? '#0c2233' : undefined }}>
                        <td className="px-3 py-1.5 font-medium text-slate-100">
                          {p.policy}
                          {isRec && (
                            <span className="inline-flex items-center gap-1 mr-2 px-2 py-0.5 rounded-full text-[10px] font-semibold text-emerald-200"
                              style={{ background: '#0c2a1a', border: '1px solid #10b98155' }}>
                              <Award className="w-3 h-3" /> موصى بها
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-1.5 font-semibold text-slate-100">{fmt(p.total_expected_margin)}</td>
                        <td className={`px-3 py-1.5 font-semibold ${riskColor(p.risk_score)}`}>{p.risk_score.toFixed(2)}</td>
                        <td className="px-3 py-1.5">{(p.served_fraction * 100).toFixed(0)}٪</td>
                        <td className="px-3 py-1.5">{p.stressed_count}</td>
                        <td className="px-3 py-1.5">{p.unmet_count}</td>
                        <td className="px-3 py-1.5">{p.objective_score.toFixed(1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Constraints panel — throughput-bound sources for the recommended policy */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Droplets className="w-4 h-4 text-sky-400" /> قيود المصادر (للسياسة الموصى بها: {res.recommended_policy})
            </div>
            {boundConstraints.length === 0 ? (
              <div className="px-4 py-3 text-[12px] text-slate-400">
                لا مصدر مُقيَّد بتدفّقه في السياسة الموصى بها — السعة الفعليّة = السعة الاسميّة لكلّ المصادر.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                    <th className="px-3 py-2 text-right font-medium">المصدر</th>
                    <th className="px-3 py-2 text-right font-medium">النوع</th>
                    <th className="px-3 py-2 text-right font-medium">السعة الاسميّة (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">السعة الفعليّة (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">الحالة</th>
                  </tr>
                </thead>
                <tbody>
                  {boundConstraints.map((c, i) => (
                    <tr key={i} className="text-slate-300" style={{ borderBottom: '1px solid #25303f', background: '#2a1a00' }}>
                      <td className="px-3 py-1.5 font-medium text-slate-100">{c.source_id}</td>
                      <td className="px-3 py-1.5 text-xs text-slate-400">
                        {SOURCE_KINDS.find(k => k.key === c.kind)?.label ?? c.kind}
                      </td>
                      <td className="px-3 py-1.5">{c.capacity_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5 font-semibold text-amber-200">{c.effective_capacity_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5 text-xs text-amber-300">المضخّة قيَّدها تدفّقها</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
