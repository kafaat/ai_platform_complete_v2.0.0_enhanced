// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationNetworkPage (توأم شبكة الريّ)
// يستهلك POST /api/v1/irrigation/network/feasibility: المستخدم يُعرّف شبكة ريّ
// (عُقد + حوافّ: بئر→مضخّة→…→منطقة)، فيفحص المحرّك جدوى التنفيذ قبل أيّ ريّ
// (اتّصاليّة/توفّر ماء/تدفّق/ضغط) ويُبرِز الاختناقات. قراءة/توصية فقط —
// لا تنفيذ ولا فتح صمّامات.
// صدق: القيود غير المحدَّدة تُعرَض صراحةً كـ«غير مفحوص» (لا تُفترَض ناجحة) —
// المنطقة feasible_unverified ليست مرور نظيف. warnings_ar تُعرَض كلّها.
// العلم مُطفأً (FEATURE_IRRIGATION_NETWORK) ⇒ 404 ⇒ رسالة «الميزة غير مُفعَّلة».
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Share2, Droplets, Network, AlertTriangle, Plus, Trash2, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react';
import { checkIrrigationNetworkFeasibility, asApiError } from '../services/api';
import type {
  IrrigationNetworkInput, IrrigationNetworkResult,
  IrrigationNetworkNode, IrrigationNetworkEdge, IrrigationNetworkNodeKind,
  IrrigationZoneStatus,
} from '../services/api';
import { ErrorState } from '../components/StateViews';

// صفوف الإدخال القابلة للتحرير (نصوص ليسهل التحرير، تُحوَّل لأرقام عند الإرسال).
// كلّ حقول القيود اختياريّة: الفارغ ⇒ null (غير محدَّد ⇒ يُعرَض كـ«غير مفحوص»).
type NodeRow = {
  node_id: string; kind: IrrigationNetworkNodeKind;
  capacity_m3: string; max_throughput_m3: string;
  max_pressure_bar: string; min_pressure_bar: string; demand_m3: string;
};
type EdgeRow = { from_id: string; to_id: string };

const NODE_KINDS: { key: IrrigationNetworkNodeKind; label: string }[] = [
  { key: 'well',       label: 'بئر' },
  { key: 'pump',       label: 'مضخّة' },
  { key: 'filter',     label: 'مُرشِّح' },
  { key: 'fertilizer', label: 'مُسمِّد' },
  { key: 'main_line',  label: 'خطّ رئيسيّ' },
  { key: 'submain',    label: 'خطّ فرعيّ' },
  { key: 'valve',      label: 'صمّام' },
  { key: 'zone',       label: 'منطقة' },
];
const kindLabel = (k: string): string => NODE_KINDS.find(o => o.key === k)?.label ?? k;

// شبكة مبدئيّة قابلة للعرض: بئر→مضخّة→صمّام→منطقة (منطقة واحدة بطلب).
const DEFAULT_NODES: NodeRow[] = [
  { node_id: 'w1', kind: 'well',  capacity_m3: '1000', max_throughput_m3: '',    max_pressure_bar: '',    min_pressure_bar: '',    demand_m3: '' },
  { node_id: 'p1', kind: 'pump',  capacity_m3: '',     max_throughput_m3: '500', max_pressure_bar: '3.0', min_pressure_bar: '',    demand_m3: '' },
  { node_id: 'v1', kind: 'valve', capacity_m3: '',     max_throughput_m3: '500', max_pressure_bar: '',    min_pressure_bar: '',    demand_m3: '' },
  { node_id: 'z1', kind: 'zone',  capacity_m3: '',     max_throughput_m3: '',    max_pressure_bar: '',    min_pressure_bar: '2.0', demand_m3: '300' },
];
const DEFAULT_EDGES: EdgeRow[] = [
  { from_id: 'w1', to_id: 'p1' },
  { from_id: 'p1', to_id: 'v1' },
  { from_id: 'v1', to_id: 'z1' },
];

const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

// حقول القيود المعروضة لكلّ نوع (مرشِد فقط — كلّها اختياريّة وتُرسَل إن مُلئت).
const FIELDS_BY_KIND: Record<IrrigationNetworkNodeKind, (keyof NodeRow)[]> = {
  well:       ['capacity_m3'],
  pump:       ['max_throughput_m3', 'max_pressure_bar'],
  filter:     ['max_throughput_m3'],
  fertilizer: ['max_throughput_m3'],
  main_line:  ['max_throughput_m3'],
  submain:    ['max_throughput_m3'],
  valve:      ['max_throughput_m3'],
  zone:       ['demand_m3', 'min_pressure_bar'],
};
const CONSTRAINT_LABELS: Record<string, string> = {
  capacity_m3: 'السعة (م³)',
  max_throughput_m3: 'أقصى تدفّق (م³)',
  max_pressure_bar: 'أقصى ضغط (بار)',
  min_pressure_bar: 'أدنى ضغط (بار)',
  demand_m3: 'الطلب (م³)',
};

export default function IrrigationNetworkPage() {
  const [nodes, setNodes] = useState<NodeRow[]>(DEFAULT_NODES);
  const [edges, setEdges] = useState<EdgeRow[]>(DEFAULT_EDGES);
  const [res, setRes] = useState<IrrigationNetworkResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(false);
  const [featureOff, setFeatureOff] = useState(false);

  // الفارغ ⇒ null (القيد غير محدَّد، يُعرَض صراحةً كـ«غير مفحوص» في النتائج).
  const optNum = (s: string): number | null => {
    const t = s.trim();
    if (t === '') return null;
    const n = Number(t);
    return isNaN(n) ? null : n;
  };

  const setNode = (i: number, key: keyof NodeRow, v: string) =>
    setNodes(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));
  const setEdge = (i: number, key: keyof EdgeRow, v: string) =>
    setEdges(rows => rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)));

  const addNode = () => setNodes(rows => [...rows, {
    node_id: `n${rows.length + 1}`, kind: 'zone',
    capacity_m3: '', max_throughput_m3: '', max_pressure_bar: '', min_pressure_bar: '', demand_m3: '',
  }]);
  const removeNode = (i: number) => setNodes(rows => rows.filter((_, j) => j !== i));
  const addEdge = () => setEdges(rows => [...rows, {
    from_id: nodes[0]?.node_id ?? '', to_id: nodes[nodes.length - 1]?.node_id ?? '',
  }]);
  const removeEdge = (i: number) => setEdges(rows => rows.filter((_, j) => j !== i));

  const buildPayload = (): IrrigationNetworkInput => {
    const ns: IrrigationNetworkNode[] = nodes.map(n => ({
      node_id: n.node_id.trim() || '—',
      kind: n.kind,
      capacity_m3: optNum(n.capacity_m3),
      max_throughput_m3: optNum(n.max_throughput_m3),
      max_pressure_bar: optNum(n.max_pressure_bar),
      min_pressure_bar: optNum(n.min_pressure_bar),
      demand_m3: optNum(n.demand_m3),
    }));
    const es: IrrigationNetworkEdge[] = edges.map(e => ({
      from_id: e.from_id.trim(), to_id: e.to_id.trim(),
    }));
    return { nodes: ns, edges: es };
  };

  const onCheck = () => {
    setLoading(true); setErr(false); setFeatureOff(false);
    checkIrrigationNetworkFeasibility(buildPayload())
      .then(r => setRes(r))
      .catch(e => {
        setRes(null);
        // 404 ⇒ العلم مُطفأ (الميزة غير مُفعَّلة) — رسالة ودودة لا حالة خطأ.
        if (asApiError(e).response?.status === 404) setFeatureOff(true);
        else setErr(true);
      })
      .finally(() => setLoading(false));
  };

  const nodeIds = nodes.map(n => n.node_id);

  // عرض حالة المنطقة: feasible=أخضر، feasible_unverified=كهرمانيّ، infeasible=أحمر.
  const statusView = (st: IrrigationZoneStatus): { label: string; cls: string; bg: string; border: string } => {
    if (st === 'feasible') return { label: 'مُجدية', cls: 'text-emerald-300', bg: '#0c2a1a', border: '#10b98155' };
    if (st === 'feasible_unverified') return { label: 'مُجدية (غير متحقَّق منها)', cls: 'text-amber-300', bg: '#2a1a00', border: '#f59e0b55' };
    return { label: 'غير مُجدية', cls: 'text-red-300', bg: '#2a0d0d', border: '#ef444455' };
  };

  // المسار يُعرَض من البئر إلى المنطقة: الخادم يردّ [zone,…,well] ⇒ نعكسه للعرض.
  const renderPath = (path: string[] | null): string =>
    path == null ? 'مقطوعة' : [...path].reverse().join(' → ');

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Share2 className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">توأم شبكة الريّ</h2>
      </div>
      <p className="text-sm text-slate-400">
        عرِّف شبكة الريّ (<span className="text-slate-300">عُقد وحوافّ: بئر ← مضخّة ← … ← منطقة</span>)،
        فيفحص المحرّك <span className="text-slate-300">جدوى التنفيذ قبل أيّ ريّ</span>
        (اتّصاليّة / توفّر ماء / تدفّق / ضغط) ويُبرِز الاختناقات.
        <span className="text-amber-300"> توصية فقط — لا تنفيذ ولا فتح صمّامات.</span>
        القيود غير المحدَّدة تُعرَض صراحةً كـ<span className="text-amber-300">«غير مفحوص»</span> (لا تُفترَض ناجحة).
      </p>

      {/* Nodes form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Network className="w-4 h-4 text-sky-400" /> العُقد (مكوّنات الشبكة)
          </div>
          <button onClick={addNode} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs" style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف عُقدة
          </button>
        </div>
        {nodes.map((n, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-2" style={{ borderColor: '#25303f' }}>
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">عُقدة {i + 1}</span>
              <button onClick={() => removeNode(i)} disabled={nodes.length <= 1}
                title="حذف العُقدة" className="p-1 rounded text-slate-500 hover:text-red-400 disabled:opacity-40">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">المعرّف</span>
                <input value={n.node_id} onChange={e => setNode(i, 'node_id', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-slate-400">النوع</span>
                <select value={n.kind} onChange={e => setNode(i, 'kind', e.target.value)}
                  className="px-3 py-2 rounded-lg text-sm" style={inputStyle}>
                  {NODE_KINDS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
                </select>
              </label>
              {FIELDS_BY_KIND[n.kind].map(fk => (
                <label key={fk} className="flex flex-col gap-1">
                  <span className="text-xs text-slate-400">{CONSTRAINT_LABELS[fk]}</span>
                  <input type="number" inputMode="decimal" step="any" value={n[fk]}
                    onChange={e => setNode(i, fk, e.target.value)}
                    placeholder="اختياريّ"
                    className="px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Edges form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 text-sm font-semibold text-slate-100">
            <Share2 className="w-4 h-4 text-sky-400" /> الحوافّ (الوصلات بين العُقد)
          </div>
          <button onClick={addEdge} disabled={nodes.length < 2}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs disabled:opacity-40" style={inputStyle}>
            <Plus className="w-3.5 h-3.5" /> أضف حافّة
          </button>
        </div>
        {edges.map((e, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">من</span>
              <select value={e.from_id} onChange={ev => setEdge(i, 'from_id', ev.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={inputStyle}>
                {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">إلى</span>
              <select value={e.to_id} onChange={ev => setEdge(i, 'to_id', ev.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={inputStyle}>
                {nodeIds.map(id => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
            <button onClick={() => removeEdge(i)} disabled={edges.length <= 1}
              title="حذف الحافّة" className="p-2 rounded-lg text-slate-500 hover:text-red-400 disabled:opacity-40"
              style={inputStyle}>
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
        <div className="flex justify-end">
          <button onClick={onCheck} disabled={loading}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Share2 className="w-4 h-4" />
            {loading ? 'جارٍ الفحص…' : 'افحص الجدوى'}
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
              توأم شبكة الريّ خلف علم تشغيل (FEATURE_IRRIGATION_NETWORK) لم يُفعَّل بعد على الخادم. تواصل مع المسؤول لتفعيله.
            </div>
          </div>
        </div>
      )}

      {err && <ErrorState title="تعذّر فحص جدوى الشبكة" onRetry={onCheck} />}

      {res && (
        <div className="space-y-4">
          {/* توصية فقط — لا تنفيذ (بانر بارز) */}
          <div className="rounded-xl border p-3 flex items-center gap-2" style={{ background: '#1a1400', borderColor: '#f59e0b55' }}>
            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
            <span className="text-sm font-semibold text-amber-200">توصية فقط — لا تنفيذ ولا فتح صمّامات.</span>
          </div>

          {/* Overall feasibility banner */}
          <div className="rounded-xl border p-4 flex items-center gap-3"
            style={res.overall_feasible
              ? { background: '#0c2a1a', borderColor: '#10b98155' }
              : { background: '#2a0d0d', borderColor: '#ef444455' }}>
            {res.overall_feasible
              ? <CheckCircle2 className="w-6 h-6 text-emerald-400 flex-shrink-0" />
              : <XCircle className="w-6 h-6 text-red-400 flex-shrink-0" />}
            <div>
              <div className={`text-base font-bold ${res.overall_feasible ? 'text-emerald-200' : 'text-red-200'}`}>
                {res.overall_feasible ? 'الشبكة مُجدية للتنفيذ' : 'الشبكة غير مُجدية للتنفيذ'}
              </div>
              <div className="text-[12px] text-slate-300">
                {res.feasible_count} من {res.zone_count} منطقة مُجدية
                <span className="text-slate-500"> · المعايرة: {res.calibrated}</span>
              </div>
            </div>
          </div>

          {/* warnings_ar banner (honesty) */}
          {res.warnings_ar.length > 0 && (
            <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
              <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="space-y-1">
                {res.warnings_ar.map((w, i) => (
                  <div key={i} className="text-[11px] text-amber-300/80">• {w}</div>
                ))}
              </div>
            </div>
          )}

          {/* Per-zone feasibility cards */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
              <Network className="w-4 h-4 text-sky-400" /> جدوى المناطق
            </div>
            <div className="p-3 space-y-3">
              {res.zones.map((z, i) => {
                const sv = statusView(z.status);
                return (
                  <div key={i} className="rounded-lg border p-3 space-y-2" style={{ background: sv.bg, borderColor: sv.border }}>
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">{z.zone_id}</span>
                        <span className="text-[11px] text-slate-400">الطلب: {z.demand_m3.toFixed(0)} م³</span>
                      </div>
                      <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${sv.cls}`}
                        style={{ border: `1px solid ${sv.border}` }}>
                        {sv.label}
                      </span>
                    </div>
                    <div className="text-[12px] text-slate-300">
                      <span className="text-slate-500">المسار: </span>
                      {z.path == null
                        ? <span className="text-red-300">مقطوعة (لا اتّصال من بئر)</span>
                        : <span className="font-mono">{renderPath(z.path)}</span>}
                    </div>

                    {/* reasons_ar — only when infeasible */}
                    {z.reasons_ar && z.reasons_ar.length > 0 && (
                      <ul className="space-y-0.5">
                        {z.reasons_ar.map((r, j) => (
                          <li key={j} className="text-[12px] text-red-300">• {r}</li>
                        ))}
                      </ul>
                    )}

                    {/* bottlenecks chips */}
                    {z.bottlenecks.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[11px] text-slate-500">اختناقات:</span>
                        {z.bottlenecks.map((b, j) => (
                          <span key={j} className="px-2 py-0.5 rounded-full text-[11px] font-medium text-red-200"
                            style={{ background: '#2a0d0d', border: '1px solid #ef444455' }}>
                            {b}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* unchecked chips (honesty — constraint NOT specified, NOT asserted) */}
                    {z.unchecked.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-[11px] text-amber-400/80">غير مفحوص:</span>
                        {z.unchecked.map((u, j) => (
                          <span key={j} className="px-2 py-0.5 rounded-full text-[11px] font-medium text-amber-200"
                            style={{ background: '#2a1a00', border: '1px solid #f59e0b55' }}>
                            {u}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Wells panel — capacity vs load */}
          {res.wells.length > 0 && (
            <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
                <Droplets className="w-4 h-4 text-sky-400" /> الآبار (السعة مقابل الحِمل)
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                    <th className="px-3 py-2 text-right font-medium">البئر</th>
                    <th className="px-3 py-2 text-right font-medium">السعة (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">الحِمل (م³)</th>
                    <th className="px-3 py-2 text-right font-medium">الحالة</th>
                  </tr>
                </thead>
                <tbody>
                  {res.wells.map((w, i) => (
                    <tr key={i} className="text-slate-300"
                      style={{ borderBottom: '1px solid #25303f', background: w.over_capacity ? '#2a0d0d' : undefined }}>
                      <td className="px-3 py-1.5 font-medium text-slate-100">{w.well_id}</td>
                      <td className="px-3 py-1.5">{w.capacity_m3.toFixed(0)}</td>
                      <td className={`px-3 py-1.5 font-semibold ${w.over_capacity ? 'text-red-300' : 'text-slate-100'}`}>{w.load_m3.toFixed(0)}</td>
                      <td className="px-3 py-1.5 text-xs">
                        {w.over_capacity
                          ? <span className="font-semibold text-red-300">تجاوز السعة</span>
                          : <span className="text-emerald-300">ضمن السعة</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Honesty footnote — calibration context */}
          <div className="text-[11px] text-slate-500">
            سياق المعايرة: <span className="text-slate-400">{res.calibrated}</span> — فحص بنيويّ
            للجدوى (اتّصاليّة/سعة/تدفّق/ضغط) لا تنبّؤ مُعاير؛ القيود غير المحدَّدة معروضة كـ«غير مفحوص».
          </div>
        </div>
      )}
    </div>
  );
}
