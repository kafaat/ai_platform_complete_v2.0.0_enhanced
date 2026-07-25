// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationPlanPage (واجهة قرار زراعيّ قابلة للتفسير)
// خطّ «مركز المحاصيل»: نسيج التربة + عمق ⇒ TAW ⇒ سياسة قرار ⇒ جدول ريّ للأيّام القادمة.
// لا تعرض «ما الخطّة؟» فقط بل «لماذا هذه الخطّة؟» + أثر السياسة + المخاطر + الميزانيّة.
// صدق: ما لا يملك الخادم بياناته (حرارة/ملوحة) يُعلَن «يحتاج بيانات» لا يُفبرَك.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Droplets, CalendarRange, AlertTriangle, CloudRain,
  Info, Scale, GitCompare, Gauge,
} from 'lucide-react';
import { useComputeIrrigationPlan } from '../hooks/useApi';
import FieldSelector from '../components/FieldSelector';
import { useSelectedField } from '../hooks/useSelectedField';
import { computeIrrigationPlan } from '../services/api';
import type { IrrigationPlanInput, IrrigationPlanResult, ForecastDayInput } from '../services/api';
import { ErrorState } from '../components/StateViews';
import { useLocation } from 'react-router';

const POLICIES: { key: string; label: string; why: string }[] = [
  { key: 'water_saving',   label: 'توفير الماء (ريّ عجزيّ)', why: 'ينتظر بلوغ RAW ثمّ يملأ جزئيّاً — يحفظ الماء ويقبل إجهاداً خفيفاً' },
  { key: 'yield_max',      label: 'أقصى غلّة',               why: 'يُطلق قبل RAW ويملأ كاملاً — لا إجهاد، أعلى استهلاك' },
  { key: 'profit_max',     label: 'أقصى ربح',                why: 'يوازن تكلفة الماء/الطاقة مقابل قيمة الغلّة (يحتاج أسعاراً)' },
  { key: 'sustainability', label: 'استدامة',                why: 'يترك سعة تخزين للمطر — يقلّل الهدر بالتسرّب العميق' },
  { key: 'risk_averse',    label: 'تجنّب المخاطرة',         why: 'يُطلق مبكّراً بهامش أمان — يحمي من خطأ التنبّؤ' },
];
const POLICY_LABEL: Record<string, string> = Object.fromEntries(POLICIES.map(p => [p.key, p.label]));
const POLICY_WHY: Record<string, string> = Object.fromEntries(POLICIES.map(p => [p.key, p.why]));

const TEXTURES: { key: string; label: string }[] = [
  { key: 'sand', label: 'رمليّ' }, { key: 'sandy_loam', label: 'طميّ-رمليّ' },
  { key: 'loam', label: 'طميّ' }, { key: 'clay_loam', label: 'طميّ-طينيّ' },
  { key: 'silty_clay', label: 'طينيّ-سلتيّ' }, { key: 'clay', label: 'طينيّ' },
];

const SCENARIO_POLICIES = ['water_saving', 'sustainability', 'profit_max', 'yield_max', 'risk_averse'];

type RiskLevel = { label: string; cls: string };
const riskColor = (s: string): string =>
  s === 'منخفض' ? 'text-emerald-300' : s === 'متوسط' ? 'text-amber-300'
    : s === 'مرتفع' ? 'text-orange-300' : 'text-slate-500';

export default function IrrigationPlanPage() {
  const location = useLocation();
  const routeFieldId = ((location.state as { fieldId?: string } | null)?.fieldId) ?? null;
  const { fieldId, field } = useSelectedField({ routeFieldId });
  const mut = useComputeIrrigationPlan();
  const [horizon, setHorizon] = useState('7');
  const [et0, setEt0] = useState('6');
  const [kc, setKc] = useState('1.0');
  const [rain, setRain] = useState('0');
  const [texture, setTexture] = useState('loam');
  const [rootDepth, setRootDepth] = useState('1.0');
  const [p, setP] = useState('0.5');
  const [policy, setPolicy] = useState('water_saving');
  const [initDepletion, setInitDepletion] = useState('0');
  const [budget, setBudget] = useState('');
  const [seasonUsed, setSeasonUsed] = useState('');
  const [waterPrice, setWaterPrice] = useState('');
  const [yieldValue, setYieldValue] = useState('');
  // مقارنة السيناريوهات (نفس البيانات، سياسات مختلفة).
  const [scenarios, setScenarios] = useState<IrrigationPlanResult[] | null>(null);
  const [scenLoading, setScenLoading] = useState(false);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => (s.trim() === '' ? null : numOr(s, 0));

  const buildPayload = (policyOverride?: string): IrrigationPlanInput => {
    const days = Math.max(1, Math.min(60, Math.round(numOr(horizon, 7))));
    const forecast: ForecastDayInput[] = Array.from({ length: days }, () => ({
      et0_mm: numOr(et0, 6), kc: numOr(kc, 1.0), rain_mm: numOr(rain, 0),
    }));
    return {
      ...(fieldId ? { field_id: fieldId } : {}),
      forecast,
      soil_texture: texture,
      root_depth_m: numOr(rootDepth, 1.0),
      raw_fraction: numOr(p, 0.5),
      policy: policyOverride ?? policy,
      initial_depletion_mm: numOr(initDepletion, 0),
      season_budget_mm: optNum(budget),
      water_price_per_m3: optNum(waterPrice),
      yield_value_per_ha: optNum(yieldValue),
    } as IrrigationPlanInput & { field_id?: string };
  };

  const onCompute = () => { setScenarios(null); mut.mutate(buildPayload()); };

  const onCompare = () => {
    setScenLoading(true);
    Promise.all(SCENARIO_POLICIES.map(pol => computeIrrigationPlan(buildPayload(pol))))
      .then(rs => setScenarios(rs))
      .catch(() => setScenarios(null))
      .finally(() => setScenLoading(false));
  };

  const res = mut.data;

  // ── اشتقاقات التفسير/المخاطر (من بيانات الخادم فقط) ──
  const clampPct = (n: number): number => Math.max(0, Math.min(100, n));
  let budgetView: { used: number; remaining: number; pct: number; over: boolean } | null = null;
  if (res && budget.trim() !== '') {
    const cap = numOr(budget, 0);
    const used = numOr(seasonUsed, 0) + res.plan.total_irrigation_mm;
    budgetView = { used, remaining: cap - used, pct: cap > 0 ? clampPct((used / cap) * 100) : 0, over: used > cap };
  }

  const whyBullets = (r: IrrigationPlanResult): string[] => {
    const out: string[] = [];
    out.push(`السياسة: ${POLICY_LABEL[r.plan.policy] ?? r.plan.policy} — ${POLICY_WHY[r.plan.policy] ?? ''}`);
    const rainDays = r.plan.days.filter(d => d.eff_rain_mm > 0 && d.irrigation_mm === 0);
    if (rainDays.length) {
      const maxRain = Math.max(...rainDays.map(d => d.eff_rain_mm));
      out.push(`مطر فعّال متوقّع (حتى ${maxRain.toFixed(1)} مم) يغطّي الحاجة في ${rainDays.length} يوم — أُجِّل الريّ`);
    }
    const depPct = r.plan.taw_mm > 0 ? (r.plan.final_depletion_mm / r.plan.taw_mm) * 100 : 0;
    out.push(`الاستنزاف النهائيّ ${r.plan.final_depletion_mm.toFixed(1)} مم مقابل RAW ${r.plan.raw_mm.toFixed(1)} مم (${depPct.toFixed(0)}% من TAW)`);
    out.push(r.plan.stress_days.length === 0
      ? 'لا إجهاد مائيّ متوقّع خلال الأفق'
      : `${r.plan.stress_days.length} يوم إجهاد متوقّع — راجِع سقف الدفعة/الميزانيّة`);
    out.push(`${r.plan.n_events} دفعة ريّ، إجمالي ${r.plan.total_irrigation_mm.toFixed(1)} مم`);
    return out;
  };

  const QUALITY_AR: Record<string, string> = { low: 'منخفضة', medium: 'متوسطة', high: 'عالية' };
  const qualityColor = (q: string): string =>
    q === 'high' ? riskColor('منخفض') : q === 'medium' ? riskColor('متوسط') : riskColor('مرتفع');

  const risks = (r: IrrigationPlanResult): { label: string; v: RiskLevel }[] => {
    const sd = r.plan.stress_days.length;
    const water = sd === 0 ? 'منخفض' : sd <= 2 ? 'متوسط' : 'مرتفع';
    // الثقة من حقل الجودة المنظَّم في الخادم (لا اشتقاق نصّيّ).
    const conf = `${(r.quality.confidence * 100).toFixed(0)}٪ · ${QUALITY_AR[r.quality.data_quality] ?? r.quality.data_quality}`;
    return [
      { label: 'مائي', v: { label: water, cls: riskColor(water) } },
      { label: 'حراريّ', v: { label: 'يحتاج بيانات', cls: riskColor('—') } },
      { label: 'ملوحة', v: { label: 'يحتاج بيانات', cls: riskColor('—') } },
      { label: 'الثقة', v: { label: conf, cls: qualityColor(r.quality.data_quality) } },
    ];
  };

  // أسباب عدم المعايرة من الحقول المنظَّمة في الخادم (assumptions_ar) لا من تحليل نصوص.
  const uncalibReasons = (r: IrrigationPlanResult): string[] => [...r.quality.assumptions_ar];

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <CalendarRange className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">خطّة الريّ المتنبّأ بها</h2>
      </div>
      <p className="text-sm text-slate-400">
        جدول الريّ للأيّام القادمة عبر خطّ «مركز المحاصيل»: نسيج التربة وعمق الجذور يحدّدان الماء
        المتاح (TAW)، والسياسة تحدّد <span className="text-slate-300">كيف نتصرّف</span> تجاه الاحتياج،
        مع تفسير القرار وأثر السياسة والمخاطر. كلّ القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>.
      </p>

      <FieldSelector label="الحقل الذي ستُبنى عليه خطة الري" />
      {field ? <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs text-slate-300">
        مصدر السياق: <b className="text-slate-100">{field.name}</b> · {field.crop || 'بلا محصول'} · {field.area ? `${field.area} هـ` : 'مساحة غير معروفة'}.
        عند توفر بيانات الطقس/الأقمار/المختبر في الخلفية ستُحقن في محرك الخطة؛ القيم أدناه تبقى قابلة للتعديل اليدوي.
      </div> : null}

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">السياسة (الهدف)</span>
            <select value={policy} onChange={e => setPolicy(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {POLICIES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">نسيج التربة</span>
            <select value={texture} onChange={e => setTexture(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {TEXTURES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </label>
          {[
            { k: 'rootDepth', label: 'عمق الجذور (م)', v: rootDepth, set: setRootDepth },
            { k: 'p', label: 'نسبة الاستنفاد p', v: p, set: setP },
            { k: 'horizon', label: 'أفق التنبّؤ (أيّام)', v: horizon, set: setHorizon },
            { k: 'et0', label: 'ET₀ يوميّ (مم)', v: et0, set: setEt0 },
            { k: 'kc', label: 'معامل المحصول Kc', v: kc, set: setKc },
            { k: 'rain', label: 'مطر متوقّع/يوم (مم)', v: rain, set: setRain },
            { k: 'init', label: 'استنزاف ابتدائيّ (مم)', v: initDepletion, set: setInitDepletion },
            { k: 'budget', label: 'ميزانيّة الموسم (مم)', v: budget, set: setBudget },
            { k: 'used', label: 'مستهلك سابقاً (مم)', v: seasonUsed, set: setSeasonUsed },
            { k: 'wp', label: 'سعر الماء (/م³، للربح)', v: waterPrice, set: setWaterPrice },
            { k: 'yv', label: 'قيمة الغلّة (/ها، للربح)', v: yieldValue, set: setYieldValue },
          ].map(f => (
            <label key={f.k} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{f.label}</span>
              <input type="number" inputMode="decimal" step="any" value={f.v}
                onChange={e => f.set(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          ))}
        </div>
        <p className="text-[11px] text-slate-500">
          تنبّؤ مبسّط موحّد (نفس ET₀/Kc/المطر لكلّ يوم) للتجربة — سيُربط لاحقاً بتنبّؤ جوّيّ يوميّ فعليّ.
        </p>
        <div className="flex justify-end gap-2">
          <button onClick={onCompare} disabled={scenLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-60"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            <GitCompare className="w-4 h-4" />
            {scenLoading ? 'جارٍ المقارنة…' : 'قارن السياسات'}
          </button>
          <button onClick={onCompute} disabled={mut.isPending || !fieldId}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <Droplets className="w-4 h-4" />
            {mut.isPending ? 'جارٍ الحساب…' : 'احسب خطّة الريّ'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر حساب خطّة الريّ" onRetry={onCompute} />}

      {/* Scenario comparison */}
      {scenarios && (
        <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-slate-100" style={{ borderBottom: '1px solid #334155' }}>
            <GitCompare className="w-4 h-4 text-sky-400" /> مقارنة السياسات (نفس البيانات)
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                <th className="px-3 py-2 text-right font-medium">السياسة</th>
                <th className="px-3 py-2 text-right font-medium">الريّ (مم)</th>
                <th className="px-3 py-2 text-right font-medium">م³/ها</th>
                <th className="px-3 py-2 text-right font-medium">دفعات</th>
                <th className="px-3 py-2 text-right font-medium">أيّام إجهاد</th>
                <th className="px-3 py-2 text-right font-medium">استنزاف نهائيّ</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s, i) => (
                <tr key={i} className="text-slate-300" style={{ borderBottom: '1px solid #25303f', background: s.plan.policy === policy ? '#0c2233' : undefined }}>
                  <td className="px-3 py-1.5">{POLICY_LABEL[SCENARIO_POLICIES[i]] ?? SCENARIO_POLICIES[i]}
                    {s.plan.policy !== SCENARIO_POLICIES[i] && <span className="text-[10px] text-amber-300"> (تراجع ⇐ {POLICY_LABEL[s.plan.policy]})</span>}
                  </td>
                  <td className="px-3 py-1.5 font-semibold text-slate-100">{s.plan.total_irrigation_mm.toFixed(1)}</td>
                  <td className="px-3 py-1.5">{s.plan.total_irrigation_m3_ha.toFixed(0)}</td>
                  <td className="px-3 py-1.5">{s.plan.n_events}</td>
                  <td className="px-3 py-1.5">{s.plan.stress_days.length}</td>
                  <td className="px-3 py-1.5">{s.plan.final_depletion_mm.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="px-4 py-2 text-[11px] text-slate-500">أثر السياسة على الريّ والإجهاد ظاهر مباشرةً. «أقصى ربح» يحتاج سعر الماء وقيمة الغلّة وإلّا يتراجع لتوفير الماء.</p>
        </div>
      )}

      {/* Results */}
      {res && (
        <div className="space-y-4">
          {/* 1) Water Budget progress */}
          {budgetView && (
            <div className="rounded-xl border p-4 space-y-2" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1"><Gauge className="w-3.5 h-3.5" /> الحصّة المائيّة الموسميّة</span>
                <span>{budgetView.pct.toFixed(0)}٪</span>
              </div>
              <div className="h-2.5 rounded-full overflow-hidden" style={{ background: '#0f1117' }}>
                <div className="h-full rounded-full" style={{
                  width: `${budgetView.pct}%`,
                  background: budgetView.over ? '#ef4444' : budgetView.pct > 80 ? '#f59e0b' : '#10b981',
                }} />
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-slate-300">استُهلك: {budgetView.used.toFixed(0)} مم</span>
                <span className={budgetView.over ? 'text-red-300' : 'text-slate-300'}>
                  {budgetView.over ? `تجاوز: ${Math.abs(budgetView.remaining).toFixed(0)} مم` : `المتبقّي: ${budgetView.remaining.toFixed(0)} مم`}
                </span>
                <span className="text-slate-500">الميزانيّة: {numOr(budget, 0).toFixed(0)} مم</span>
              </div>
            </div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'الماء المتاح TAW (مم)', v: res.plan.taw_mm.toFixed(1) },
              { label: 'الماء المتاح بيُسر RAW (مم)', v: res.plan.raw_mm.toFixed(1) },
              { label: 'إجمالي الريّ (مم)', v: res.plan.total_irrigation_mm.toFixed(1) },
              { label: 'إجمالي الريّ (م³/هكتار)', v: res.plan.total_irrigation_m3_ha.toFixed(0) },
              { label: 'عدد دفعات الريّ', v: String(res.plan.n_events) },
              { label: 'أيّام الإجهاد', v: String(res.plan.stress_days.length) },
              { label: 'الاستنزاف النهائيّ (مم)', v: res.plan.final_depletion_mm.toFixed(1) },
              { label: 'التسرّب العميق (مم)', v: res.plan.total_deep_perc_mm.toFixed(1) },
            ].map((x, i) => (
              <div key={i} className="rounded-xl p-3 border text-center" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1">{x.label}</div>
                <div className="text-lg font-bold text-slate-100">{x.v}</div>
              </div>
            ))}
          </div>

          {/* 3) Risk strip */}
          <div className="rounded-xl border p-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-1 text-xs text-slate-400 mb-2"><Scale className="w-3.5 h-3.5" /> مخاطر الخطّة</div>
            <div className="grid grid-cols-4 gap-2">
              {risks(res).map((r, i) => (
                <div key={i} className="text-center rounded-lg py-2" style={{ background: '#0f1117' }}>
                  <div className="text-[11px] text-slate-500 mb-0.5">{r.label}</div>
                  <div className={`text-sm font-semibold ${r.v.cls}`}>{r.v.label}</div>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-slate-600 mt-2">الحراريّ/الملوحة «يحتاج بيانات»: لا يحملهما هذا الحساب (يلزم حرارة وEC تربة).</p>
          </div>

          {/* 2) Why this plan */}
          <div className="rounded-xl border p-4" style={{ background: '#0a1626', borderColor: '#0ea5e933' }}>
            <div className="flex items-center gap-1 text-sm font-semibold text-sky-200 mb-2"><Info className="w-4 h-4" /> لماذا هذه الخطّة؟</div>
            <ul className="space-y-1">
              {whyBullets(res).map((b, i) => (
                <li key={i} className="text-[12px] text-slate-300 flex gap-1.5"><span className="text-emerald-400">✓</span>{b}</li>
              ))}
            </ul>
          </div>

          {/* 5) Uncalibrated banner (rich) */}
          <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">🟡 نموذج غير مُعاير — اعتمد على:</div>
              {uncalibReasons(res).map((n, i) => (
                <div key={i} className="text-[11px] text-amber-300/80">• {n}</div>
              ))}
              {res.plan.notes_ar.map((n, i) => (
                <div key={`p${i}`} className="text-[11px] text-slate-400">• {n}</div>
              ))}
            </div>
          </div>

          {/* Days table */}
          <div className="rounded-xl border overflow-hidden" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
                  <th className="px-3 py-2 text-right font-medium">اليوم</th>
                  <th className="px-3 py-2 text-right font-medium">ETc</th>
                  <th className="px-3 py-2 text-right font-medium">مطر فعّال</th>
                  <th className="px-3 py-2 text-right font-medium">استنزاف قبل</th>
                  <th className="px-3 py-2 text-right font-medium">ريّ</th>
                  <th className="px-3 py-2 text-right font-medium">استنزاف بعد</th>
                  <th className="px-3 py-2 text-right font-medium">الحالة</th>
                </tr>
              </thead>
              <tbody>
                {res.plan.days.map(d => {
                  const deferredByRain = d.eff_rain_mm > 0 && d.irrigation_mm === 0;
                  return (
                    <tr key={d.day_index} className="text-slate-300"
                      style={{ borderBottom: '1px solid #25303f', background: d.stressed ? '#2a0d0d' : undefined }}>
                      <td className="px-3 py-1.5">{d.day_index + 1}</td>
                      <td className="px-3 py-1.5">{d.etc_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5">
                        {d.eff_rain_mm > 0
                          ? <span className="inline-flex items-center gap-1 text-sky-300"><CloudRain className="w-3.5 h-3.5" />{d.eff_rain_mm.toFixed(1)}</span>
                          : '—'}
                      </td>
                      <td className="px-3 py-1.5">{d.dr_before_irrig_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5 font-semibold text-slate-100">{d.irrigation_mm > 0 ? d.irrigation_mm.toFixed(1) : '—'}</td>
                      <td className="px-3 py-1.5">{d.dr_end_mm.toFixed(1)}</td>
                      <td className="px-3 py-1.5 text-xs">
                        {d.stressed
                          ? <span className="text-orange-300">إجهاد</span>
                          : deferredByRain
                            ? <span className="text-sky-300">أُجّل (مطر)</span>
                            : d.irrigation_mm > 0
                              ? <span className="text-emerald-300">ريّ</span>
                              : <span className="text-slate-500">—</span>}
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
