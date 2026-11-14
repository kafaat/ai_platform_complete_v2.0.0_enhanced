// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationWaterPage (ربط حيّ بـ POST /api/v1/irrigation/water-analysis)
// يُبرِز وحدة تحليل ماء الريّ الخلفيّة (SAR/RSC + تصنيف FAO-29/USDA-197/USSL).
// صدق: المؤشّر الذي يحتاج قيمة غائبة يُعلَن «غير محسوب» (من الخادم) لا يُفبرَك.
// حسابٌ لا يُخزَّن ولا يُربط بحقل: لا اختيار حقل هنا ولا field_id في الطلب (الخادم يرفضه).
// النتيجة المخبريّة المرتبطة بحقل تُسجَّل في «عيّنات المختبر» (/lab/samples ثمّ water-results).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Droplets, FlaskConical, AlertTriangle, CheckCircle } from 'lucide-react';
import { useWaterAnalysis } from '../hooks/useApi';
import type { WaterSampleInput, WaterSourceKind } from '../services/api';
import { WATER_SOURCE_OPTIONS } from '../lib/waterFieldOps';
import { ErrorState } from '../components/StateViews';

const IONS: { key: keyof WaterSampleInput; label: string; hint: string }[] = [
  { key: 'na',     label: 'الصوديوم Na',        hint: 'meq/L' },
  { key: 'ca',     label: 'الكالسيوم Ca',        hint: 'meq/L' },
  { key: 'mg',     label: 'المغنيسيوم Mg',       hint: 'meq/L' },
  { key: 'hco3',   label: 'البيكربونات HCO₃',    hint: 'meq/L' },
  { key: 'co3',    label: 'الكربونات CO₃',       hint: 'meq/L' },
  { key: 'cl',     label: 'الكلوريد Cl',         hint: 'meq/L' },
  { key: 'ec_dsm', label: 'التوصيليّة EC',       hint: 'dS/m' },
  { key: 'ph',     label: 'الأس الهيدروجينيّ pH', hint: '' },
];

const isWaterSource = (v: string): v is WaterSourceKind =>
  WATER_SOURCE_OPTIONS.some(o => o.key === v);

const NOT_COMPUTABLE_AR: Record<string, string> = {
  numeric_overflow: 'القيم تتجاوز نطاق الحساب العدديّ — راجع وحدات القياس',
  calcium_plus_magnesium_zero: 'Ca + Mg = صفر',
};

export default function IrrigationWaterPage() {
  const [vals, setVals] = useState<Record<string, string>>({});
  // نوع مصدر الماء (بئر/قناة/مختلط) — لا اسم حقل.
  const [source, setSource] = useState<WaterSourceKind>('well');
  const [submittedFormKey, setSubmittedFormKey] = useState<string | null>(null);
  const mut = useWaterAnalysis();
  // Never present the prior analysis as if it belonged to newly edited readings/source.
  const currentFormKey = JSON.stringify({ source, vals });
  const invalidInputs = IONS.filter(({ key }) => {
    const raw = vals[key];
    if (raw == null || raw.trim() === '') return false;
    const value = Number(raw);
    return !Number.isFinite(value) || value < 0 || (key === 'ph' && value > 14);
  });

  const num = (k: string): number | null => {
    const v = vals[k];
    if (v == null || v.trim() === '') return null;
    const n = Number(v);
    return isNaN(n) ? null : n;
  };

  const onAnalyze = () => {
    const payload: WaterSampleInput = {
      sample_id: `water-calc-${Date.now()}`,
      source,
      na: num('na'), ca: num('ca'), mg: num('mg'), hco3: num('hco3'),
      co3: num('co3'), cl: num('cl'), ec_dsm: num('ec_dsm'), ph: num('ph'),
    };
    if (invalidInputs.length > 0) return;
    setSubmittedFormKey(currentFormKey);
    mut.mutate(payload);
  };

  const res = submittedFormKey === currentFormKey && !mut.isError ? mut.data : undefined;
  const positiveVerdict = res?.verdict === 'suitable' && res.data_complete === true;
  // FAO-29 slight-to-moderate tier: usable with management, never a green check.
  const restrictedVerdict = res?.verdict === 'suitable_with_restrictions' && res.data_complete === true;
  const restrictionReasons = restrictedVerdict ? res?.restriction_flags_ar ?? [] : [];
  // Legacy servers lack verdict. Fail closed on their positive-looking text as well.
  const verdictLabel = !res ? '' : positiveVerdict || restrictedVerdict
    || res.verdict === 'needs_treatment' || res.hazard_flags_ar.length > 0
    ? res?.suitable_ar ?? ''
    : 'بيانات غير كافية للحكم العامّ';
  const tone = positiveVerdict
    ? { bg: '#04140a', border: '#16a34a33' }
    : restrictedVerdict
      ? { bg: '#1a1400', border: '#f59e0b55' }
      : { bg: '#1a0800', border: '#f9731633' };

  return (
    <div className="space-y-5 max-w-3xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Droplets className="w-5 h-5 text-sky-400" />
        <h2 className="text-xl font-bold text-slate-100">تحليل ماء الريّ</h2>
      </div>
      <p className="text-sm text-slate-400">
        أدخِل نتائج تحليل العيّنة المخبريّ (الأيونات بـmeq/L). يُحسب SAR وRSC ويُصنَّف
        خطر الملوحة/الصوديوم/القلويّة. القيم الغائبة تُعلَن «غير محسوبة» (لا تقدير مفبرَك).
      </p>

      <p role="note" className="text-xs text-amber-300">
        حساب فوريّ فقط: لا تُحفظ النتيجة ولا تُربط بأيّ حقل. لتسجيل تحليل مخبريّ مرتبط بحقل
        استخدم «عيّنات المختبر».
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <label className="flex flex-col gap-1 mb-3 max-w-xs">
          <span className="text-xs text-slate-400">مصدر الماء</span>
          <select value={source}
            onChange={e => { if (isWaterSource(e.target.value)) setSource(e.target.value); }}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            {WATER_SOURCE_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {IONS.map(f => (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{f.label}{f.hint && <span className="text-slate-600"> ({f.hint})</span>}</span>
              <input type="number" inputMode="decimal" step="any" min={0} max={f.key === 'ph' ? 14 : undefined}
                value={vals[f.key] ?? ''}
                onChange={e => setVals(v => ({ ...v, [f.key]: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          ))}
        </div>
        {invalidInputs.length > 0 && (
          <p role="alert" className="text-xs text-orange-300 mt-3">
            قياسات غير صالحة: {invalidInputs.map(({ label }) => label).join('، ')}. أدخل قيماً غير سالبة وpH بين 0 و14.
          </p>
        )}
        <div className="flex justify-end mt-4">
          <button onClick={onAnalyze} disabled={mut.isPending || invalidInputs.length > 0}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <FlaskConical className="w-4 h-4" />
            {mut.isPending ? 'جارٍ التحليل…' : 'تحليل العيّنة'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر تحليل العيّنة" onRetry={onAnalyze} />}

      {/* Results */}
      {res && (
        <div className="space-y-4">
          <p className="text-[11px] text-slate-500">نتيجة حساب غير محفوظة وغير مرتبطة بحقل.</p>
          {/* Indices */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'SAR (الصوديوم)', v: res.indices.sar },
              { label: 'RSC (meq/L)', v: res.indices.rsc_meq_l },
              { label: 'EC (dS/m)', v: res.indices.ec_dsm },
              { label: 'pH', v: res.indices.ph },
            ].map((x, i) => (
              <div key={i} className="rounded-xl p-3 border text-center" style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="text-[11px] text-slate-400 mb-1">{x.label}</div>
                <div className="text-lg font-bold text-slate-100">{x.v ?? '—'}</div>
              </div>
            ))}
          </div>

          {/* Classifications */}
          <div className="rounded-xl border p-4 space-y-2" style={{ background: '#1e293b', borderColor: '#334155' }}>
            {[
              { t: 'الملوحة (FAO-29)', c: res.classification.salinity },
              { t: 'القلويّة RSC (USDA-197)', c: res.classification.alkalinity_rsc },
              { t: 'الصوديوم SAR (USSL)', c: res.classification.sodicity_sar },
            ].map((row, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 border-b last:border-0" style={{ borderColor: '#334155' }}>
                <span className="text-sm text-slate-300">{row.t}</span>
                <span className="text-xs text-slate-400">
                  {row.c.class ?? '—'}
                  {(row.c.restriction_ar || row.c.hazard_ar || row.c.note_ar)
                    ? ` · ${row.c.restriction_ar || row.c.hazard_ar || row.c.note_ar}` : ''}
                </span>
              </div>
            ))}
          </div>

          {/* Verdict */}
          <div data-testid="water-verdict" data-verdict={res.verdict ?? 'legacy'}
            className="rounded-xl border p-4 flex items-start gap-3"
            style={{ background: tone.bg, borderColor: tone.border }}>
            {positiveVerdict
              ? <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              : <AlertTriangle className={`w-5 h-5 shrink-0 mt-0.5 ${restrictedVerdict ? 'text-amber-400' : 'text-orange-400'}`} />}
            <div>
              <div className="text-sm font-semibold text-slate-100">{verdictLabel}</div>
              {restrictionReasons.length > 0 && (
                <ul aria-label="قيود الاستعمال (FAO-29)" className="text-xs text-amber-300 mt-1 list-disc ps-4">
                  {restrictionReasons.map(r => <li key={r}>{r}</li>)}
                </ul>
              )}
              {res.hazard_flags_ar.length > 0 && (
                <div className="text-xs text-orange-300 mt-1">{res.hazard_flags_ar.join(' · ')}</div>
              )}
              {(res.indices_not_computable ?? []).length > 0 && (
                <div className="text-[11px] text-orange-300 mt-1">
                  مؤشّرات تعذّر حسابها (ليست بيانات ناقصة):{' '}
                  {(res.indices_not_computable ?? [])
                    .map(x => `${x.index === 'sar' ? 'SAR' : 'RSC'}: ${NOT_COMPUTABLE_AR[x.reason] ?? x.reason}`)
                    .join('، ')}
                </div>
              )}
              {(res.advisories_ar ?? []).map(a => (
                <div key={a} className="text-[11px] text-slate-400 mt-1">{a}</div>
              ))}
              {!res.data_complete && res.missing_inputs.length > 0 && (
                <div className="text-[11px] text-slate-500 mt-1">قيم ناقصة (مؤشّرات غير محسوبة): {res.missing_inputs.join('، ')}</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
