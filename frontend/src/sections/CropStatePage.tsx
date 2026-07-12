// ═══════════════════════════════════════════════════════════════
// SAHOOL — CropStatePage (حالة المحصول الموحّدة، يستهلك /api/v1/crop-twin/decision)
// قرار واحد من حالة محصول واحدة: حالة + ريّ + تسميد + مخاطر + ثقة + اقتصاد محجوز.
// صدق: calibrated/assumptions ظاهرة؛ ما لا يحمله الخادم (حرارة/ملوحة/اقتصاد) معلَن لا مُفبرَك.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import {
  Sprout, Droplets, FlaskConical, Scale, Info, AlertTriangle, Coins, MapPin,
} from 'lucide-react';
import { useCropDecision, useFields } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import type { CropDecisionInput, CropDecisionForecastDay } from '../services/api';
import { ErrorState } from '../components/StateViews';

// الحقل الخام كما يصل من useFields — نقرأ منه فقط ما نعبّئ به النموذج بصدق.
interface PrefillField {
  field_id?: string | number;
  id?: string | number;
  crop?: string | null;
  ndvi?: string | number | null;
}

const POLICIES: { key: string; label: string }[] = [
  { key: 'water_saving',   label: 'توفير الماء' },
  { key: 'yield_max',      label: 'أقصى غلّة' },
  { key: 'profit_max',     label: 'أقصى ربح' },
  { key: 'sustainability', label: 'استدامة' },
  { key: 'risk_averse',    label: 'تجنّب المخاطرة' },
];
const TEXTURES: { key: string; label: string }[] = [
  { key: 'sand', label: 'رمليّ' }, { key: 'sandy_loam', label: 'طميّ-رمليّ' },
  { key: 'loam', label: 'طميّ' }, { key: 'clay_loam', label: 'طميّ-طينيّ' },
  { key: 'clay', label: 'طينيّ' },
];
const STAGES: { key: string; label: string }[] = [
  { key: 'initial', label: 'بدئيّة' }, { key: 'development', label: 'نموّ' },
  { key: 'mid', label: 'وسطيّة' }, { key: 'late', label: 'متأخّرة' },
];
const QUALITY_AR: Record<string, string> = { low: 'منخفضة', medium: 'متوسطة', high: 'عالية' };
const riskColor = (s: string): string =>
  s === 'منخفض' ? 'text-emerald-300' : s === 'متوسط' ? 'text-amber-300'
    : s === 'مرتفع' ? 'text-orange-300' : 'text-slate-500';

export default function CropStatePage() {
  const mut = useCropDecision();
  // اختيار الحقل المشترك عبر الشاشات (علّة مُبلَّغة 2026-07-11: لا اختيار حقل هنا).
  // التعبئة المسبقة صادقة: المحصول وNDVI فقط — ما يحمله سجلّ الحقل فعلاً، والباقي يدويّ.
  const { fieldId, setFieldId, options: fieldOptions } = useSelectedField();
  const fieldsQ = useFields();
  const [crop, setCrop] = useState('wheat');
  const [stage, setStage] = useState('mid');
  const [ndvi, setNdvi] = useState('0.72');
  const [texture, setTexture] = useState('loam');
  const [rootDepth, setRootDepth] = useState('1.0');
  const [policy, setPolicy] = useState('water_saving');
  const [horizon, setHorizon] = useState('7');
  const [et0, setEt0] = useState('7');
  const [rain, setRain] = useState('0');
  const [target, setTarget] = useState('120');
  const [initDepletion, setInitDepletion] = useState('30');

  useEffect(() => {
    if (!fieldId) return;
    const raw = ((fieldsQ.data?.fields ?? []) as PrefillField[]).find(
      (f) => String(f.field_id ?? f.id) === fieldId,
    );
    if (!raw) return;
    if (raw.crop) setCrop(String(raw.crop));
    const n = Number(raw.ndvi);
    if (Number.isFinite(n) && n > 0) setNdvi(String(n));
  }, [fieldId, fieldsQ.data]);

  const numOr = (s: string, d: number): number => {
    const n = Number(s);
    return s.trim() === '' || isNaN(n) ? d : n;
  };
  const optNum = (s: string): number | null => (s.trim() === '' ? null : numOr(s, 0));

  const onCompute = () => {
    const days = Math.max(1, Math.min(60, Math.round(numOr(horizon, 7))));
    const forecast: CropDecisionForecastDay[] = Array.from({ length: days }, () => ({
      t_min_c: 12, t_max_c: 32, et0_mm: numOr(et0, 7), rain_mm: numOr(rain, 0),
    }));
    const payload: CropDecisionInput = {
      crop, stage, ndvi: optNum(ndvi), forecast, policy,
      soil: { texture, root_depth_m: numOr(rootDepth, 1.0), raw_fraction: 0.5 },
      management: { target_uptake_kg_ha: numOr(target, 0), initial_depletion_mm: numOr(initDepletion, 0) },
    };
    mut.mutate(payload);
  };

  const res = mut.data;

  return (
    <div className="space-y-5 max-w-4xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Sprout className="w-5 h-5 text-emerald-400" />
        <h2 className="text-xl font-bold text-slate-100">حالة المحصول الموحّدة</h2>
      </div>
      <p className="text-sm text-slate-400">
        قرار واحد من حالة محصول واحدة: المرحلة والماء والعنصر ⟵ ثمّ <span className="text-slate-300">ريّ + تسميد + مخاطر</span> مقترحة
        مع درجة ثقة. كلّ القيم <span className="text-amber-300">تقديريّة غير معايَرة</span>؛ الاقتصاد لم يُفعَّل بعد.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1">
          <span className="flex items-center gap-1 text-xs text-slate-400">
            <MapPin className="w-3.5 h-3.5" aria-hidden="true" /> اختر الحقل (يعبّئ المحصول وNDVI من سجلّه)
          </span>
          <select
            value={fieldId ?? ''}
            onChange={(e) => setFieldId(e.target.value || null)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
          >
            <option value="">بدون حقل — إدخال يدويّ</option>
            {fieldOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}{o.crop && o.crop !== '—' ? ` · ${o.crop}` : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">المحصول</span>
            <input value={crop} onChange={e => setCrop(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} /></label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">المرحلة</span>
            <select value={stage} onChange={e => setStage(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {STAGES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}</select></label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">السياسة</span>
            <select value={policy} onChange={e => setPolicy(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {POLICIES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}</select></label>
          <label className="flex flex-col gap-1"><span className="text-xs text-slate-400">نسيج التربة</span>
            <select value={texture} onChange={e => setTexture(e.target.value)} className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {TEXTURES.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}</select></label>
          {[
            { k: 'ndvi', label: 'NDVI (لـKc ديناميكيّ)', v: ndvi, set: setNdvi },
            { k: 'rootDepth', label: 'عمق الجذور (م)', v: rootDepth, set: setRootDepth },
            { k: 'horizon', label: 'أفق التنبّؤ (أيّام)', v: horizon, set: setHorizon },
            { k: 'et0', label: 'ET₀ يوميّ (مم)', v: et0, set: setEt0 },
            { k: 'rain', label: 'مطر متوقّع/يوم (مم)', v: rain, set: setRain },
            { k: 'target', label: 'هدف الامتصاص (كجم/ها)', v: target, set: setTarget },
            { k: 'init', label: 'استنزاف ابتدائيّ (مم)', v: initDepletion, set: setInitDepletion },
          ].map(f => (
            <label key={f.k} className="flex flex-col gap-1"><span className="text-xs text-slate-400">{f.label}</span>
              <input type="number" inputMode="decimal" step="any" value={f.v} onChange={e => f.set(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} /></label>
          ))}
        </div>
        <div className="flex justify-end">
          <button onClick={onCompute} disabled={mut.isPending}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#10b981' }}>
            <Sprout className="w-4 h-4" />
            {mut.isPending ? 'جارٍ تقييم الحالة…' : 'قيّم حالة المحصول'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر تقييم حالة المحصول" onRetry={onCompute} />}

      {res && (
        <div className="space-y-4">
          {/* Crop state strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'المرحلة', v: res.phenology.stage, sub: `تقدّم ${(res.phenology.progress * 100).toFixed(0)}٪` },
              { label: 'Kc الديناميكيّ', v: res.dynamic_kc.toFixed(2), sub: res.crop_known ? 'محصول مُعرّف' : 'عامّ' },
              { label: 'استنزاف الماء', v: `${res.water_state.depletion_mm.toFixed(0)} مم`, sub: `RAW ${res.water_state.raw_mm.toFixed(0)}` },
              { label: 'الثقة', v: `${(res.confidence * 100).toFixed(0)}٪`, sub: QUALITY_AR[res.data_quality] ?? res.data_quality },
            ].map((x, i) => (
              <div key={i} className="rounded-xl p-3 border text-center" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1">{x.label}</div>
                <div className="text-lg font-bold text-slate-100">{x.v}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{x.sub}</div>
              </div>
            ))}
          </div>

          {/* Two decisions: irrigation + fertilization */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="rounded-xl border p-4" style={{ background: '#0a1626', borderColor: '#0ea5e933' }}>
              <div className="flex items-center gap-1 text-sm font-semibold text-sky-200 mb-2"><Droplets className="w-4 h-4" /> الريّ المقترح</div>
              <div className="text-sm text-slate-100">{res.irrigation.action_ar}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                السياسة: {res.irrigation.policy} · الإجمالي {res.irrigation.total_mm.toFixed(0)} مم · {res.irrigation.n_events} دفعة · {res.irrigation.stress_days} يوم إجهاد
              </div>
            </div>
            <div className="rounded-xl border p-4" style={{ background: '#0a1612', borderColor: '#10b98133' }}>
              <div className="flex items-center gap-1 text-sm font-semibold text-emerald-200 mb-2"><FlaskConical className="w-4 h-4" /> التسميد المقترح</div>
              <div className="text-sm text-slate-100">{res.fertilization.action_ar}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                المُمتصّ حتى الآن {res.fertilization.uptake_to_date_kg_ha.toFixed(0)} كجم/ها · {res.fertilization.due ? 'مستحقّ' : 'غير مستحقّ'}
              </div>
            </div>
          </div>

          {/* Risk strip */}
          <div className="rounded-xl border p-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center gap-1 text-xs text-slate-400 mb-2"><Scale className="w-3.5 h-3.5" /> المخاطر</div>
            <div className="grid grid-cols-3 gap-2">
              {res.risks.map((r, i) => (
                <div key={i} className="text-center rounded-lg py-2" style={{ background: '#0f1117' }}>
                  <div className="text-[11px] text-slate-500 mb-0.5">{r.label_ar}</div>
                  <div className={`text-sm font-semibold ${riskColor(r.level_ar)}`}>{r.level_ar}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Economic state reserved */}
          <div className="rounded-xl border p-3 flex items-center gap-2" style={{ background: '#161616', borderColor: '#33415533' }}>
            <Coins className="w-4 h-4 text-slate-500" />
            <div className="text-[12px] text-slate-400">
              الحالة الاقتصاديّة: <span className="text-slate-300">لم تُفعَّل بعد</span> — تحتاج: {(res.economic_state.required_inputs ?? []).join('، ')}
            </div>
          </div>

          {/* Uncalibrated banner */}
          <div className="rounded-xl border p-4 flex items-start gap-3" style={{ background: '#1a1400', borderColor: '#f59e0b33' }}>
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="text-sm font-semibold text-amber-200">🟡 نموذج غير مُعاير (calibrated={String(res.calibrated)})</div>
              {res.assumptions_ar.map((n, i) => <div key={i} className="text-[11px] text-amber-300/80">• {n}</div>)}
              {res.warnings_ar.map((n, i) => <div key={`w${i}`} className="text-[11px] text-slate-400">• {n}</div>)}
            </div>
          </div>

          {/* Unified flags */}
          {res.stress_flags.length > 0 && (
            <div className="rounded-xl border p-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="flex items-center gap-1 text-xs text-slate-400 mb-2"><Info className="w-3.5 h-3.5" /> أعلام الحالة</div>
              <div className="flex flex-wrap gap-2">
                {res.stress_flags.map((f, i) => (
                  <span key={i} className="text-[11px] px-2 py-1 rounded-lg text-orange-300" style={{ background: '#2a0d0d' }}>{f.label_ar}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
