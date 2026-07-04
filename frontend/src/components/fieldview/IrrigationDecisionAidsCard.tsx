import { useMemo, useState } from 'react';
import { Droplets, FlaskConical, Gauge, Layers, Sprout, Waves } from 'lucide-react';
import {
  useGrossIrrigation,
  useIrrigationConfidence,
  useIrrigationSoilTypes,
  useMoistureDecision,
  useNdviConfidence,
  useSoilSamplingDepth,
  useSoilSamplingProtocol,
  useSoilSamplingSubsamples,
  useWaterSensitivityCrops,
} from '../../hooks/useIrrigationDecisionAids';
import {
  IRRIGATION_METHOD_OPTIONS,
  SAMPLING_PURPOSE_OPTIONS,
  SOIL_TYPE_OPTIONS,
  confidenceBadge,
  confidenceComponentFacts,
  cropsRows,
  depthRows,
  fmtNum,
  grossFacts,
  inputNamesAr,
  moistureDecisionColor,
  moistureFacts,
  parseMeasure,
  parsePctToFraction,
  pctFromFraction,
  soilTypeRows,
  subsampleFacts,
  unsupportedMessage,
  type IrrigationConfidenceInput,
  type NdviConfidenceInput,
} from '../../lib/irrigationDecisionAids';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — تُمرَّر للخادم كسياق (root depth/حساسيّة المرحلة). */
  cropLabel?: string | null;
  enabled?: boolean;
}

type SectionKey = 'moisture' | 'confidence' | 'gross' | 'crops' | 'soils' | 'sampling';

const SECTIONS: { key: SectionKey; label_ar: string }[] = [
  { key: 'moisture', label_ar: 'قرار الرطوبة' },
  { key: 'confidence', label_ar: 'ثقة القراءة' },
  { key: 'gross', label_ar: 'الإجمالي المسحوب' },
  { key: 'crops', label_ar: 'حساسيّة المحاصيل' },
  { key: 'soils', label_ar: 'أنواع التربة' },
  { key: 'sampling', label_ar: 'عيّنة التربة' },
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

/** «هل أروي الآن وبكم أثق؟»: قرار رطوبة RWC من قراءة مستشعر يُدخِلها المستخدم +
 *  شارات ثقة القراءة/التوصية + الصافي⇒الإجمالي المسحوب + مراجع (محاصيل حسّاسة/
 *  أنواع تربة/بروتوكول عيّنة). الأحكام والنصوص كلّها من الخادم — الواجهة تعرض
 *  ولا تحكم؛ 404 ⇒ «غير مُفعَّل» صادقة، وأخطاء الشبكة ⇒ نصّ إعادة محاولة. */
export default function IrrigationDecisionAidsCard({ cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<SectionKey>('moisture');

  // — قرار الرطوبة: قراءة المستشعر ٪ (تُحوَّل كسراً للخادم — تحويل وحدة بحت) —
  const [vwcPctInput, setVwcPctInput] = useState('');
  const [soilType, setSoilType] = useState('loam');
  const [rootDepthInput, setRootDepthInput] = useState('');
  const vwc = useMemo(() => parsePctToFraction(vwcPctInput), [vwcPctInput]);
  const rootDepthM = useMemo(() => parseMeasure(rootDepthInput), [rootDepthInput]);
  const moistureQ = useMoistureDecision(
    { vwc, soilType, crop: cropLabel ?? null, rootDepthM },
    enabled && open === 'moisture',
  );

  // — ثقة قراءة NDVI: مدخلات المستخدم كاملة قبل أيّ استدعاء (لا تخمين) —
  const [ndviInput, setNdviInput] = useState('');
  const [obsDate, setObsDate] = useState('');
  const [areaInput, setAreaInput] = useState('');
  const [cloudInput, setCloudInput] = useState('');
  const ndviReq = useMemo<NdviConfidenceInput | null>(() => {
    const ndvi = parseMeasure(ndviInput);
    const area = parseMeasure(areaInput);
    if (ndvi == null || area == null || !obsDate) return null;
    const cloud = parseMeasure(cloudInput);
    // cloud_pct يُرسَل فقط إن أدخله المستخدم — غيابه يترك افتراض الخادم (0) معلَناً في عقده.
    return {
      ndvi_value: ndvi,
      observation_date: obsDate,
      field_area_ha: area,
      ...(cloud != null ? { cloud_pct: cloud } : {}),
    };
  }, [ndviInput, obsDate, areaInput, cloudInput]);
  const ndviConfQ = useNdviConfidence(enabled && open === 'confidence' ? ndviReq : null);

  // — ثقة توصية الريّ المُجمَّعة: أربعة كسور اختياريّة (٪ من المستخدم) — الغائب
  //   يُرسَل null والخادم يحكم (ET₀ حرج ⇒ غيابه unsafe من الخادم لا منّا) —
  const [cNdvi, setCNdvi] = useState('');
  const [cEt0, setCEt0] = useState('');
  const [cSoil, setCSoil] = useState('');
  const [cWx, setCWx] = useState('');
  const irrReq = useMemo<IrrigationConfidenceInput | null>(() => {
    const n = parsePctToFraction(cNdvi);
    const e = parsePctToFraction(cEt0);
    const s = parsePctToFraction(cSoil);
    const w = parsePctToFraction(cWx);
    if (n == null && e == null && s == null && w == null) return null;
    return { ndvi_confidence: n, et0_confidence: e, soil_moisture_confidence: s, weather_forecast_confidence: w };
  }, [cNdvi, cEt0, cSoil, cWx]);
  const irrConfQ = useIrrigationConfidence(enabled && open === 'confidence' ? irrReq : null);

  // — الإجمالي المسحوب: الصافي مم + طريقة (مفاتيح الخادم) + كفاءة اختياريّة ٪ —
  const [netInput, setNetInput] = useState('');
  const [method, setMethod] = useState('drip');
  const [effInput, setEffInput] = useState('');
  const netMm = useMemo(() => parseMeasure(netInput), [netInput]);
  const eff = useMemo(() => parsePctToFraction(effInput), [effInput]);
  const grossQ = useGrossIrrigation(netMm, method, eff, enabled && open === 'gross');

  // — مراجع: محاصيل حساسيّة الماء + أنواع التربة (تُجلَب عند فتح قسمها فقط) —
  const cropsQ = useWaterSensitivityCrops(enabled && open === 'crops');
  const soilTypesQ = useIrrigationSoilTypes(enabled && (open === 'soils' || open === 'moisture'));

  // — عيّنة التربة: مساحة من قياس المستخدم + غرض؛ البروتوكول الكامل عند الطلب —
  const [sampleAreaInput, setSampleAreaInput] = useState('');
  const [purpose, setPurpose] = useState('general');
  const [showProtocol, setShowProtocol] = useState(false);
  const sampleArea = useMemo(() => parseMeasure(sampleAreaInput), [sampleAreaInput]);
  const subsQ = useSoilSamplingSubsamples(sampleArea, enabled && open === 'sampling');
  const depthQ = useSoilSamplingDepth(purpose, enabled && open === 'sampling');
  const protocolQ = useSoilSamplingProtocol(sampleArea, purpose, enabled && open === 'sampling' && showProtocol);

  const mFacts = useMemo(() => moistureFacts(moistureQ.data), [moistureQ.data]);
  const ndviBadge = confidenceBadge(ndviConfQ.data?.confidence?.level);
  const irrBadge = confidenceBadge(irrConfQ.data?.level);
  const gFacts = useMemo(() => grossFacts(grossQ.data), [grossQ.data]);
  const crops = useMemo(() => cropsRows(cropsQ.data), [cropsQ.data]);
  const soils = useMemo(() => soilTypeRows(soilTypesQ.data), [soilTypesQ.data]);
  const sFacts = useMemo(() => subsampleFacts(subsQ.data), [subsQ.data]);
  const dRows = useMemo(() => depthRows(depthQ.data), [depthQ.data]);

  if (!enabled) return null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="irrigation-decision-aids" aria-label="مساعدات قرار الريّ والعيّنات">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-sky-300" aria-hidden="true" /> مساعدات قرار الريّ والعيّنات
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

      {/* ── قرار الرطوبة: VWC من مستشعر حقيقيّ → RWC → قرار الخادم + كمّيّته ── */}
      {open === 'moisture' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <Gauge className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <label htmlFor="ida-vwc" className="font-bold" style={{ color: T.ink }}>رطوبة المستشعر VWC (٪):</label>
            <input id="ida-vwc" type="number" min="0" max="100" step="0.1" value={vwcPctInput} onChange={(e) => setVwcPctInput(e.target.value)} placeholder="من قياس" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="ida-soil" className="font-bold" style={{ color: T.ink }}>التربة:</label>
            <select id="ida-soil" value={soilType} onChange={(e) => setSoilType(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {SOIL_TYPE_OPTIONS.map((s) => (
                <option key={s.key} value={s.key}>{s.label_ar}</option>
              ))}
            </select>
            <label htmlFor="ida-root" className="font-bold" style={{ color: T.ink }}>عمق الجذور (م، اختياري):</label>
            <input id="ida-root" type="number" min="0" step="0.1" value={rootDepthInput} onChange={(e) => setRootDepthInput(e.target.value)} placeholder="تلقائي" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
          </div>

          {vwc == null ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل قراءة رطوبة حقيقيّة من المستشعر (٪) ليقرّر الخادم.</div>
          ) : moistureQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب قرار الرطوبة…</div>
          ) : moistureQ.isError ? (
            <RetryNote q={moistureQ} label="قرار الرطوبة" />
          ) : moistureQ.data?.disabled ? (
            <DisabledNote />
          ) : moistureQ.data?.ok === false ? (
            <div className="text-[11px]" style={{ color: '#fdba74' }}>{moistureQ.data.error_ar ?? '—'}</div>
          ) : moistureQ.data?.ok ? (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: moistureDecisionColor(moistureQ.data.decision) }}>
                  {moistureQ.data.decision_ar ?? '—'}
                </span>
                {moistureQ.data.reason_ar && <span className="text-[11px]" style={{ color: T.muted }}>{moistureQ.data.reason_ar}</span>}
              </div>
              <FactPills facts={mFacts} />
              {moistureQ.data.irrigation_amount && (
                <div className="text-[11px]" style={{ color: T.ink }}>
                  كمّيّة الريّ: <b>{fmtNum(moistureQ.data.irrigation_amount.irrigation_mm, 1)} مم</b>
                  <span style={{ color: T.faint }}> · عمق الجذور {fmtNum(moistureQ.data.irrigation_amount.root_depth_m, 2)} م ({moistureQ.data.irrigation_amount.root_depth_source_ar ?? '—'})</span>
                  {moistureQ.data.irrigation_amount.note_ar && <div style={{ color: T.muted }}>{moistureQ.data.irrigation_amount.note_ar}</div>}
                </div>
              )}
              {moistureQ.data.stage_sensitivity_note_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{moistureQ.data.stage_sensitivity_note_ar}</div>}
              {moistureQ.data.fc_ratio_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{moistureQ.data.fc_ratio_note_ar}</div>}
              {moistureQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{moistureQ.data.disclaimer_ar}</div>}
            </>
          ) : null}
        </div>
      )}

      {/* ── ثقة القراءة والتوصية: شارات مستوى الخادم حرفيّاً + أساسها (مكوّنات/أسباب) ── */}
      {open === 'confidence' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Gauge className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
              <span className="font-bold" style={{ color: T.ink }}>ثقة قراءة NDVI:</span>
              <label htmlFor="ida-ndvi">القيمة:</label>
              <input id="ida-ndvi" type="number" step="0.01" min="-1" max="1" value={ndviInput} onChange={(e) => setNdviInput(e.target.value)} placeholder="0.62" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-obs">تاريخ الرصد:</label>
              <input id="ida-obs" type="date" value={obsDate} onChange={(e) => setObsDate(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-area">المساحة (هكتار):</label>
              <input id="ida-area" type="number" min="0" step="0.1" value={areaInput} onChange={(e) => setAreaInput(e.target.value)} placeholder="من قياس" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-cloud">سحب (٪، اختياري):</label>
              <input id="ida-cloud" type="number" min="0" max="100" step="1" value={cloudInput} onChange={(e) => setCloudInput(e.target.value)} placeholder="0" className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            </div>
            {ndviReq == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل قيمة NDVI وتاريخ الرصد والمساحة ليُقيّم الخادم الثقة.</div>
            ) : ndviConfQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم ثقة القراءة…</div>
            ) : ndviConfQ.isError ? (
              <RetryNote q={ndviConfQ} label="ثقة قراءة NDVI" />
            ) : ndviConfQ.data?.disabled ? (
              <DisabledNote />
            ) : ndviConfQ.data?.confidence ? (
              <>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: ndviBadge.color }}>
                    {ndviBadge.label_ar} · {pctFromFraction(ndviConfQ.data.confidence.score)}
                  </span>
                </div>
                <FactPills facts={confidenceComponentFacts(ndviConfQ.data)} />
                {(ndviConfQ.data.reasons_ar ?? []).map((r) => (
                  <div key={r} className="text-[11px]" style={{ color: '#fdba74' }}>• {r}</div>
                ))}
                {ndviConfQ.data.recommendation_ar && <div className="text-[11px]" style={{ color: T.muted }}>{ndviConfQ.data.recommendation_ar}</div>}
              </>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
              <Waves className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
              <span className="font-bold" style={{ color: T.ink }}>ثقة توصية الريّ (٪ لكلّ مصدر، اترك الغائب فارغاً):</span>
              <label htmlFor="ida-cn">NDVI:</label>
              <input id="ida-cn" type="number" min="0" max="100" value={cNdvi} onChange={(e) => setCNdvi(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-ce">ET₀:</label>
              <input id="ida-ce" type="number" min="0" max="100" value={cEt0} onChange={(e) => setCEt0(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-cs">رطوبة التربة:</label>
              <input id="ida-cs" type="number" min="0" max="100" value={cSoil} onChange={(e) => setCSoil(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
              <label htmlFor="ida-cw">توقّعات الطقس:</label>
              <input id="ida-cw" type="number" min="0" max="100" value={cWx} onChange={(e) => setCWx(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            </div>
            {irrReq == null ? (
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل ثقة مصدر واحد على الأقلّ — الخادم يجمعها (ET₀ حرج عنده).</div>
            ) : irrConfQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تجميع ثقة التوصية…</div>
            ) : irrConfQ.isError ? (
              <RetryNote q={irrConfQ} label="ثقة توصية الريّ" />
            ) : irrConfQ.data?.disabled ? (
              <DisabledNote />
            ) : irrConfQ.data ? (
              <>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] px-2 py-0.5 rounded-full font-bold" style={{ border: `1px solid ${T.line}`, color: irrBadge.color }}>
                    {irrBadge.label_ar} · {pctFromFraction(irrConfQ.data.score)}
                  </span>
                  {irrConfQ.data.safe_for_action != null && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: irrConfQ.data.safe_for_action ? '#86efac' : '#fdba74' }}>
                      {irrConfQ.data.safe_for_action ? 'آمنة للتنفيذ الآلي (حكم الخادم)' : 'غير آمنة للتنفيذ الآلي (حكم الخادم)'}
                    </span>
                  )}
                </div>
                {irrConfQ.data.rationale_ar && <div className="text-[11px]" style={{ color: T.muted }}>{irrConfQ.data.rationale_ar}</div>}
                {(irrConfQ.data.inputs_missing ?? []).length > 0 && (
                  <div className="text-[11px]" style={{ color: '#fca5a5' }}>مدخلات حرجة مفقودة: {inputNamesAr(irrConfQ.data.inputs_missing).join('، ')}</div>
                )}
                {(irrConfQ.data.inputs_degraded ?? []).length > 0 && (
                  <div className="text-[11px]" style={{ color: '#fdba74' }}>مدخلات ضعيفة: {inputNamesAr(irrConfQ.data.inputs_degraded).join('، ')}</div>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* ── الإجمالي المسحوب: الصافي ÷ كفاءة التطبيق — حساب الخادم (calibrated=false) ── */}
      {open === 'gross' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <Waves className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <label htmlFor="ida-net" className="font-bold" style={{ color: T.ink }}>الصافي (مم):</label>
            <input id="ida-net" type="number" min="0" step="0.1" value={netInput} onChange={(e) => setNetInput(e.target.value)} placeholder="من خطّة الريّ" className="w-24 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="ida-method" className="font-bold" style={{ color: T.ink }}>الطريقة:</label>
            <select id="ida-method" value={method} onChange={(e) => setMethod(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {IRRIGATION_METHOD_OPTIONS.map((m) => (
                <option key={m.key} value={m.key}>{m.label_ar}</option>
              ))}
            </select>
            <label htmlFor="ida-eff" className="font-bold" style={{ color: T.ink }}>كفاءة مقيسة (٪، اختياري):</label>
            <input id="ida-eff" type="number" min="1" max="100" step="1" value={effInput} onChange={(e) => setEffInput(e.target.value)} placeholder="كفاءة الطريقة" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
          </div>
          {netMm == null || netMm <= 0 ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل الصافي (مم) من خطّة الريّ ليحسب الخادم الماء المسحوب فعلاً.</div>
          ) : grossQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب الإجمالي المسحوب…</div>
          ) : grossQ.isError ? (
            <RetryNote q={grossQ} label="الإجمالي المسحوب" />
          ) : grossQ.data?.disabled ? (
            <DisabledNote />
          ) : grossQ.data ? (
            <>
              <FactPills facts={gFacts} />
              {grossQ.data.calibrated === false && (
                <div className="text-[10px]" style={{ color: '#fdba74' }}>⚠ كفاءة غير معايَرة لهذا النظام (علم الخادم calibrated=false) — أدخِل كفاءة مقيسة إن توفّرت.</div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* ── المحاصيل المدعومة بحساسيّة المراحل المائيّة — قائمة الخادم كما هي ── */}
      {open === 'crops' && (
        cropsQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المحاصيل المدعومة…</div>
        ) : cropsQ.isError ? (
          <RetryNote q={cropsQ} label="محاصيل حساسيّة الماء" />
        ) : cropsQ.data?.disabled ? (
          <DisabledNote />
        ) : crops.length > 0 ? (
          <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
            <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Sprout className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> محاصيل مدعومة بتقويم مائيّ:
            </div>
            {crops.map((c) => (
              <div key={c.crop} className="text-[11px]" style={{ color: T.muted }}>
                <b style={{ color: T.ink }}>{c.name_ar ?? c.crop}</b>
                {c.drought_tolerance_ar && <> · تحمّل الجفاف: {c.drought_tolerance_ar}</>}
                {c.season_ar && <> · الموسم: {c.season_ar}</>}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: T.muted }}>لا محاصيل مدعومة من الخادم بعد.</div>
        )
      )}

      {/* ── أنواع التربة المرجعيّة (θs/θFC/θWP — NRCCA عبر الخادم) ── */}
      {open === 'soils' && (
        soilTypesQ.isLoading ? (
          <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة أنواع التربة…</div>
        ) : soilTypesQ.isError ? (
          <RetryNote q={soilTypesQ} label="أنواع التربة" />
        ) : soilTypesQ.data?.disabled ? (
          <DisabledNote />
        ) : soils.length > 0 ? (
          <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
            <div className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
              <Layers className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" /> القيم المرجعيّة لأنواع التربة:
            </div>
            {soils.map((s) => (
              <div key={s.key} className="text-[11px]" style={{ color: T.muted }}>
                <b style={{ color: T.ink }}>{s.name_ar ?? s.key}</b>
                {' · '}θFC {fmtNum(s.theta_fc, 3)} · θWP {fmtNum(s.theta_wp, 3)} · θs {fmtNum(s.theta_s, 3)}
                {s.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{s.note_ar}</div>}
              </div>
            ))}
            {soilTypesQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{soilTypesQ.data.note_ar}</div>}
          </div>
        ) : (
          <div className="text-[11px]" style={{ color: T.muted }}>لا قيم مرجعيّة من الخادم بعد.</div>
        )
      )}

      {/* ── عيّنة التربة: عدد فرعيّات حسب مساحة مقيسة + عمق حسب الغرض + بروتوكول كامل ── */}
      {open === 'sampling' && (
        <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <FlaskConical className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <label htmlFor="ida-sarea" className="font-bold" style={{ color: T.ink }}>مساحة الحقل (هكتار):</label>
            <input id="ida-sarea" type="number" min="0" step="0.1" value={sampleAreaInput} onChange={(e) => setSampleAreaInput(e.target.value)} placeholder="من قياس" className="w-20 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
            <label htmlFor="ida-purpose" className="font-bold" style={{ color: T.ink }}>الغرض:</label>
            <select id="ida-purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)} className="px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle}>
              {SAMPLING_PURPOSE_OPTIONS.map((p) => (
                <option key={p.key} value={p.key}>{p.label_ar}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setShowProtocol((v) => !v)}
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{ border: `1px solid ${showProtocol ? '#14532d' : T.line}`, color: showProtocol ? '#86efac' : T.muted, background: showProtocol ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)' }}
            >
              البروتوكول الكامل
            </button>
          </div>

          {/* عدد العيّنات الفرعيّة — حكم الخادم من مساحة مقيسة فقط */}
          {sampleArea == null ? (
            <div className="text-[10px]" style={{ color: T.faint }}>أدخِل مساحة الحقل (من قياس) ليوصي الخادم بعدد العيّنات الفرعيّة.</div>
          ) : subsQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب العيّنات الفرعيّة…</div>
          ) : subsQ.isError ? (
            <RetryNote q={subsQ} label="عدد العيّنات الفرعيّة" />
          ) : subsQ.data?.disabled ? (
            <DisabledNote />
          ) : unsupportedMessage(subsQ.data) ? (
            <div className="text-[11px]" style={{ color: '#fdba74' }}>{unsupportedMessage(subsQ.data)}</div>
          ) : (
            <>
              <FactPills facts={sFacts} />
              {subsQ.data?.advice_ar && <div className="text-[11px]" style={{ color: T.muted }}>{subsQ.data.advice_ar}</div>}
              {subsQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{subsQ.data.note_ar}</div>}
            </>
          )}

          {/* العمق حسب الغرض — مرجع الخادم */}
          {depthQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة عمق العيّنة…</div>
          ) : depthQ.isError ? (
            <RetryNote q={depthQ} label="عمق العيّنة" />
          ) : depthQ.data?.disabled ? (
            <DisabledNote />
          ) : depthQ.data ? (
            <div className="text-[11px]" style={{ color: T.ink }}>
              العمق الموصى به: <b>{depthQ.data.depth_ar ?? '—'}</b>
              {depthQ.data.applies_to_ar && <span style={{ color: T.faint }}> · {depthQ.data.applies_to_ar}</span>}
              {dRows.length > 0 && (
                <div className="text-[10px] mt-0.5" style={{ color: T.faint }}>
                  {dRows.map((r) => `${r.for_ar ?? r.purpose ?? '—'}: ${r.depth_ar ?? '—'}`).join(' · ')}
                </div>
              )}
              {depthQ.data.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{depthQ.data.principle_ar}</div>}
            </div>
          ) : null}

          {/* البروتوكول الكامل عند الطلب — خطوات/تحذيرات/توقيت الخادم حرفيّاً */}
          {showProtocol && (
            protocolQ.isLoading ? (
              <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة البروتوكول…</div>
            ) : protocolQ.isError ? (
              <RetryNote q={protocolQ} label="بروتوكول العيّنة" />
            ) : protocolQ.data?.disabled ? (
              <DisabledNote />
            ) : protocolQ.data ? (
              <div className="flex flex-col gap-1 rounded-xl border p-2" style={boxStyle}>
                {(protocolQ.data.steps_ar ?? []).map((s) => (
                  <div key={s} className="text-[11px]" style={{ color: T.muted }}>{s}</div>
                ))}
                {(protocolQ.data.avoid_ar ?? []).map((a) => (
                  <div key={a} className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {a}</div>
                ))}
                {protocolQ.data.timing_ar && <div className="text-[10px]" style={{ color: T.faint }}>{protocolQ.data.timing_ar}</div>}
                {protocolQ.data.yemen_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{protocolQ.data.yemen_note_ar}</div>}
                {protocolQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{protocolQ.data.disclaimer_ar}</div>}
              </div>
            ) : null
          )}
        </div>
      )}
    </section>
  );
}
