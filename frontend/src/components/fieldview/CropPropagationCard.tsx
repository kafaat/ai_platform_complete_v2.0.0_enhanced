import { useMemo, useState } from 'react';
import {
  ChevronDown, ChevronLeft, FlaskConical, Grid3x3, Layers,
  Leaf, Scissors, Sprout, ThermometerSun,
} from 'lucide-react';
import {
  useCompareDroughtResilience,
  useCropSuitability,
  useCropTwinCompose,
  useDroughtResilience,
  usePracticeGuide,
  usePracticesList,
  usePropagationMethodGuide,
  usePropagationMethods,
  useRootstockSelection,
  useSamplingStrategy,
  useSeedEvaluate,
} from '../../hooks/useCropPropagation';
import {
  comparedCrops, composeFacts, composeStressFlags, droughtComponentFacts, droughtRiskColor,
  fmtNum, methodGuideTypes, practiceBenefits, practicesList, propagationMethods, qualityColor,
  rankedCrops, rootstockStresses, samplingDepths, samplingFacts, samplingMethodBadge,
  seedAcceptableColor, seedFlags, serverMessage, suitabilityRatingColor,
} from '../../lib/cropPropagation';
import type { DisplayFact } from '../../lib/cropPropagation';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — سياق عرض/إدخال افتراضيّ (المحرّكات محايدة المحصول). */
  cropLabel?: string | null;
  enabled?: boolean;
}

// ألوان بطاقات فرعيّة داكنة مطابقة لـWaterHarvestingCard/AgronomyConsistencyCard.
const CARD_BG = 'rgba(15,23,42,.35)';
const SUB_BG = 'rgba(2,6,23,.5)';

type SectionKey =
  | 'suitability' | 'compose' | 'propagation' | 'practices'
  | 'drought' | 'seed' | 'sampling';

/** تحليل رقم من نصّ إدخال — فارغ/غير منتهٍ ⇒ null (لا افتراض قيمة، لا تخمين). */
function parseNum(text: string): number | null {
  const t = text.trim();
  if (t === '') return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** رأس قسم قابل للطيّ (RTL: يسار = مفتوح) — نفس أسلوب AgronomyConsistencyCard. */
function SectionHeader({
  icon, title, open, onToggle,
}: { icon: React.ReactNode; title: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center justify-between gap-2 rounded-xl border px-2.5 py-1.5"
      style={{ borderColor: T.line, background: CARD_BG }}
    >
      <span className="inline-flex items-center gap-2 text-[12px] font-bold" style={{ color: T.ink }}>
        {icon} {title}
      </span>
      {open
        ? <ChevronDown className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />
        : <ChevronLeft className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />}
    </button>
  );
}

/** وسم حقيقة صغير (label: value) — نفس أسلوب WaterHarvestingCard/AgronomyConsistencyCard. */
function FactPills({ facts }: { facts: DisplayFact[] }) {
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

const inputCls = 'px-2 py-0.5 rounded-lg text-[11px]';
const inputStyle = { border: `1px solid ${T.line}`, background: SUB_BG, color: T.ink } as const;

/** حقل نصّ/رقم صغير موسوم — لا افتراض قيمة (فارغ ⇒ لا إرسال في موقع الاستدعاء). */
function LabeledInput({
  id, label, value, onChange, type = 'text', placeholder, width = 'w-24',
}: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; width?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id} className="text-[11px] font-bold" style={{ color: T.ink }}>{label}:</label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? 'من قياس'}
        className={`${width} ${inputCls}`}
        style={inputStyle}
        {...(type === 'number' ? { step: 'any' } : {})}
      />
    </span>
  );
}

const STAGE_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'initial', label_ar: 'ابتدائيّة' },
  { key: 'development', label_ar: 'نموّ' },
  { key: 'mid', label_ar: 'منتصف' },
  { key: 'late', label_ar: 'متأخّرة' },
];

const VARIABILITY_OPTIONS: { key: string; label_ar: string }[] = [
  { key: 'unknown', label_ar: 'غير معروف' },
  { key: 'low', label_ar: 'منخفض' },
  { key: 'medium', label_ar: 'متوسّط' },
  { key: 'high', label_ar: 'عالٍ' },
];

const IRRIGATED_OPTIONS: { key: string; label_ar: string }[] = [
  { key: '', label_ar: '— غير محدّد —' },
  { key: 'true', label_ar: 'مرويّ' },
  { key: 'false', label_ar: 'بعليّ' },
];

/**
 * بطاقة المعرفة الزراعيّة الاختصاصيّة (Crop Propagation & Knowledge): تعكس نقاط backend
 * يتيمة (P3) بلا قارئ واجهة: ملاءمة المحاصيل · تركيب حالة المحصول (dry-run) · الإكثار
 * الخضري واختيار الأصل · الأساليب المحسّنة · صمود الجفاف (مفرد/مقارنة) · تقييم مصدر
 * البذار · استراتيجيّة أخذ العيّنات. صدق صارم: الأحكام والنصوص من الخادم تُعرَض حرفيّاً؛
 * الأقسام قابلة للطيّ واستعلاماتها كسولة (لا تُطلَق قبل فتح القسم وتوفّر المدخلات)؛
 * 404 ⇒ «غير مُفعَّلة على هذا الخادم» صادق؛ null ⇒ «—» والغائب يسقط لا يُصفَّر.
 */
export default function CropPropagationCard({ cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<Set<SectionKey>>(new Set());
  const isOpen = (k: SectionKey) => open.has(k);
  const toggle = (k: SectionKey) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });

  // ── ملاءمة المحاصيل ──
  const [csPh, setCsPh] = useState('');
  const [csEc, setCsEc] = useState('');
  const [csRain, setCsRain] = useState('');
  const [csTemp, setCsTemp] = useState('');
  const [csIrrigated, setCsIrrigated] = useState(true);
  const [csCrops, setCsCrops] = useState('');
  const csPhN = parseNum(csPh);
  const csEcN = parseNum(csEc);
  const suitabilityInput = useMemo(() => {
    if (csPhN == null || csEcN == null) return null; // pH/EC إجباريّان خادميّاً (لا تخمين)
    const crops = csCrops.split(',').map((c) => c.trim()).filter(Boolean);
    return {
      ph: csPhN, ec_dsm: csEcN,
      season_rain_mm: parseNum(csRain), temp_mean_c: parseNum(csTemp),
      irrigated: csIrrigated, crops: crops.length > 0 ? crops : null,
    };
  }, [csPhN, csEcN, csRain, csTemp, csIrrigated, csCrops]);
  const suitabilityQ = useCropSuitability(isOpen('suitability') ? suitabilityInput : null);
  const ranked = useMemo(() => rankedCrops(suitabilityQ.data), [suitabilityQ.data]);

  // ── تركيب حالة المحصول (dry-run) ──
  const [cmCrop, setCmCrop] = useState('');
  const [cmStage, setCmStage] = useState('mid');
  const [cmNdvi, setCmNdvi] = useState('');
  const [cmTmin, setCmTmin] = useState('');
  const [cmTmax, setCmTmax] = useState('');
  const [cmEt0, setCmEt0] = useState('');
  const [cmRain, setCmRain] = useState('');
  const cmTminN = parseNum(cmTmin);
  const cmTmaxN = parseNum(cmTmax);
  const cmEt0N = parseNum(cmEt0);
  const composeInput = useMemo(() => {
    if (cmTminN == null || cmTmaxN == null || cmEt0N == null) return null; // يوم توقّع صحيح إجباريّ
    return {
      crop: (cmCrop.trim() || cropLabel) || null,
      stage: cmStage,
      ndvi: parseNum(cmNdvi),
      forecast: [{ t_min_c: cmTminN, t_max_c: cmTmaxN, et0_mm: cmEt0N, rain_mm: parseNum(cmRain) ?? 0 }],
    };
  }, [cmTminN, cmTmaxN, cmEt0N, cmCrop, cropLabel, cmStage, cmNdvi, cmRain]);
  const composeQ = useCropTwinCompose(isOpen('compose') ? composeInput : null);
  const cmFacts = useMemo(() => composeFacts(composeQ.data), [composeQ.data]);
  const cmFlags = useMemo(() => composeStressFlags(composeQ.data), [composeQ.data]);

  // ── الإكثار الخضري: طرق + دليل + اختيار الأصل ──
  const methodsQ = usePropagationMethods(isOpen('propagation'));
  const methods = useMemo(() => propagationMethods(methodsQ.data), [methodsQ.data]);
  const [pickedMethod, setPickedMethod] = useState<string | null>(null);
  const methodGuideQ = usePropagationMethodGuide(pickedMethod, isOpen('propagation'));
  const guideTypes = useMemo(() => methodGuideTypes(methodGuideQ.data), [methodGuideQ.data]);
  const [stress, setStress] = useState('salinity');
  const rootstockQ = useRootstockSelection(stress, isOpen('propagation'));
  const stresses = useMemo(() => rootstockStresses(rootstockQ.data), [rootstockQ.data]);

  // ── الأساليب المحسّنة: قائمة + دليل ──
  const practicesQ = usePracticesList(isOpen('practices'));
  const practices = useMemo(() => practicesList(practicesQ.data), [practicesQ.data]);
  const [pickedPractice, setPickedPractice] = useState<string | null>(null);
  const practiceGuideQ = usePracticeGuide(pickedPractice, isOpen('practices'));
  const benefits = useMemo(() => practiceBenefits(practiceGuideQ.data), [practiceGuideQ.data]);

  // ── صمود الجفاف: مفرد + مقارنة ──
  const [drCrop, setDrCrop] = useState('');
  const [drTemp, setDrTemp] = useState('');
  const [drIrr, setDrIrr] = useState(''); // '' | 'true' | 'false'
  const drTempN = parseNum(drTemp);
  const drIrrB = drIrr === '' ? null : drIrr === 'true';
  const droughtQ = useDroughtResilience(
    isOpen('drought') ? (drCrop.trim() || cropLabel || null) : null, drTempN, drIrrB,
  );
  const drComponents = useMemo(() => droughtComponentFacts(droughtQ.data), [droughtQ.data]);
  const [cmpCrops, setCmpCrops] = useState('');
  const compareQ = useCompareDroughtResilience(
    isOpen('drought') && cmpCrops.trim() ? cmpCrops.trim() : null, drTempN, drIrrB,
  );
  const compared = useMemo(() => comparedCrops(compareQ.data), [compareQ.data]);

  // ── تقييم مصدر البذار ──
  const [seedCertified, setSeedCertified] = useState(false);
  const [seedPurity, setSeedPurity] = useState('');
  const [seedGerm, setSeedGerm] = useState('');
  const [seedSubmitted, setSeedSubmitted] = useState(false);
  const seedInput = useMemo(() => {
    if (!seedSubmitted) return null; // لا تقييم قبل طلب المستخدم (certified منطقيّ لا فراغ له)
    return { certified: seedCertified, purity_pct: parseNum(seedPurity), germination_pct: parseNum(seedGerm) };
  }, [seedSubmitted, seedCertified, seedPurity, seedGerm]);
  const seedQ = useSeedEvaluate(isOpen('seed') ? seedInput : null);
  const seedFlagList = useMemo(() => seedFlags(seedQ.data), [seedQ.data]);

  // ── استراتيجيّة أخذ العيّنات ──
  const [smArea, setSmArea] = useState('');
  const [smHistory, setSmHistory] = useState(false);
  const [smVar, setSmVar] = useState('unknown');
  const [smCrop, setSmCrop] = useState('');
  const smAreaN = parseNum(smArea);
  const samplingQ = useSamplingStrategy(
    { areaHa: smAreaN, hasHistory: smHistory, variability: smVar, crop: smCrop.trim() || cropLabel || null },
    isOpen('sampling'),
  );
  const smFacts = useMemo(() => samplingFacts(samplingQ.data), [samplingQ.data]);
  const smDepths = useMemo(() => samplingDepths(samplingQ.data), [samplingQ.data]);

  if (!enabled) return null;

  const disabledMsg = (d?: boolean) => d
    ? <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على هذا الخادم بعد.</div>
    : null;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="crop-propagation"
      aria-label="المعرفة الزراعيّة الاختصاصيّة"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" /> المعرفة الزراعيّة الاختصاصيّة
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ═══ ملاءمة المحاصيل ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="ملاءمة المحاصيل (ترتيب مرجّح)" open={isOpen('suitability')} onToggle={() => toggle('suitability')} />
          {isOpen('suitability') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="cs-ph" label="الحموضة pH" value={csPh} onChange={setCsPh} type="number" width="w-14" />
                <LabeledInput id="cs-ec" label="الملوحة ECe dS/m" value={csEc} onChange={setCsEc} type="number" width="w-16" />
                <LabeledInput id="cs-rain" label="مطر الموسم مم" value={csRain} onChange={setCsRain} type="number" width="w-16" />
                <LabeledInput id="cs-temp" label="حرارة متوسّطة °م" value={csTemp} onChange={setCsTemp} type="number" width="w-14" />
                <label className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                  <input type="checkbox" checked={csIrrigated} onChange={(e) => setCsIrrigated(e.target.checked)} /> مرويّ
                </label>
              </div>
              <LabeledInput id="cs-crops" label="محاصيل محدّدة (فاصلة)" value={csCrops} onChange={setCsCrops} placeholder="wheat, barley … (اختياريّ)" width="w-56" />
              {csPhN == null || csEcN == null ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل الحموضة والملوحة (إجباريّتان — يحجب الخادم دونهما).</div>
              ) : suitabilityQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ ترتيب الملاءمة…</div>
              ) : suitabilityQ.isError ? (
                <div className="text-[11px]" style={{ color: '#fca5a5' }}>تعذّر الترتيب — تحقّق من المدخلات (قد تكون خارج نطاق مقبول).</div>
              ) : disabledMsg(suitabilityQ.data?.disabled) ?? (suitabilityQ.data ? (
                <div className="flex flex-col gap-1.5">
                  {ranked.map((s) => (
                    <div key={s.crop} className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span className="font-bold" style={{ color: T.ink }}>{s.name_ar ?? s.crop ?? '—'}</span>
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: suitabilityRatingColor(s.rating_ar), border: `1px solid ${T.line}` }}>{s.rating_ar ?? '—'}</span>
                        <span style={{ color: T.faint }}>درجة {fmtNum(s.score, 2)}</span>
                      </div>
                      {(s.reasons_ar ?? []).map((r, i) => <div key={i} className="text-[11px]" style={{ color: T.muted }}>• {r}</div>)}
                    </div>
                  ))}
                  {suitabilityQ.data.note_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{suitabilityQ.data.note_ar}</div>}
                  {suitabilityQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{suitabilityQ.data.disclaimer_ar}</div>}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ تركيب حالة المحصول (dry-run) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Leaf className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="تركيب حالة المحصول (معاينة dry-run)" open={isOpen('compose')} onToggle={() => toggle('compose')} />
          {isOpen('compose') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>معاينة مقروءة لا تُوزَّع للتنفيذ — كلّ القيم موسومة غير معايَرة مع افتراضات صريحة.</div>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="cm-crop" label="المحصول" value={cmCrop} onChange={setCmCrop} placeholder={cropLabel || 'اختياريّ'} width="w-24" />
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="cm-stage" className="text-[11px] font-bold" style={{ color: T.ink }}>المرحلة:</label>
                  <select id="cm-stage" value={cmStage} onChange={(e) => setCmStage(e.target.value)} className={inputCls} style={inputStyle}>
                    {STAGE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="cm-ndvi" label="NDVI" value={cmNdvi} onChange={setCmNdvi} type="number" width="w-14" placeholder="اختياريّ" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px]" style={{ color: T.faint }}>يوم توقّع (إجباريّ):</span>
                <LabeledInput id="cm-tmin" label="حرارة صغرى °م" value={cmTmin} onChange={setCmTmin} type="number" width="w-14" />
                <LabeledInput id="cm-tmax" label="حرارة عظمى °م" value={cmTmax} onChange={setCmTmax} type="number" width="w-14" />
                <LabeledInput id="cm-et0" label="ET₀ مم" value={cmEt0} onChange={setCmEt0} type="number" width="w-14" />
                <LabeledInput id="cm-rain" label="مطر مم" value={cmRain} onChange={setCmRain} type="number" width="w-14" placeholder="0" />
              </div>
              {cmTminN == null || cmTmaxN == null || cmEt0N == null ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل حرارتَي اليوم وET₀ لتركيب الحالة.</div>
              ) : composeQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تركيب حالة المحصول…</div>
              ) : disabledMsg(composeQ.data?.disabled) ?? (composeQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="font-bold" style={{ color: T.ink }}>{composeQ.data.crop ?? '—'}</span>
                    {composeQ.data.crop_known === false && <span style={{ color: '#fdba74' }}>محصول غير مُعرّف (Kc عامّ)</span>}
                    {composeQ.data.quality?.data_quality && (
                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: qualityColor(composeQ.data.quality.data_quality), border: `1px solid ${T.line}` }}>
                        جودة: {composeQ.data.quality.data_quality}
                      </span>
                    )}
                  </div>
                  <FactPills facts={cmFacts} />
                  {composeQ.data.kc_source_ar && <div className="text-[11px]" style={{ color: T.muted }}>مصدر Kc: {composeQ.data.kc_source_ar}</div>}
                  {cmFlags.map((f) => <div key={f.code} className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {f.label_ar ?? f.code}</div>)}
                  {(composeQ.data.quality?.assumptions_ar ?? []).map((a, i) => <div key={i} className="text-[10px]" style={{ color: T.faint }}>— {a}</div>)}
                  {(composeQ.data.warnings_ar ?? []).map((w, i) => <div key={`w${i}`} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {w}</div>)}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ الإكثار الخضري واختيار الأصل ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Scissors className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="الإكثار الخضري + اختيار الأصل" open={isOpen('propagation')} onToggle={() => toggle('propagation')} />
          {isOpen('propagation') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {methodsQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة طرق الإكثار…</div>
              ) : disabledMsg(methodsQ.data?.disabled) ?? (
                <>
                  {methods.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-bold" style={{ color: T.ink }}>الطرق:</span>
                      {methods.map((m) => (
                        <button
                          key={m.method}
                          type="button"
                          onClick={() => setPickedMethod(pickedMethod === m.method ? null : (m.method ?? null))}
                          className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                          style={{
                            border: `1px solid ${pickedMethod === m.method ? '#0c4a6e' : T.line}`,
                            color: pickedMethod === m.method ? '#7dd3fc' : T.muted,
                            background: pickedMethod === m.method ? 'rgba(12,74,110,.25)' : SUB_BG,
                          }}
                        >
                          {m.name_ar ?? m.method}
                        </button>
                      ))}
                    </div>
                  )}
                  {pickedMethod && (
                    methodGuideQ.isLoading ? (
                      <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة دليل الطريقة…</div>
                    ) : serverMessage(methodGuideQ.data) ? (
                      <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(methodGuideQ.data)}</div>
                    ) : methodGuideQ.data?.supported ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        <div className="text-[11px] font-bold" style={{ color: T.ink }}>
                          {methodGuideQ.data.name_ar ?? '—'}
                          {methodGuideQ.data.best_for_ar && <span className="font-normal" style={{ color: T.faint }}> · الأنسب: {methodGuideQ.data.best_for_ar}</span>}
                        </div>
                        {methodGuideQ.data.what_ar && <div className="text-[11px]" style={{ color: T.muted }}>{methodGuideQ.data.what_ar}</div>}
                        {guideTypes.map((tp) => <div key={tp} className="text-[11px]" style={{ color: T.muted }}>• {tp}</div>)}
                        {methodGuideQ.data.tip_ar && <div className="text-[11px]" style={{ color: '#86efac' }}>{methodGuideQ.data.tip_ar}</div>}
                        {methodGuideQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{methodGuideQ.data.disclaimer_ar}</div>}
                      </div>
                    ) : null
                  )}
                  {methodsQ.data?.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{methodsQ.data.principle_ar}</div>}
                  {methodsQ.data?.caution_ar && <div className="text-[10px]" style={{ color: '#fdba74' }}>{methodsQ.data.caution_ar}</div>}
                </>
              )}

              {/* اختيار الأصل حسب الإجهاد */}
              <div className="flex flex-col gap-1.5 pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-bold" style={{ color: T.ink }}>الأصل حسب الإجهاد:</span>
                  {(stresses.length > 0 ? stresses : rootstockQ.data ? [] : []).map((s) => (
                    <button
                      key={s.stress}
                      type="button"
                      onClick={() => setStress(s.stress ?? 'salinity')}
                      className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                      style={{
                        border: `1px solid ${stress === s.stress ? '#14532d' : T.line}`,
                        color: stress === s.stress ? '#86efac' : T.muted,
                        background: stress === s.stress ? 'rgba(20,83,45,.25)' : SUB_BG,
                      }}
                    >
                      {s.label_ar ?? s.stress}
                    </button>
                  ))}
                </div>
                {rootstockQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة إرشاد الأصل…</div>
                ) : disabledMsg(rootstockQ.data?.disabled) ?? (rootstockQ.data ? (
                  <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                    <div className="text-[11px] font-bold" style={{ color: T.ink }}>{rootstockQ.data.stress_ar ?? '—'}</div>
                    {rootstockQ.data.advice_ar && <div className="text-[11px]" style={{ color: T.muted }}>{rootstockQ.data.advice_ar}</div>}
                    {rootstockQ.data.related_ar && <div className="text-[10px]" style={{ color: T.faint }}>{rootstockQ.data.related_ar}</div>}
                    {rootstockQ.data.principle_ar && <div className="text-[10px]" style={{ color: T.faint }}>{rootstockQ.data.principle_ar}</div>}
                    {rootstockQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{rootstockQ.data.disclaimer_ar}</div>}
                  </div>
                ) : null)}
              </div>
            </div>
          )}
        </div>

        {/* ═══ الأساليب الزراعيّة المحسّنة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="الأساليب الزراعيّة المحسّنة" open={isOpen('practices')} onToggle={() => toggle('practices')} />
          {isOpen('practices') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {practicesQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الأساليب…</div>
              ) : disabledMsg(practicesQ.data?.disabled) ?? (
                <>
                  {practices.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {practices.map((p) => (
                        <button
                          key={p.practice}
                          type="button"
                          onClick={() => setPickedPractice(pickedPractice === p.practice ? null : (p.practice ?? null))}
                          className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                          style={{
                            border: `1px solid ${pickedPractice === p.practice ? '#14532d' : T.line}`,
                            color: pickedPractice === p.practice ? '#86efac' : T.muted,
                            background: pickedPractice === p.practice ? 'rgba(20,83,45,.25)' : SUB_BG,
                          }}
                        >
                          {p.name_ar ?? p.practice}
                        </button>
                      ))}
                    </div>
                  )}
                  {pickedPractice && (
                    practiceGuideQ.isLoading ? (
                      <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة الدليل…</div>
                    ) : serverMessage(practiceGuideQ.data) ? (
                      <div className="text-[11px]" style={{ color: T.muted }}>{serverMessage(practiceGuideQ.data)}</div>
                    ) : practiceGuideQ.data?.supported ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        <div className="text-[11px] font-bold" style={{ color: T.ink }}>{practiceGuideQ.data.name_ar ?? '—'}</div>
                        {practiceGuideQ.data.what_ar && <div className="text-[11px]" style={{ color: T.muted }}>{practiceGuideQ.data.what_ar}</div>}
                        {benefits.map((b) => <div key={b} className="text-[11px]" style={{ color: T.muted }}>• {b}</div>)}
                        {practiceGuideQ.data.caution_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>⚠ {practiceGuideQ.data.caution_ar}</div>}
                        {practiceGuideQ.data.yemen_note_ar && <div className="text-[10px]" style={{ color: '#86efac' }}>{practiceGuideQ.data.yemen_note_ar}</div>}
                        {practiceGuideQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{practiceGuideQ.data.disclaimer_ar}</div>}
                      </div>
                    ) : null
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ صمود الجفاف (مفرد + مقارنة) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ThermometerSun className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="صمود الجفاف/الحرارة" open={isOpen('drought')} onToggle={() => toggle('drought')} />
          {isOpen('drought') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="dr-crop" label="المحصول" value={drCrop} onChange={setDrCrop} placeholder={cropLabel || 'wheat / قمح'} width="w-24" />
                <LabeledInput id="dr-temp" label="حرارة عظمى متوقّعة °م" value={drTemp} onChange={setDrTemp} type="number" width="w-16" placeholder="اختياريّ" />
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="dr-irr" className="text-[11px] font-bold" style={{ color: T.ink }}>الريّ:</label>
                  <select id="dr-irr" value={drIrr} onChange={(e) => setDrIrr(e.target.value)} className={inputCls} style={inputStyle}>
                    {IRRIGATED_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
              </div>
              {!drCrop.trim() && !cropLabel ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل محصولاً لقراءة درجة صموده.</div>
              ) : droughtQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة درجة الصمود…</div>
              ) : disabledMsg(droughtQ.data?.disabled) ?? (droughtQ.data ? (
                droughtQ.data.resilience_score == null ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>{droughtQ.data.note_ar ?? 'لا صفات موثّقة لهذا المحصول — لا درجة.'}</div>
                ) : (
                  <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="font-bold" style={{ color: T.ink }}>{droughtQ.data.crop_id ?? '—'}</span>
                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: droughtRiskColor(droughtQ.data.risk_level_ar), border: `1px solid ${T.line}` }}>{droughtQ.data.risk_level_ar ?? '—'}</span>
                      <span style={{ color: T.faint }}>درجة {fmtNum(droughtQ.data.resilience_score, 2)}</span>
                      {droughtQ.data.confidence && <span style={{ color: T.faint }}>ثقة: {droughtQ.data.confidence}</span>}
                    </div>
                    <FactPills facts={drComponents} />
                    {droughtQ.data.heat_warning_ar && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{droughtQ.data.heat_warning_ar}</div>}
                    {droughtQ.data.heat_basis_ar && <div className="text-[10px]" style={{ color: T.faint }}>{droughtQ.data.heat_basis_ar}</div>}
                    {droughtQ.data.heat_irrigation_caveat_ar && <div className="text-[10px]" style={{ color: '#86efac' }}>{droughtQ.data.heat_irrigation_caveat_ar}</div>}
                    {droughtQ.data.source_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{droughtQ.data.source_note_ar}</div>}
                  </div>
                )
              ) : null)}

              {/* مقارنة عدّة محاصيل */}
              <div className="flex flex-col gap-1.5 pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <LabeledInput id="dr-compare" label="قارِن محاصيل (فاصلة)" value={cmpCrops} onChange={setCmpCrops} placeholder="wheat, sorghum, maize" width="w-56" />
                {!cmpCrops.trim() ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>أدخِل محاصيل مفصولة بفواصل لترتيبها بالأصمد.</div>
                ) : compareQ.isLoading ? (
                  <div className="text-[11px]" style={{ color: T.faint }}>جارٍ المقارنة…</div>
                ) : disabledMsg(compareQ.data?.disabled) ?? (compareQ.data ? (
                  <div className="flex flex-col gap-1">
                    {compareQ.data.most_resilient && <div className="text-[11px]" style={{ color: '#86efac' }}>الأصمد: {compareQ.data.most_resilient}</div>}
                    {compared.map((c) => (
                      <div key={c.crop_id} className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
                        <span className="font-semibold" style={{ color: T.ink }}>{c.crop_id}</span>
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: droughtRiskColor(c.risk_level_ar), border: `1px solid ${T.line}` }}>{c.risk_level_ar ?? '—'}</span>
                        <span style={{ color: T.faint }}>درجة {fmtNum(c.resilience_score, 2)}</span>
                      </div>
                    ))}
                    {compareQ.data.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{compareQ.data.note_ar}</div>}
                    {compareQ.data.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{compareQ.data.honesty_note_ar}</div>}
                  </div>
                ) : null)}
              </div>
            </div>
          )}
        </div>

        {/* ═══ تقييم مصدر البذار ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<FlaskConical className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="تقييم مصدر البذار" open={isOpen('seed')} onToggle={() => toggle('seed')} />
          {isOpen('seed') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                  <input type="checkbox" checked={seedCertified} onChange={(e) => { setSeedCertified(e.target.checked); setSeedSubmitted(false); }} /> بذار معتمد
                </label>
                <LabeledInput id="seed-purity" label="النقاوة ٪" value={seedPurity} onChange={(v) => { setSeedPurity(v); setSeedSubmitted(false); }} type="number" width="w-14" placeholder="اختياريّ" />
                <LabeledInput id="seed-germ" label="الإنبات ٪" value={seedGerm} onChange={(v) => { setSeedGerm(v); setSeedSubmitted(false); }} type="number" width="w-14" placeholder="اختياريّ" />
                <button type="button" onClick={() => setSeedSubmitted(true)} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>قيّم المصدر</button>
              </div>
              {!seedSubmitted ? (
                <div className="text-[11px]" style={{ color: T.faint }}>حدّد الاعتماد (والنقاوة/الإنبات إن توفّرا من فحص) ثمّ قيّم.</div>
              ) : seedQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ التقييم…</div>
              ) : disabledMsg(seedQ.data?.disabled) ?? (seedQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: seedAcceptableColor(seedQ.data.acceptable), border: `1px solid ${T.line}` }}>
                      {seedQ.data.acceptable ? 'مقبول' : 'راجِع المصدر'}
                    </span>
                    {seedQ.data.summary_ar && <span style={{ color: T.muted }}>{seedQ.data.summary_ar}</span>}
                  </div>
                  {seedFlagList.map((f, i) => <div key={i} className="text-[11px]" style={{ color: T.muted }}>{f}</div>)}
                  {seedQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{seedQ.data.disclaimer_ar}</div>}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ استراتيجيّة أخذ العيّنات ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Grid3x3 className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="استراتيجيّة أخذ عيّنات التربة" open={isOpen('sampling')} onToggle={() => toggle('sampling')} />
          {isOpen('sampling') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="sm-area" label="المساحة هكتار" value={smArea} onChange={setSmArea} type="number" width="w-16" />
                <label className="inline-flex items-center gap-1 text-[11px] font-bold" style={{ color: T.ink }}>
                  <input type="checkbox" checked={smHistory} onChange={(e) => setSmHistory(e.target.checked)} /> تاريخ معرفة بالحقل
                </label>
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="sm-var" className="text-[11px] font-bold" style={{ color: T.ink }}>التباين:</label>
                  <select id="sm-var" value={smVar} onChange={(e) => setSmVar(e.target.value)} className={inputCls} style={inputStyle}>
                    {VARIABILITY_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="sm-crop" label="المحصول" value={smCrop} onChange={setSmCrop} placeholder={cropLabel || 'اختياريّ (لعمق العيّنة)'} width="w-28" />
              </div>
              {smAreaN == null ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل مساحة الحقل (من قياس) للتوصية بالاستراتيجيّة.</div>
              ) : samplingQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ حساب الاستراتيجيّة…</div>
              ) : disabledMsg(samplingQ.data?.disabled) ?? (samplingQ.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: samplingMethodBadge(samplingQ.data.method).color, border: `1px solid ${T.line}` }}>{samplingMethodBadge(samplingQ.data.method).label_ar}</span>
                    {samplingQ.data.is_estimate && <span style={{ color: T.faint }}>تقديريّ</span>}
                  </div>
                  <FactPills facts={smFacts} />
                  {samplingQ.data.rationale_ar && <div className="text-[11px]" style={{ color: T.muted }}>{samplingQ.data.rationale_ar}</div>}
                  {samplingQ.data.note_ar && <div className="text-[11px]" style={{ color: T.muted }}>{samplingQ.data.note_ar}</div>}
                  {smDepths.length > 0 && (
                    <div className="text-[11px]" style={{ color: T.muted }}>
                      العمق: {smDepths.join(' · ')}
                      {samplingQ.data.depth_advice?.note_ar && <span style={{ color: T.faint }}> — {samplingQ.data.depth_advice.note_ar}</span>}
                    </div>
                  )}
                  {samplingQ.data.calibration_advice_ar && <div className="text-[10px]" style={{ color: T.faint }}>{samplingQ.data.calibration_advice_ar}</div>}
                </div>
              ) : null)}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
