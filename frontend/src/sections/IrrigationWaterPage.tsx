// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationWaterPage (ربط حيّ بـ POST /api/v1/irrigation/water-analysis)
// يُبرِز وحدة تحليل ماء الريّ الخلفيّة (SAR/RSC + تصنيف FAO-29/USDA-197/USSL).
// صدق: المؤشّر الذي يحتاج قيمة غائبة يُعلَن «غير محسوب» (من الخادم) لا يُفبرَك.
// الحساب لا يُخزَّن ولا يُربط بحقل: لا field_id في طلبه (الخادم يرفضه).
// «حفظ كنتيجة مخبر لحقل» إجراءٌ منفصل صريح (قرار المالك 2026-11-14): يختار المستخدم حقلاً
// ويُرسَل القياس نفسه عبر مسار المختبر المُخزَّن القائم — عيّنة ماء للحقل (POST /api/v1/lab/samples)
// ثمّ POST /api/v1/lab/water-results — حيث يفرض الخادم ملكيّة المستأجِر للحقل والعيّنة.
// لا مسار جديد (ميزانية المسارات 629/629).
// ═══════════════════════════════════════════════════════════════
import { useMemo, useRef, useState } from 'react';
import { Droplets, FlaskConical, AlertTriangle, CheckCircle, Save } from 'lucide-react';
import { useCreateLabSample, useLabSamples, useWaterAnalysis } from '../hooks/useApi';
import { useSubmitWaterLabResult } from '../hooks/useWaterFieldOps';
import { useFieldOptions } from '../hooks/useFieldOptions';
import { apiErrorMessage, type LabSampleRecord, type WaterSampleInput, type WaterSourceKind } from '../services/api';
import { WATER_SOURCE_OPTIONS, type WaterLabAnalysis, type WaterSamplePayload } from '../lib/waterFieldOps';
import { fieldRepresentativePoint } from '../lib/geo';
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
  // نوع مصدر الماء (أنواع v168: بئر/خزّان/قناة/نهر/بلديّة/أمطار/أخرى) — لا اسم حقل.
  const [source, setSource] = useState<WaterSourceKind>('well');
  const [submittedFormKey, setSubmittedFormKey] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
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
        حساب فوريّ فقط: لا تُحفظ النتيجة ولا تُربط بأيّ حقل. لتسجيل القياس نفسه نتيجةَ مخبرٍ
        مرتبطة بحقل استخدم «حفظ كنتيجة مخبر لحقل».
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
        <div className="flex justify-end gap-2 mt-4">
          <button type="button" onClick={() => setSaveOpen(o => !o)} aria-expanded={saveOpen}
            disabled={invalidInputs.length > 0}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-slate-100 disabled:opacity-60"
            style={{ background: '#334155' }}>
            <Save className="w-4 h-4" />
            حفظ كنتيجة مخبر لحقل
          </button>
          <button onClick={onAnalyze} disabled={mut.isPending || invalidInputs.length > 0}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#0ea5e9' }}>
            <FlaskConical className="w-4 h-4" />
            {mut.isPending ? 'جارٍ التحليل…' : 'تحليل العيّنة'}
          </button>
        </div>
      </div>

      {saveOpen && invalidInputs.length === 0 && (
        <SaveAsLabResult
          measurement={{
            source,
            na: num('na'), ca: num('ca'), mg: num('mg'), hco3: num('hco3'),
            co3: num('co3'), cl: num('cl'), ec_dsm: num('ec_dsm'), ph: num('ph'),
          }}
        />
      )}

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

// ── حفظ كنتيجة مخبر لحقل ─────────────────────────────────────────────────────
// يمرّ بمسار المختبر القائم كما هو: عيّنة ماء تُنشأ لحقل المستخدم المختار (أو عيّنة ماء قائمة
// للحقل تنتظر نتيجتها الأولى: sampled/in_lab)، ثمّ نتيجة الماء على sample_id. الحقل لا يُرسَل
// إلى water-results؛ الربط بالحقل هو العيّنة، والخادم يرفض حقلاً أو عيّنةً خارج المستأجِر.
// النتيجة تُخزَّن «بانتظار المراجعة» ولا تصير مدخل قرار قبل اعتمادها.

type Measurement = Omit<WaterSamplePayload, 'sample_id' | 'sampled_at'> & { source: WaterSourceKind };

const NEW_SAMPLE = '__new__';
const AWAITING_FIRST_RESULT = new Set(['sampled', 'in_lab']);
const VERDICT_AR: Record<string, string> = {
  suitable: 'صالح للريّ',
  suitable_with_restrictions: 'صالح مع قيود',
  needs_treatment: 'يحتاج معالجة',
  insufficient_data: 'بيانات غير كافية',
};

function SaveAsLabResult({ measurement }: { measurement: Measurement }) {
  const fieldsQ = useFieldOptions();
  const [fieldId, setFieldId] = useState('');
  const field = fieldsQ.options.find(f => f.id === fieldId);
  const samplesQ = useLabSamples(fieldId || undefined);
  const openSamples = useMemo<LabSampleRecord[]>(
    () => (fieldId ? samplesQ.data ?? [] : [])
      .filter(s => s.field_id === fieldId && s.kind === 'water' && AWAITING_FIRST_RESULT.has(s.status)),
    [fieldId, samplesQ.data],
  );
  const [sampleChoice, setSampleChoice] = useState(NEW_SAMPLE);
  const [coords, setCoords] = useState({ field: '', lat: '', lon: '' });
  const [sampledOn, setSampledOn] = useState('');
  const [saved, setSaved] = useState<WaterLabAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const createSample = useCreateLabSample();
  const submitWater = useSubmitWaterLabResult();
  // A sample created by an attempt whose result failed is reused by the retry (one sample,
  // not one per click); the create itself carries one Idempotency-Key per field and point.
  const created = useRef<{ scope: string; key: string; sampleId?: string; stored?: boolean } | null>(null);

  const rep = field ? fieldRepresentativePoint(field) : null;
  const lat = coords.field === fieldId ? coords.lat : rep ? String(rep[0]) : '';
  const lon = coords.field === fieldId ? coords.lon : rep ? String(rep[1]) : '';
  const latN = Number(lat);
  const lonN = Number(lon);
  const coordsOk = lat.trim() !== '' && lon.trim() !== '' && Number.isFinite(latN) && Number.isFinite(lonN)
    && Math.abs(latN) <= 90 && Math.abs(lonN) <= 180;
  const usingNew = sampleChoice === NEW_SAMPLE || !openSamples.some(s => s.sample_id === sampleChoice);
  const busy = createSample.isPending || submitWater.isPending;
  const canSave = !!fieldId && !busy && (!usingNew || coordsOk);

  const onSave = async () => {
    if (!canSave) return;
    setError(null);
    setSaved(null);
    const scope = JSON.stringify([fieldId, latN, lonN, measurement.source, sampledOn]);
    const attempt = usingNew
      ? (created.current?.scope === scope && !created.current.stored
        ? created.current
        : { scope, key: requestKey() })
      : null;
    if (attempt) created.current = attempt;
    try {
      let sampleId = attempt ? attempt.sampleId : sampleChoice;
      if (attempt && !sampleId) {
        const row = await createSample.mutateAsync({
          idempotency_key: attempt.key,
          field_id: fieldId,
          kind: 'water',
          latitude: latN,
          longitude: lonN,
          source: measurement.source,
          sampled_on: sampledOn || null,
          status: 'collected',
        });
        sampleId = row.sample_id;
        attempt.sampleId = sampleId;
      }
      const result = await submitWater.mutateAsync({
        ...measurement,
        sample_id: sampleId as string,
        sampled_at: sampledOn ? `${sampledOn}T00:00:00+00:00` : null,
      });
      setSaved(result);
      // The next save is a new measurement: it gets a sample of its own.
      if (attempt) attempt.stored = true;
    } catch (e) {
      setError(apiErrorMessage(e, 'تعذّر حفظ نتيجة المخبر'));
    }
  };

  return (
    <section aria-label="حفظ كنتيجة مخبر لحقل" className="rounded-xl border p-4 space-y-3"
      style={{ background: '#1e293b', borderColor: '#334155' }}>
      <p className="text-xs text-slate-400">
        يُسجَّل القياس المُدخَل أعلاه نتيجةَ مخبرٍ لعيّنة ماء من الحقل المختار (مسار عيّنات المختبر)،
        بانتظار مراجعة مختصّ قبل أن يُعتمَد مدخلاً للقرار.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الحقل</span>
          <select value={fieldId}
            onChange={e => { setFieldId(e.target.value); setSampleChoice(NEW_SAMPLE); setSaved(null); setError(null); }}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            <option value="">اختر حقلاً…</option>
            {fieldsQ.options.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">عيّنة الماء</span>
          <select value={usingNew ? NEW_SAMPLE : sampleChoice} disabled={!fieldId}
            onChange={e => setSampleChoice(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
            <option value={NEW_SAMPLE}>عيّنة جديدة لهذا الحقل</option>
            {openSamples.map(s => <option key={s.sample_id} value={s.sample_id}>{s.sample_id}</option>)}
          </select>
        </label>
        {usingNew && fieldId && (
          <>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">خط العرض (موقع العيّنة)</span>
              <input type="number" step="any" min={-90} max={90} value={lat}
                onChange={e => setCoords({ field: fieldId, lat: e.target.value, lon })}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">خط الطول (موقع العيّنة)</span>
              <input type="number" step="any" min={-180} max={180} value={lon}
                onChange={e => setCoords({ field: fieldId, lat, lon: e.target.value })}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          </>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">تاريخ أخذ العيّنة (اختياريّ)</span>
          <input type="date" value={sampledOn} onChange={e => setSampledOn(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </label>
      </div>
      {usingNew && fieldId && !coordsOk && (
        <p className="text-xs text-orange-300">أدخل موقع العيّنة (خطّي العرض والطول) — لا موقع معروف لهذا الحقل.</p>
      )}
      <div className="flex justify-end">
        <button type="button" onClick={onSave} disabled={!canSave}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
          style={{ background: '#16a34a' }}>
          <Save className="w-4 h-4" />
          {busy ? 'جارٍ الحفظ…' : 'حفظ النتيجة للحقل'}
        </button>
      </div>
      {error && <p role="alert" className="text-xs text-orange-300">{error}</p>}
      {saved && (
        <p role="status" className="text-xs text-emerald-300">
          حُفظت نتيجة المخبر للحقل {field?.name ?? fieldId} (العيّنة {saved.sample_id}
          {saved.result_id ? ` · النتيجة ${saved.result_id}` : ''}) — الحكم:{' '}
          {saved.verdict ? VERDICT_AR[saved.verdict] ?? saved.verdict : '—'}
          {saved.quality_status === 'unreviewed' ? ' · بانتظار المراجعة' : ''}
          {/* R5 source_evidence: the type is the user's declaration, never a verified source. */}
          {' · '}نوع المصدر «{sourceLabel(saved.source ?? measurement.source)}» معلَن من المُدخِل وغير مُتحقَّق منه
        </p>
      )}
    </section>
  );
}

function sourceLabel(kind: string): string {
  return WATER_SOURCE_OPTIONS.find(o => o.key === kind)?.label_ar ?? kind;
}

function requestKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}
