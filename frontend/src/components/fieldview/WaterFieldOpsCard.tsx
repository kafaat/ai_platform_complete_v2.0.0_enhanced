import { useMemo, useState } from 'react';
import { CloudLightning, Droplets, FlaskConical, Leaf, MapPin, NotebookPen, Waves, Wheat } from 'lucide-react';
import {
  useGeoLocateField,
  useIntegratedWaterAdvice,
  useNutrient4rPlan,
  useRecordOutcome,
  useSubmitWaterLabResult,
  useUpstreamFlood,
  useWaterBalance,
  useWaterStressRisk,
  useWeatherAlerts,
  useWeatherLayers,
  useWheatWaterCalendar,
} from '../../hooks/useWaterFieldOps';
import {
  STAGE_OPTIONS_BY_CROP,
  WATER_CROP_OPTIONS,
  WATER_SOURCE_OPTIONS,
  WB_STAGE_OPTIONS,
  alertRows,
  alertSeverityColor,
  build4rInput,
  buildIntegratedInput,
  buildOutcomeRecordInput,
  buildStressInput,
  buildWaterBalanceInput,
  buildWaterSamplePayload,
  classificationRows,
  floodParagraphs,
  fmtNum,
  geoFacts,
  layerCaption,
  layerRows,
  listOrText,
  nutrientNameAr,
  nutrientStatusBadge,
  outcomeMetricRows,
  outcomeSuccessLabel,
  parseMeasure,
  planRows,
  sensitivityColor,
  stressLevelColor,
  unsupportedMessage,
  waterBalanceFacts,
  waterIndicesFacts,
  writeErrorMessage,
  type OutcomeRecordFormText,
  type Soil4RFormText,
  type WaterBalanceFormText,
  type WaterSampleFormText,
} from '../../lib/waterFieldOps';
import { T } from '../ds';

interface Props {
  /** معرّف الحقل النشط — يُربَط به تسجيل النتيجة (outcome/record) إن وُجد. */
  fieldId?: string | null;
  /** تسمية محصول الحقل النشط — سياق عرض فقط (المستخدم يختار مفتاح المحصول للخادم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

type SectionKey =
  | 'advice' | 'wheatcal' | 'balance' | 'flood' | 'lab' | 'weather' | 'nutrients' | 'outcome' | 'geo';

const SECTIONS: { key: SectionKey; label_ar: string }[] = [
  { key: 'advice', label_ar: 'نصيحة وإجهاد مائيّ' },
  { key: 'wheatcal', label_ar: 'تقويم القمح' },
  { key: 'balance', label_ar: 'ميزان مائيّ' },
  { key: 'flood', label_ar: 'سيول أعالي الوادي' },
  { key: 'lab', label_ar: 'تحليل ماء الريّ' },
  { key: 'weather', label_ar: 'تنبيهات وطبقات الطقس' },
  { key: 'nutrients', label_ar: 'خطّة 4R' },
  { key: 'outcome', label_ar: 'تسجيل نتيجة' },
  { key: 'geo', label_ar: 'موقع الحقل' },
];

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const boxStyle = { borderColor: T.line, background: 'rgba(15,23,42,.35)' } as const;

/** خطأ شبكة/خادم ⇒ نصّ إعادة محاولة صادق (لا إخفاء ولا تلفيق). */
function RetryNote({ q, label }: { q: { refetch: () => void }; label: string }) {
  return (
    <div className="text-[11px]" style={{ color: '#fca5a5' }}>
      تعذّر جلب {label} من الخادم.
      <button type="button" onClick={() => q.refetch()} className="ms-1 underline" style={{ color: '#fca5a5' }}>
        أعد المحاولة
      </button>
    </div>
  );
}

/** 404 من الخادم ⇒ إعلان «غير مُفعَّل» صادق (الميزة غير منشورة على هذا الخادم). */
function DisabledNote() {
  return <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على هذا الخادم.</div>;
}

function FactPills({ facts }: { facts: { label: string; value: string }[] }) {
  if (facts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {facts.map((f) => (
        <span key={f.label} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
          <span style={{ color: T.faint }}>{f.label}:</span> {f.value}
        </span>
      ))}
    </div>
  );
}

function NumField(props: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; width?: string; step?: string;
}) {
  return (
    <>
      <label htmlFor={props.id} className="font-bold" style={{ color: T.ink }}>{props.label}</label>
      <input
        id={props.id}
        type="number"
        step={props.step ?? 'any'}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder ?? 'من قياس'}
        className={`${props.width ?? 'w-20'} px-2 py-0.5 rounded-lg text-[11px]`}
        style={inputStyle}
      />
    </>
  );
}

/** «عمليّات الماء والحقل»: نصيحة مائيّة متكاملة + خطر إجهاد + تقويم القمح (التوافقيّ
 *  بتحذير التشبّع) · ميزان FAO-56 (وقرار الملوحة) · مورد السيول الواردة · تحليل ماء
 *  الريّ المخبريّ (SAR/RSC/EC) · تنبيهات الطقس المشتقّة وmanifest الطبقات · خطّة 4R
 *  للتربة الكلسيّة · إدامة نتيجة القرار (outcome/record — كتابة صادقة) · تحديد
 *  المحافظة/الإقليم من GPS. الأحكام والنصوص كلّها من الخادم — الواجهة تعرض ولا تحكم؛
 *  404 ⇒ «غير مُفعَّل» صادقة، وأخطاء الكتابة تُعرَض بنصّ الخادم (لا «نجاح» مُختلق). */
export default function WaterFieldOpsCard({ fieldId, cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<SectionKey>('advice');

  // — نصيحة/إجهاد: محصول+مرحلة (مفاتيح عقد الخادم) + نضوب ٪ + صافي مم اختياريّ —
  const [crop, setCrop] = useState('wheat');
  const [stageKey, setStageKey] = useState('flowering');
  const [depletionInput, setDepletionInput] = useState('');
  const [netMmInput, setNetMmInput] = useState('');
  const stageOptions = STAGE_OPTIONS_BY_CROP[crop] ?? [];
  const integratedReq = useMemo(
    () => buildIntegratedInput(crop, stageKey, depletionInput, netMmInput),
    [crop, stageKey, depletionInput, netMmInput],
  );
  const stressReq = useMemo(
    // مع صافي الريّ نستدعي integrated-advice (تشمل خطر الإجهاد) — لا استدعاء مزدوجاً.
    () => (integratedReq ? null : buildStressInput(crop, stageKey, depletionInput)),
    [integratedReq, crop, stageKey, depletionInput],
  );
  const stressQ = useWaterStressRisk(enabled && open === 'advice' ? stressReq : null);
  const integratedQ = useIntegratedWaterAdvice(enabled && open === 'advice' ? integratedReq : null);
  // العرض الموحّد: أيّهما نشط (الحقول مشتركة — integrated تضيف النصيحة المدموجة).
  const adviceQ = integratedReq ? integratedQ : stressQ;

  // — تقويم القمح (توافقيّ + تحذير التشبّع) — يُجلَب عند فتح قسمه فقط —
  const wheatCalQ = useWheatWaterCalendar(enabled && open === 'wheatcal');

  // — ميزان الماء: حرارتا اليوم (قياس) + اختياريّات تُرسَل فقط عند إدخالها —
  const [wb, setWb] = useState<WaterBalanceFormText>({
    crop: '', stage: 'mid', tMin: '', tMax: '', rainMm: '', latitude: '', elevation: '',
    dayOfYear: '', soilEce: '', waterEcw: '', analysisAgeDays: '', analysisConfidencePct: '',
  });
  const setWbField = (k: keyof WaterBalanceFormText) => (v: string) => setWb((p) => ({ ...p, [k]: v }));
  const wbReq = useMemo(() => buildWaterBalanceInput(wb), [wb]);
  const wbQ = useWaterBalance(enabled && open === 'balance' ? wbReq : null);
  const wbFacts = useMemo(() => waterBalanceFacts(wbQ.data), [wbQ.data]);

  // — السيول الواردة: المطر المحلّيّ قياس من المستخدم (لا تخمين) —
  const [localRainInput, setLocalRainInput] = useState('');
  const localRainMm = useMemo(() => parseMeasure(localRainInput), [localRainInput]);
  const floodQ = useUpstreamFlood(localRainMm, enabled && open === 'flood');
  const floodParas = useMemo(() => floodParagraphs(floodQ.data), [floodQ.data]);

  // — تحليل ماء الريّ: كتابة (الخادم يخزّن) ⇒ إرسال صريح بزرّ، لا تلقائيّاً —
  const [sample, setSample] = useState<WaterSampleFormText>({
    sampleId: '', source: 'well', na: '', ca: '', mg: '', hco3: '', co3: '', cl: '',
    ecDsm: '', ph: '', sampledAt: '',
  });
  const setSampleField = (k: keyof WaterSampleFormText) => (v: string) => setSample((p) => ({ ...p, [k]: v }));
  const samplePayload = useMemo(() => buildWaterSamplePayload(sample), [sample]);
  const labM = useSubmitWaterLabResult();
  const labIdx = useMemo(() => waterIndicesFacts(labM.data), [labM.data]);
  const labClasses = useMemo(() => classificationRows(labM.data), [labM.data]);

  // — إحداثيّات مشتركة (الطقس + الموقع): نفس موقع الحقل، تُدخَل مرّة واحدة —
  const [latInput, setLatInput] = useState('');
  const [lonInput, setLonInput] = useState('');
  const [elevInput, setElevInput] = useState('');
  const lat = useMemo(() => parseMeasure(latInput), [latInput]);
  const lon = useMemo(() => parseMeasure(lonInput), [lonInput]);
  const elevM = useMemo(() => parseMeasure(elevInput), [elevInput]);
  const alertsQ = useWeatherAlerts(lat, lon, enabled && open === 'weather');
  const layersQ = useWeatherLayers(enabled && open === 'weather');
  const alerts = useMemo(() => alertRows(alertsQ.data), [alertsQ.data]);
  const layers = useMemo(() => layerRows(layersQ.data), [layersQ.data]);
  const geoQ = useGeoLocateField(lat, lon, elevM, enabled && open === 'geo');
  const gFacts = useMemo(() => geoFacts(geoQ.data), [geoQ.data]);

  // — خطّة 4R: قياس مخبريّ واحد على الأقلّ (الخادم يحجب ما يحتاج تحليلاً) —
  const [soil4r, setSoil4r] = useState<Soil4RFormText>({
    caco3Pct: '', ph: '', pPpm: '', fePpm: '', znPpm: '', omPct: '',
  });
  const set4rField = (k: keyof Soil4RFormText) => (v: string) => setSoil4r((p) => ({ ...p, [k]: v }));
  const soil4rReq = useMemo(() => build4rInput(soil4r), [soil4r]);
  const planQ = useNutrient4rPlan(enabled && open === 'nutrients' ? soil4rReq : null);
  const plan = useMemo(() => planRows(planQ.data), [planQ.data]);

  // — تسجيل نتيجة (outcome/record): كتابة تُدِيم في Postgres ⇒ إرسال صريح بزرّ —
  const [outcome, setOutcome] = useState<OutcomeRecordFormText>({
    decisionId: '', recommendedIrrigationMm: '', predictedStressDays: '', expectedYieldTHa: '',
    seasonBudgetMm: '', actualIrrigationMm: '', observedStressDays: '', actualYieldTHa: '',
    actualWaterUsedMm: '', idempotencyKey: '',
  });
  const setOutcomeField = (k: keyof OutcomeRecordFormText) => (v: string) =>
    setOutcome((p) => ({ ...p, [k]: v }));
  const outcomeReq = useMemo(
    () => buildOutcomeRecordInput(outcome, fieldId ?? null),
    [outcome, fieldId],
  );
  const outcomeM = useRecordOutcome();
  const successBadge = outcomeSuccessLabel(outcomeM.data?.success);
  const recordedMetrics = useMemo(() => outcomeMetricRows(outcomeM.data), [outcomeM.data]);

  if (!enabled) return null;

  const coordInputs = (prefix: string, withElevation: boolean) => (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
      <MapPin className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
      <NumField id={`${prefix}-lat`} label="خطّ العرض:" value={latInput} onChange={setLatInput} placeholder="15.35" />
      <NumField id={`${prefix}-lon`} label="خطّ الطول:" value={lonInput} onChange={setLonInput} placeholder="44.20" />
      {withElevation && (
        <NumField id={`${prefix}-elev`} label="الارتفاع (م، اختياريّ):" value={elevInput} onChange={setElevInput} placeholder="من GPS" />
      )}
    </div>
  );

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="water-field-ops" aria-label="عمليّات الماء والحقل">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-sky-300" aria-hidden="true" /> عمليّات الماء والحقل
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      {/* أقسام قابلة للطيّ — استعلام كلّ قسم لا يُطلق إلّا عند فتحه (لا استدعاء ميّت). */}
      <div className="flex flex-wrap items-center gap-1.5 mb-2">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setOpen(s.key)}
            className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{
              border: `1px solid ${open === s.key ? '#0c4a6e' : T.line}`,
              color: open === s.key ? '#7dd3fc' : T.muted,
              background: open === s.key ? 'rgba(12,74,110,.25)' : 'rgba(15,23,42,.45)',
            }}
          >
            {s.label_ar}
          </button>
        ))}
      </div>

      {/* ── نصيحة وإجهاد: stress-risk دائماً، وintegrated-advice عند إدخال صافي الريّ ── */}
      {open === 'advice' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <Leaf className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <label htmlFor="wfo-crop" className="font-bold" style={{ color: T.ink }}>المحصول:</label>
            <select
              id="wfo-crop"
              value={crop}
              onChange={(e) => {
                const c = e.target.value;
                setCrop(c);
                // مراحل كلّ محصول تختلف (عقد الخادم) — نعيد الاختيار لأولى مراحله.
                setStageKey(STAGE_OPTIONS_BY_CROP[c]?.[0]?.key ?? '');
              }}
              className="px-2 py-0.5 rounded-lg text-[11px]"
              style={inputStyle}
            >
              {WATER_CROP_OPTIONS.map((c) => <option key={c.key} value={c.key}>{c.label_ar}</option>)}
            </select>
            <label htmlFor="wfo-stage" className="font-bold" style={{ color: T.ink }}>المرحلة:</label>
            <select id="wfo-stage" value={stageKey} onChange={(e) => setStageKey(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {stageOptions.map((s) => <option key={s.key} value={s.key}>{s.label_ar}</option>)}
            </select>
            <NumField id="wfo-depl" label="نضوب التربة (٪):" value={depletionInput} onChange={setDepletionInput} width="w-16" />
            <NumField id="wfo-net" label="صافي الريّ (مم، اختياريّ):" value={netMmInput} onChange={setNetMmInput} placeholder="من الميزان" />
          </div>

          {!integratedReq && !stressReq ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل نضوب التربة (٪ من قياس/تقدير ميدانيّ) ليقيّم الخادم الخطر — وأضف صافي الريّ (مم) لنصيحة متكاملة.</div>
          ) : adviceQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم الإجهاد المائيّ…</div>
          ) : adviceQ.isError ? (
            <RetryNote q={adviceQ} label="تقييم الإجهاد المائيّ" />
          ) : adviceQ.data?.disabled ? (
            <DisabledNote />
          ) : unsupportedMessage(adviceQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{unsupportedMessage(adviceQ.data)}</div>
          ) : adviceQ.data?.supported ? (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: stressLevelColor(adviceQ.data.stress_level) }}>
                  {adviceQ.data.stress_level_ar ?? '—'}
                </span>
                {adviceQ.data.sensitivity && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: sensitivityColor(adviceQ.data.sensitivity) }}>
                    حساسيّة المرحلة: {adviceQ.data.sensitivity}
                  </span>
                )}
                {adviceQ.data.is_critical_window && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: '1px solid #7c2d12', color: '#fdba74' }}>نافذة حرجة</span>
                )}
                {adviceQ.data.urgent_irrigation && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold" style={{ border: '1px solid #7f1d1d', color: '#fca5a5' }}>ريّ عاجل (حكم الخادم)</span>
                )}
              </div>
              {adviceQ.data.stage_ar && (
                <div className="text-[11px]" style={{ color: T.muted }}>
                  {adviceQ.data.crop_ar ?? '—'} · {adviceQ.data.stage_ar} · نضوب {fmtNum(adviceQ.data.depletion_pct, 0)}٪
                  {adviceQ.data.net_irrigation_mm != null && <> · صافي {fmtNum(adviceQ.data.net_irrigation_mm, 1)} مم</>}
                </div>
              )}
              {adviceQ.data.integrated_advice_ar
                ? <div className="text-[11px] font-bold" style={{ color: T.ink }}>{adviceQ.data.integrated_advice_ar}</div>
                : adviceQ.data.advice_ar && <div className="text-[11px]" style={{ color: T.ink }}>{adviceQ.data.advice_ar}</div>}
              {adviceQ.data.corroboration_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{adviceQ.data.corroboration_note_ar}</div>}
            </>
          ) : null}
        </div>
      )}

      {/* ── تقويم القمح التوافقيّ (wheat-calendar) — يتمايز بتحذير التشبّع المائيّ.
            التقويم العامّ حسب المحصول تعرضه بطاقة مخاطر المناخ — لا تكرار. ── */}
      {open === 'wheatcal' && (
        wheatCalQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة تقويم القمح المائيّ…</div>
        ) : wheatCalQ.isError ? (
          <RetryNote q={wheatCalQ} label="تقويم القمح المائيّ" />
        ) : wheatCalQ.data?.disabled ? (
          <DisabledNote />
        ) : wheatCalQ.data?.supported ? (
          <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
            <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Wheat className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> {wheatCalQ.data.crop_ar ?? 'القمح'}
              {wheatCalQ.data.season_total_mm && <span className="font-normal" style={{ color: T.faint }}> · الموسم {wheatCalQ.data.season_total_mm} مم</span>}
            </div>
            {wheatCalQ.data.critical_window_ar && <div className="text-[11px]" style={{ color: T.muted }}>النافذة الحرجة: {wheatCalQ.data.critical_window_ar}</div>}
            {wheatCalQ.data.irrigation_frequency_ar && <div className="text-[11px]" style={{ color: T.muted }}>الريّات: {wheatCalQ.data.irrigation_frequency_ar}</div>}
            {(wheatCalQ.data.stages ?? []).map((s) => (
              <div key={s.stage_key ?? s.name_ar} className="text-[11px]" style={{ color: T.muted }}>
                <b style={{ color: sensitivityColor(s.sensitivity) }}>{s.name_ar ?? '—'}</b>
                {s.water_share_pct != null && <> · {fmtNum(s.water_share_pct)}٪ من الاحتياج</>}
                {s.note_ar && <> — {s.note_ar}</>}
              </div>
            ))}
            {wheatCalQ.data.warning_waterlogging_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {wheatCalQ.data.warning_waterlogging_ar}</div>}
            {wheatCalQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{wheatCalQ.data.disclaimer_ar}</div>}
          </div>
        ) : null
      )}

      {/* ── ميزان الماء FAO-56: حرارتا اليوم من قياس؛ الملوحة تُفعَّل خادميّاً فقط
            عند تمرير تحليل مخبريّ (salinity_decision يُعرَض كما أعلنه الخادم). ── */}
      {open === 'balance' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <Waves className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <label htmlFor="wfo-wb-crop" className="font-bold" style={{ color: T.ink }}>المحصول:</label>
            <input id="wfo-wb-crop" type="text" value={wb.crop} onChange={(e) => setWbField('crop')(e.target.value)} placeholder={cropLabel ?? 'wheat'} className="w-24 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="wfo-wb-stage" className="font-bold" style={{ color: T.ink }}>المرحلة:</label>
            <select id="wfo-wb-stage" value={wb.stage} onChange={(e) => setWbField('stage')(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {WB_STAGE_OPTIONS.map((s) => <option key={s.key} value={s.key}>{s.label_ar}</option>)}
            </select>
            <NumField id="wfo-wb-tmin" label="الصغرى (°م):" value={wb.tMin} onChange={setWbField('tMin')} width="w-16" />
            <NumField id="wfo-wb-tmax" label="الكبرى (°م):" value={wb.tMax} onChange={setWbField('tMax')} width="w-16" />
            <NumField id="wfo-wb-rain" label="مطر اليوم (مم، اختياريّ):" value={wb.rainMm} onChange={setWbField('rainMm')} placeholder="افتراض الخادم 0" width="w-24" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="font-bold" style={{ color: T.ink }}>الموقع (اختياريّ — غيابه يُبقي افتراضات الخادم):</span>
            <NumField id="wfo-wb-lat" label="عرض:" value={wb.latitude} onChange={setWbField('latitude')} placeholder="15.5" width="w-16" />
            <NumField id="wfo-wb-elev" label="ارتفاع (م):" value={wb.elevation} onChange={setWbField('elevation')} placeholder="2000" width="w-20" />
            <NumField id="wfo-wb-doy" label="يوم السنة:" value={wb.dayOfYear} onChange={setWbField('dayOfYear')} placeholder="100" width="w-16" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="font-bold" style={{ color: T.ink }}>تحليل ملوحة (اختياريّ — حضوره يُفعّل مسار الملوحة خادميّاً):</span>
            <NumField id="wfo-wb-ece" label="ECe تربة:" value={wb.soilEce} onChange={setWbField('soilEce')} placeholder="dS/m" width="w-16" />
            <NumField id="wfo-wb-ecw" label="ECw ماء:" value={wb.waterEcw} onChange={setWbField('waterEcw')} placeholder="dS/m" width="w-16" />
            <NumField id="wfo-wb-age" label="عمر التحليل (يوم):" value={wb.analysisAgeDays} onChange={setWbField('analysisAgeDays')} width="w-16" />
            <NumField id="wfo-wb-conf" label="ثقته (٪):" value={wb.analysisConfidencePct} onChange={setWbField('analysisConfidencePct')} width="w-14" />
          </div>

          {!wbReq ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل المحصول وحرارتَي اليوم (من قياس) ليحسب الخادم ET₀ ⇒ ETc ⇒ الصافي.</div>
          ) : wbQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب ميزان الماء…</div>
          ) : wbQ.isError ? (
            <RetryNote q={wbQ} label="ميزان الماء" />
          ) : wbQ.data?.disabled ? (
            <DisabledNote />
          ) : wbQ.data ? (
            <>
              <FactPills facts={wbFacts} />
              {wbQ.data.kc_source_ar && <div className="text-[10px]" style={{ color: T.faint }}>Kc: {wbQ.data.kc_source_ar} · طريقة ET₀: {wbQ.data.method ?? '—'}</div>}
              {wbQ.data.advice_ar && <div className="text-[11px]" style={{ color: T.ink }}>{wbQ.data.advice_ar}</div>}
              {wbQ.data.salinity_decision && (
                <div className="text-[11px]" style={{ color: wbQ.data.salinity_decision.warn ? '#fdba74' : T.muted }}>
                  قرار الملوحة (الخادم): {wbQ.data.salinity_decision.enabled ? 'مُفعَّلة' : 'غير مُفعَّلة'} — {wbQ.data.salinity_decision.reason_ar ?? '—'}
                  {(wbQ.data.salinity_decision.signals ?? []).map((sig) => (
                    <div key={sig} className="text-[10px]" style={{ color: T.faint }}>• {sig}</div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* ── مورد السيول الواردة (upstream-flood): توجيه مفاهيميّ من الخادم حرفيّاً ── */}
      {open === 'flood' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <CloudLightning className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <NumField id="wfo-flood-rain" label="المطر المحلّيّ السنويّ (مم):" value={localRainInput} onChange={setLocalRainInput} width="w-24" />
          </div>
          {localRainMm == null ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل المطر المحلّيّ (مم/سنة من قياس/سجلّ) ليشرح الخادم مورد السيول الواردة.</div>
          ) : floodQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة مورد السيول…</div>
          ) : floodQ.isError ? (
            <RetryNote q={floodQ} label="مورد السيول الواردة" />
          ) : floodQ.data?.disabled ? (
            <DisabledNote />
          ) : floodQ.data ? (
            <>
              {floodParas.map((p) => (
                <div key={p.slice(0, 24)} className="text-[11px]" style={{ color: T.muted }}>{p}</div>
              ))}
              {floodQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{floodQ.data.caution_ar}</div>}
              {floodQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{floodQ.data.disclaimer_ar}</div>}
            </>
          ) : null}
        </div>
      )}

      {/* ── تحليل ماء الريّ المخبريّ: كتابة صريحة بزرّ (الخادم يخزّن ويحلّل SAR/RSC/EC).
            الغائب لا يُصفَّر — الخادم يُعلن missing_inputs بصدق. ── */}
      {open === 'lab' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <FlaskConical className="w-3.5 h-3.5 shrink-0 text-violet-300" aria-hidden="true" />
            <label htmlFor="wfo-lab-id" className="font-bold" style={{ color: T.ink }}>معرّف العيّنة:</label>
            <input id="wfo-lab-id" type="text" value={sample.sampleId} onChange={(e) => setSampleField('sampleId')(e.target.value)} placeholder="من /lab/samples" className="w-28 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="wfo-lab-src" className="font-bold" style={{ color: T.ink }}>المصدر:</label>
            <select id="wfo-lab-src" value={sample.source} onChange={(e) => setSampleField('source')(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {WATER_SOURCE_OPTIONS.map((s) => <option key={s.key} value={s.key}>{s.label_ar}</option>)}
            </select>
            <label htmlFor="wfo-lab-date" className="font-bold" style={{ color: T.ink }}>تاريخ العيّنة:</label>
            <input id="wfo-lab-date" type="date" value={sample.sampledAt} onChange={(e) => setSampleField('sampledAt')(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="font-bold" style={{ color: T.ink }}>الأيونات (meq/L):</span>
            <NumField id="wfo-lab-na" label="Na" value={sample.na} onChange={setSampleField('na')} width="w-14" />
            <NumField id="wfo-lab-ca" label="Ca" value={sample.ca} onChange={setSampleField('ca')} width="w-14" />
            <NumField id="wfo-lab-mg" label="Mg" value={sample.mg} onChange={setSampleField('mg')} width="w-14" />
            <NumField id="wfo-lab-hco3" label="HCO₃" value={sample.hco3} onChange={setSampleField('hco3')} width="w-14" />
            <NumField id="wfo-lab-co3" label="CO₃" value={sample.co3} onChange={setSampleField('co3')} width="w-14" />
            <NumField id="wfo-lab-cl" label="Cl" value={sample.cl} onChange={setSampleField('cl')} width="w-14" />
            <NumField id="wfo-lab-ec" label="EC (dS/m)" value={sample.ecDsm} onChange={setSampleField('ecDsm')} width="w-16" />
            <NumField id="wfo-lab-ph" label="pH" value={sample.ph} onChange={setSampleField('ph')} width="w-14" />
          </div>
          <div>
            <button
              type="button"
              disabled={!samplePayload || labM.isPending}
              onClick={() => samplePayload && labM.mutate(samplePayload)}
              className="text-[11px] px-3 py-1 rounded-lg font-bold disabled:opacity-50"
              style={{ border: '1px solid #0c4a6e', color: '#7dd3fc', background: 'rgba(12,74,110,.25)' }}
            >
              {labM.isPending ? 'جارٍ الإرسال…' : 'أرسِل نتيجة التحليل'}
            </button>
            {!samplePayload && <span className="ms-2 text-[10px]" style={{ color: T.faint }}>معرّف العيّنة إلزاميّ (من قسم عيّنات المختبر).</span>}
          </div>
          {labM.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{writeErrorMessage(labM.error)}</div>}
          {labM.data && (
            <>
              <div className="text-[11px] font-bold" style={{ color: T.ink }}>{labM.data.suitable_ar ?? '—'}</div>
              <FactPills facts={labIdx} />
              {labClasses.map((r) => (
                <div key={r.label_ar} className="text-[11px]" style={{ color: T.muted }}>
                  <b style={{ color: T.ink }}>{r.label_ar}:</b> {r.text_ar}
                </div>
              ))}
              {(labM.data.hazard_flags_ar ?? []).map((f) => (
                <div key={f} className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {f}</div>
              ))}
              {(labM.data.missing_inputs ?? []).length > 0 && (
                <div className="text-[10px]" style={{ color: T.faint }}>قياسات غير مُدخَلة (أعلنها الخادم): {(labM.data.missing_inputs ?? []).join('، ')}</div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── تنبيهات الطقس المشتقّة (بإحداثيّات، بلا كتابة) + manifest الطبقات ── */}
      {open === 'weather' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            {coordInputs('wfo-wx', false)}
            {lat == null || lon == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل إحداثيّات الحقل ليشتقّ الخادم تنبيهات الطقس الزراعيّة.</div>
            ) : alertsQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ اشتقاق التنبيهات…</div>
            ) : alertsQ.isError ? (
              <RetryNote q={alertsQ} label="تنبيهات الطقس" />
            ) : alertsQ.data?.disabled ? (
              <DisabledNote />
            ) : alerts.length > 0 ? (
              alerts.map((a) => (
                <div key={`${a.type}-${a.window}`} className="text-[11px]" style={{ color: T.muted }}>
                  <span className="px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: alertSeverityColor(a.severity) }}>
                    {a.title_ar ?? a.type ?? '—'}
                  </span>
                  {a.detail_ar && <span className="ms-1">{a.detail_ar}</span>}
                  {a.window && <span className="ms-1 text-[10px]" style={{ color: T.faint }}>({a.window})</span>}
                </div>
              ))
            ) : alertsQ.data ? (
              <div className="text-[11px]" style={{ color: T.muted }}>لا تنبيهات مشتقّة لهذه الإحداثيّات الآن (حكم الخادم).</div>
            ) : null}
          </div>

          {/* manifest الطبقات — تعريفات الخادم كما هي (وسم «مشتقّة» لعلم derived). */}
          {layersQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة طبقات الطقس…</div>
          ) : layersQ.isError ? (
            <RetryNote q={layersQ} label="طبقات الطقس" />
          ) : layersQ.data?.disabled ? (
            <DisabledNote />
          ) : layers.length > 0 ? (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
              <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                طبقات يرسمها SAHOOL ({layersQ.data?.source ?? '—'}):
              </div>
              <div className="flex flex-wrap gap-1.5">
                {layers.map((l) => (
                  <span key={l.key} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                    {layerCaption(l)}
                  </span>
                ))}
              </div>
              {(layersQ.data?.operation_layers ?? []).length > 0 && (
                <div className="text-[10px]" style={{ color: T.faint }}>
                  طبقات عمليّات: {(layersQ.data?.operation_layers ?? []).map((o) => o.label_ar ?? o.key).join('، ')}
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {/* ── خطّة 4R للتربة الكلسيّة — من تحليل مخبريّ (الخادم يحجب ما يحتاج تحليلاً) ── */}
      {open === 'nutrients' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <Leaf className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>تحليل التربة (المتوفّر فقط):</span>
            <NumField id="wfo-4r-caco3" label="CaCO₃ (٪):" value={soil4r.caco3Pct} onChange={set4rField('caco3Pct')} width="w-14" />
            <NumField id="wfo-4r-ph" label="pH:" value={soil4r.ph} onChange={set4rField('ph')} width="w-14" />
            <NumField id="wfo-4r-p" label="P (ppm):" value={soil4r.pPpm} onChange={set4rField('pPpm')} width="w-14" />
            <NumField id="wfo-4r-fe" label="Fe (ppm):" value={soil4r.fePpm} onChange={set4rField('fePpm')} width="w-14" />
            <NumField id="wfo-4r-zn" label="Zn (ppm):" value={soil4r.znPpm} onChange={set4rField('znPpm')} width="w-14" />
            <NumField id="wfo-4r-om" label="مادّة عضويّة (٪):" value={soil4r.omPct} onChange={set4rField('omPct')} width="w-14" />
          </div>
          {!soil4rReq ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل قيمة تحليل مخبريّ واحدة على الأقلّ — لا خطّة تسميد من لا شيء.</div>
          ) : planQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ بناء خطّة 4R…</div>
          ) : planQ.isError ? (
            <RetryNote q={planQ} label="خطّة 4R" />
          ) : planQ.data?.disabled ? (
            <DisabledNote />
          ) : plan.length > 0 ? (
            plan.map((item) => {
              const badge = nutrientStatusBadge(item.status);
              return (
                <div key={item.nutrient} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line }}>
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <b style={{ color: T.ink }}>{nutrientNameAr(item.nutrient)}</b>
                    <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: badge.color }}>{badge.label_ar}</span>
                  </div>
                  {item.source_ar && <div className="text-[11px]" style={{ color: T.muted }}>المصدر: {item.source_ar}</div>}
                  {item.rate_ar && <div className="text-[11px]" style={{ color: T.muted }}>المعدّل: {item.rate_ar}</div>}
                  {item.timing_ar && <div className="text-[11px]" style={{ color: T.muted }}>التوقيت: {item.timing_ar}</div>}
                  {item.placement_ar && <div className="text-[11px]" style={{ color: T.muted }}>الموضع: {item.placement_ar}</div>}
                  {(item.warnings_ar ?? []).map((w) => (
                    <div key={w} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {w}</div>
                  ))}
                </div>
              );
            })
          ) : planQ.data ? (
            <div className="text-[11px]" style={{ color: T.muted }}>لا بنود خطّة أعادها الخادم لهذه المدخلات.</div>
          ) : null}
        </div>
      )}

      {/* ── تسجيل نتيجة (outcome/record): كتابة تُدِيم القياس في outcome_record —
            نموذج كتابة صادق: زرّ صريح، persisted/replayed كما أعلنها الخادم،
            و503 يعني «لم يُسجَّل شيء» (لا نجاح مُختلق). القياس بلا إدامة (/measure)
            موجود في صفحة تشغيل القرار — لا تكرار. ── */}
      {open === 'outcome' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <NotebookPen className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
            <label htmlFor="wfo-out-did" className="font-bold" style={{ color: T.ink }}>معرّف القرار (اختياريّ):</label>
            <input id="wfo-out-did" type="text" value={outcome.decisionId} onChange={(e) => setOutcomeField('decisionId')(e.target.value)} placeholder="يُسَكّ إن غاب" className="w-32 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="wfo-out-idem" className="font-bold" style={{ color: T.ink }}>مفتاح لاتكرار (اختياريّ):</label>
            <input id="wfo-out-idem" type="text" value={outcome.idempotencyKey} onChange={(e) => setOutcomeField('idempotencyKey')(e.target.value)} placeholder="يمنع تكرار العيّنة" className="w-32 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="font-bold" style={{ color: T.ink }}>المُخطَّط:</span>
            <NumField id="wfo-out-rec" label="ريّ موصى (مم):" value={outcome.recommendedIrrigationMm} onChange={setOutcomeField('recommendedIrrigationMm')} width="w-16" />
            <NumField id="wfo-out-stress-p" label="أيّام إجهاد متوقّعة:" value={outcome.predictedStressDays} onChange={setOutcomeField('predictedStressDays')} width="w-14" />
            <NumField id="wfo-out-yield-p" label="غلّة متوقّعة (طن/هـ):" value={outcome.expectedYieldTHa} onChange={setOutcomeField('expectedYieldTHa')} width="w-16" />
            <NumField id="wfo-out-budget" label="موازنة الموسم (مم):" value={outcome.seasonBudgetMm} onChange={setOutcomeField('seasonBudgetMm')} width="w-16" />
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="font-bold" style={{ color: T.ink }}>المرصود:</span>
            <NumField id="wfo-out-act" label="ريّ فعليّ (مم):" value={outcome.actualIrrigationMm} onChange={setOutcomeField('actualIrrigationMm')} width="w-16" />
            <NumField id="wfo-out-stress-a" label="أيّام إجهاد مرصودة:" value={outcome.observedStressDays} onChange={setOutcomeField('observedStressDays')} width="w-14" />
            <NumField id="wfo-out-yield-a" label="غلّة فعليّة (طن/هـ):" value={outcome.actualYieldTHa} onChange={setOutcomeField('actualYieldTHa')} width="w-16" />
            <NumField id="wfo-out-water" label="ماء مستهلَك (مم):" value={outcome.actualWaterUsedMm} onChange={setOutcomeField('actualWaterUsedMm')} width="w-16" />
          </div>
          <div>
            <button
              type="button"
              disabled={!outcomeReq || outcomeM.isPending}
              onClick={() => outcomeReq && outcomeM.mutate(outcomeReq)}
              className="text-[11px] px-3 py-1 rounded-lg font-bold disabled:opacity-50"
              style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(20,83,45,.25)' }}
            >
              {outcomeM.isPending ? 'جارٍ الإدامة…' : 'سجّل النتيجة (إدامة دائمة)'}
            </button>
            {!outcomeReq && <span className="ms-2 text-[10px]" style={{ color: T.faint }}>قيمة واحدة على الأقلّ (مُخطَّطة أو مرصودة) — لا نُدِيم سجلّاً فارغاً.</span>}
          </div>
          {outcomeM.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{writeErrorMessage(outcomeM.error)}</div>}
          {outcomeM.data && (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: successBadge.color }}>{successBadge.label_ar}</span>
                {outcomeM.data.persisted && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#86efac' }}>
                    {outcomeM.data.replayed ? 'أُعيد القياس القائم (لم تُكرَّر العيّنة)' : 'أُديمت في سجلّ النتائج'}
                  </span>
                )}
              </div>
              <div className="text-[10px]" style={{ color: T.faint }}>
                outcome: {outcomeM.data.outcome_id ?? '—'} · decision: {outcomeM.data.decision_id ?? '—'}
              </div>
              {recordedMetrics.map((m) => (
                <div key={m.key} className="text-[11px]" style={{ color: T.muted }}>
                  • {m.label_ar ?? m.key ?? '—'}
                  {m.delta != null && <span style={{ color: T.faint }}> (Δ {fmtNum(m.delta, 2)})</span>}
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* ── تحديد موقع الحقل: المحافظة/الإقليم/المناخ من GPS (الارتفاع يحسم الجبليّ) ── */}
      {open === 'geo' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          {coordInputs('wfo-geo', true)}
          {lat == null || lon == null ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل إحداثيّات الحقل (من GPS) ليحدّد الخادم المحافظة والإقليم المناخيّ.</div>
          ) : geoQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تحديد الموقع…</div>
          ) : geoQ.isError ? (
            <RetryNote q={geoQ} label="تحديد الموقع" />
          ) : geoQ.data?.disabled ? (
            <DisabledNote />
          ) : unsupportedMessage(geoQ.data) ? (
            <div className="text-[11px]" style={{ color: T.muted }}>{unsupportedMessage(geoQ.data)}</div>
          ) : geoQ.data?.supported ? (
            <>
              <FactPills facts={gFacts} />
              {geoQ.data.climate_ar && <div className="text-[11px]" style={{ color: T.muted }}>{geoQ.data.climate_ar}</div>}
              {geoQ.data.zone_source_ar && <div className="text-[10px]" style={{ color: T.faint }}>أساس التصنيف: {geoQ.data.zone_source_ar}</div>}
              {listOrText(geoQ.data.suited_crops_ar) && <div className="text-[11px]" style={{ color: T.muted }}>محاصيل ملائمة: {listOrText(geoQ.data.suited_crops_ar)}</div>}
              {listOrText(geoQ.data.avoid_ar) && <div className="text-[11px]" style={{ color: '#fdba74' }}>تجنّب: {listOrText(geoQ.data.avoid_ar)}</div>}
              {geoQ.data.multi_zone_warning_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{geoQ.data.multi_zone_warning_ar}</div>}
              {geoQ.data.yemen_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{geoQ.data.yemen_note_ar}</div>}
              {geoQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{geoQ.data.disclaimer_ar}</div>}
            </>
          ) : null}
        </div>
      )}
    </section>
  );
}
