import { useMemo, useState } from 'react';
import {
  Activity, ChevronDown, ChevronLeft, GitBranch, Layers,
  Recycle, ShieldAlert, Sprout, TrendingUp, UserCheck,
} from 'lucide-react';
import {
  useCropRisk, useCropRotation, useDecisionPlaybook, useEscalationAssess,
  useFieldLineage, useKcCompare, useKcSeries, usePersistKc, usePlantSoilFeedback,
  usePlantSoilFeedbackTrend, type FeedbackTrendSeason,
  useSeasonComparison,
} from '../../hooks/useAgroAnalytics';
import {
  betterBadge, buildSeasonMetrics, CROP_RISK_OPTIONS, cropRiskRows, escalationBadge,
  feedbackDirectionBadge, fmtNum, KC_SCENARIO_OPTIONS, kcCompareStages, kcSeriesRows,
  lineageDecisionRows, outcomeCount, parseMeasure, parsePctToFraction, pctFromFraction,
  priorityAr, psfFacts, riskTypeAr, rotationFacts, scoreOutOf100, seasonMetricRows,
  severityBadge, shortDate, trendArrow, WEATHER_SIGNAL_OPTIONS,
} from '../../lib/agroAnalytics';
import type {
  DecisionPlaybookInput, DisplayFact, EscalationAssessInput, SeasonCropInput,
  SoilFeedbackInput,
} from '../../lib/agroAnalytics';
import { T } from '../ds';

interface Props {
  /** الحقل النشط — للأقسام المرتبطة بحقل (سلسلة Kc + النسب). null ⇒ حالة «اختر حقلاً». */
  fieldId?: string | null;
  /** تسمية محصول الحقل — سياق عرض/إدخال افتراضيّ (لا حكم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

// ألوان بطاقات فرعيّة داكنة مطابقة لـWaterHarvestingCard (الطبقة الموازية للثيم الداكن).
const CARD_BG = 'rgba(15,23,42,.35)';
const SUB_BG = 'rgba(2,6,23,.5)';

type SectionKey =
  | 'crop-risk' | 'rotation' | 'playbook' | 'kc' | 'psf'
  | 'season' | 'escalation' | 'lineage';

/** رأس قسم قابل للطيّ — يعرض العنوان والأيقونة وسهم الحالة (RTL: يسار = مفتوح). */
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

/** وسم حقيقة صغير (label: value) — نفس أسلوب WaterHarvestingCard. */
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
        {...(type === 'number' ? { min: '0', step: 'any' } : {})}
      />
    </span>
  );
}

/**
 * بطاقة التحليلات الزراعيّة-البيئيّة (Agro Analytics): تعكس طبقة backend يتيمة (P1)
 * تُكمّل AgroKnowledgeCard — مخاطر المحصول · الدورة الزراعيّة · دليل القرار · سلسلة Kc
 * (لحقل + مقارنة موسمين) · تغذية راجعة نبات-تربة · مقارنة المواسم · تقييم تصعيد · نسب
 * أصل الحقل. صدق صارم: كلّ الأحكام والنصوص من الخادم تُعرَض حرفيّاً (لا يُعاد الحكم)؛
 * الأقسام قابلة للطيّ واستعلاماتها كسولة (لا تُطلَق قبل فتح القسم وتوفّر المدخلات)؛
 * 404 ⇒ حالة «غير مُفعَّل» صادقة؛ الأقسام المرتبطة بحقل تعرض «اختر حقلاً» عند غيابه.
 */
export default function AgroAnalyticsCard({ fieldId, cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<Set<SectionKey>>(new Set());
  const isOpen = (k: SectionKey) => open.has(k);
  const toggle = (k: SectionKey) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });

  // محصول افتراضيّ من علامة الحقل إن طابق ملفّاً معروفاً في crop_risk (وإلّا فارغ).
  const defaultCrop = useMemo(() => {
    const hit = CROP_RISK_OPTIONS.find((o) => o.key === cropLabel);
    return hit ? hit.key : '';
  }, [cropLabel]);

  // ── حالة قسم مخاطر المحصول ──
  const [crCrop, setCrCrop] = useState('');
  const [crDisease, setCrDisease] = useState(''); // ٪ ⇒ كسر
  const [crHeat, setCrHeat] = useState('');
  const [crFrost, setCrFrost] = useState('');
  const [crHumidity, setCrHumidity] = useState('');
  const crop = crCrop || defaultCrop;
  const cropRiskInput = useMemo(() => {
    if (!crop) return null;
    return {
      crop,
      // عتبات الخادم افتراضها 0؛ الفارغ يُرسَل 0 (موثَّق في CropRiskRequest) — لا اختراع.
      disease_risk_score: parsePctToFraction(crDisease) ?? 0,
      heat_stress_hours: parseMeasure(crHeat) ?? 0,
      frost_risk_hours: parseMeasure(crFrost) ?? 0,
      humidity_avg_percent: parseMeasure(crHumidity), // اختياريّ ⇒ null إن فارغ
    };
  }, [crop, crDisease, crHeat, crFrost, crHumidity]);
  const cropRiskQ = useCropRisk(isOpen('crop-risk') && crop ? cropRiskInput : null);
  const risks = useMemo(() => cropRiskRows(cropRiskQ.data), [cropRiskQ.data]);

  // ── حالة قسم الدورة الزراعيّة (بناء تاريخ مواسم) ──
  const [seasons, setSeasons] = useState<SeasonCropInput[]>([]);
  const [rsSeason, setRsSeason] = useState('');
  const [rsCrop, setRsCrop] = useState('');
  const [rsFamily, setRsFamily] = useState('');
  const [rsLegume, setRsLegume] = useState(false);
  const [rsCover, setRsCover] = useState(false);
  const addSeason = () => {
    if (!rsSeason.trim() || !rsCrop.trim()) return;
    setSeasons((prev) => [...prev, {
      season_id: rsSeason.trim(), crop_id: rsCrop.trim(),
      crop_family: rsFamily.trim() || null, is_legume: rsLegume, is_cover_crop: rsCover,
    }]);
    setRsSeason(''); setRsCrop(''); setRsFamily(''); setRsLegume(false); setRsCover(false);
  };
  const rotationQ = useCropRotation(isOpen('rotation') && seasons.length > 0 ? seasons : null);
  const rotFacts = useMemo(() => rotationFacts(rotationQ.data), [rotationQ.data]);

  // ── حالة قسم دليل القرار ──
  const [pbCrop, setPbCrop] = useState('');
  const [pbSignals, setPbSignals] = useState<Set<string>>(new Set());
  const [pbRec, setPbRec] = useState('');
  const playbookInput = useMemo<DecisionPlaybookInput | null>(() => {
    if (pbSignals.size === 0) return null; // بلا إشارة ⇒ لا سؤال (تجنّب استدعاء فارغ)
    return {
      crop: (pbCrop || defaultCrop) || null,
      weather_signals: [...pbSignals].map((s) => ({ signal_type: s, confidence_score: 0.9 })),
      recommendation_ar: pbRec.trim() || null,
    };
  }, [pbCrop, defaultCrop, pbSignals, pbRec]);
  const playbookQ = useDecisionPlaybook(isOpen('playbook') ? playbookInput : null);
  const pb = playbookQ.data;

  // ── حالة قسم Kc (لحقل + مقارنة موسمين) ──
  const [kcCropId, setKcCropId] = useState('');
  const [kcScenario, setKcScenario] = useState('potential');
  const [kcCur, setKcCur] = useState('');
  const [kcPrev, setKcPrev] = useState('');
  const kcSeriesQ = useKcSeries(
    isOpen('kc') ? (fieldId ?? null) : null, kcCropId || null, kcScenario || null,
  );
  const kcCompareQ = useKcCompare(
    isOpen('kc') ? (fieldId ?? null) : null, kcCropId || null,
    kcCur || null, kcPrev || null, kcScenario,
  );
  const kcRows = useMemo(() => kcSeriesRows(kcSeriesQ.data), [kcSeriesQ.data]);
  const kcStages = useMemo(() => kcCompareStages(kcCompareQ.data), [kcCompareQ.data]);

  // ── حفظ Kc موسم (upsert) — كتابة مدير (IRRIGATION_MANAGE خادميّاً). كانت نقطة
  // الكتابة الوحيدة في هذه المجموعة بلا واجهة؛ القيم الفارغة تُرسَل null (لا اختلاق).
  const [kcSaveSeason, setKcSaveSeason] = useState('');
  const [kcSaveIni, setKcSaveIni] = useState('');
  const [kcSaveMid, setKcSaveMid] = useState('');
  const [kcSaveEnd, setKcSaveEnd] = useState('');
  const persistKc = usePersistKc();
  const kcSaveReady = !!fieldId && !!kcCropId.trim() && !!kcSaveSeason.trim();
  const onPersistKc = () => {
    if (!kcSaveReady || !fieldId) return;
    persistKc.mutate({
      field_id: fieldId,
      crop_id: kcCropId.trim(),
      season_id: kcSaveSeason.trim(),
      scenario_type: kcScenario,
      kc_ini: parseMeasure(kcSaveIni),
      kc_mid: parseMeasure(kcSaveMid),
      kc_end: parseMeasure(kcSaveEnd),
    });
  };

  // ── حالة قسم التغذية الراجعة نبات-تربة (مؤشّرات proxy — كلّها اختياريّة) ──
  const [psfRot, setPsfRot] = useState('');
  const [psfLeg, setPsfLeg] = useState('');
  const [psfCover, setPsfCover] = useState('');
  const [psfHost, setPsfHost] = useState('');
  const [psfSoc, setPsfSoc] = useState('');
  const [psfSal, setPsfSal] = useState('');
  const psfInput = useMemo<SoilFeedbackInput>(() => ({
    // كسور [0,1] عبر إدخال ٪ (كما يفكّر المزارع)؛ SOC/الملوحة قياسات مطلقة كما يتوقّعها الخادم.
    rotation_diversity: parsePctToFraction(psfRot),
    legume_ratio: parsePctToFraction(psfLeg),
    cover_crop_ratio: parsePctToFraction(psfCover),
    host_repeat_risk: parsePctToFraction(psfHost),
    soil_organic_carbon_pct: parseMeasure(psfSoc),
    salinity_ds_m: parseMeasure(psfSal),
  }), [psfRot, psfLeg, psfCover, psfHost, psfSoc, psfSal]);
  const psfQ = usePlantSoilFeedback(isOpen('psf') ? psfInput : null);
  const psf = psfQ.data;
  const psfFactsList = useMemo(() => psfFacts(psf), [psf]);

  // ── اتّجاه متعدّد المواسم: لقطات المؤشّرات الحاليّة تُضاف لسلسلة زمنيّة ──
  // (الأقدم→الأحدث)؛ POST plant-soil-feedback/trend يشتقّ الاتّجاه (يحتاج موسمين+).
  const [trendSeasonId, setTrendSeasonId] = useState('');
  const [trendSeasons, setTrendSeasons] = useState<FeedbackTrendSeason[]>([]);
  const trendM = usePlantSoilFeedbackTrend();
  const addTrendSeason = () => {
    if (!trendSeasonId.trim()) return;
    setTrendSeasons((s) => [...s, { season_id: trendSeasonId.trim(), inputs: psfInput }]);
    setTrendSeasonId('');
    trendM.reset();
  };

  // ── حالة قسم مقارنة المواسم ──
  const [scCurId, setScCurId] = useState('');
  const [scPrevId, setScPrevId] = useState('');
  const [scCropId, setScCropId] = useState('');
  const [scCurYield, setScCurYield] = useState('');
  const [scPrevYield, setScPrevYield] = useState('');
  const [scCurWater, setScCurWater] = useState('');
  const [scPrevWater, setScPrevWater] = useState('');
  const seasonReady = !!scCurId.trim() && !!scPrevId.trim() && !!scCropId.trim();
  const scCurrent = seasonReady
    ? buildSeasonMetrics(scCurId.trim(), scCropId.trim(), { yield_t_ha: scCurYield, water_used_m3: scCurWater })
    : null;
  const scPrevious = seasonReady
    ? buildSeasonMetrics(scPrevId.trim(), scCropId.trim(), { yield_t_ha: scPrevYield, water_used_m3: scPrevWater })
    : null;
  const seasonQ = useSeasonComparison(
    isOpen('season') ? scCurrent : null, isOpen('season') ? scPrevious : null,
  );
  const seasonRows = useMemo(() => seasonMetricRows(seasonQ.data), [seasonQ.data]);

  // ── حالة قسم تقييم التصعيد ──
  const [escSource, setEscSource] = useState('rag');
  const [escConf, setEscConf] = useState(''); // ٪ ⇒ كسر
  const [escHasAnswer, setEscHasAnswer] = useState(true);
  const [escPoints, setEscPoints] = useState('');
  const escInput = useMemo<EscalationAssessInput>(() => ({
    source: escSource.trim() || 'rag',
    confidence: parsePctToFraction(escConf), // فارغ ⇒ null ⇒ BLOCKED من الخادم (لا تأليف)
    has_answer: escHasAnswer,
    uncertain_points: escPoints.split('\n').map((s) => s.trim()).filter(Boolean),
  }), [escSource, escConf, escHasAnswer, escPoints]);
  const escQ = useEscalationAssess(isOpen('escalation') ? escInput : null);
  const esc = escQ.data;

  // ── حالة قسم نسب أصل الحقل ──
  const lineageQ = useFieldLineage(isOpen('lineage') ? (fieldId ?? null) : null);
  const lineageRows = useMemo(() => lineageDecisionRows(lineageQ.data), [lineageQ.data]);

  if (!enabled) return null;

  const noField = <div className="text-[11px]" style={{ color: T.faint }}>اختر حقلاً لعرض هذا القسم.</div>;
  const disabledMsg = (d?: boolean) => d
    ? <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على الخادم بعد.</div>
    : null;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="agro-analytics"
      aria-label="التحليلات الزراعيّة-البيئيّة"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" /> التحليلات الزراعيّة-البيئيّة
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ═══ مخاطر المحصول ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ShieldAlert className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="مخاطر المحصول" open={isOpen('crop-risk')} onToggle={() => toggle('crop-risk')} />
          {isOpen('crop-risk') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="cr-crop" className="text-[11px] font-bold" style={{ color: T.ink }}>المحصول:</label>
                  <select id="cr-crop" value={crop} onChange={(e) => setCrCrop(e.target.value)} className={inputCls} style={inputStyle}>
                    <option value="">— اختر —</option>
                    {CROP_RISK_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="cr-disease" label="خطر المرض ٪" value={crDisease} onChange={setCrDisease} type="number" width="w-16" />
                <LabeledInput id="cr-heat" label="ساعات حرّ" value={crHeat} onChange={setCrHeat} type="number" width="w-14" />
                <LabeledInput id="cr-frost" label="ساعات صقيع" value={crFrost} onChange={setCrFrost} type="number" width="w-14" />
                <LabeledInput id="cr-hum" label="رطوبة ٪" value={crHumidity} onChange={setCrHumidity} type="number" width="w-14" />
              </div>
              {!crop ? (
                <div className="text-[11px]" style={{ color: T.faint }}>اختر المحصول ثمّ أدخِل إشارات الطقس (من قياس/تراكب).</div>
              ) : cropRiskQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم المخاطر…</div>
              ) : disabledMsg(cropRiskQ.data?.disabled) ?? (
                risks.length > 0 ? (
                  <div className="flex flex-col gap-1">
                    {risks.map((r, i) => {
                      const sev = severityBadge(r.severity);
                      return (
                        <div key={`${r.risk_type}-${i}`} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                          <div className="flex items-center gap-2 text-[11px]">
                            <span className="font-bold" style={{ color: T.ink }}>{riskTypeAr(r.risk_type)}</span>
                            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: sev.color, border: `1px solid ${T.line}` }}>{sev.label_ar}</span>
                            <span style={{ color: T.faint }}>درجة {pctFromFraction(r.score)}</span>
                          </div>
                          {r.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{r.reason_ar}</div>}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-[11px]" style={{ color: T.muted }}>لا مخاطر مُحفَّزة عند هذه الإشارات (طقس حميد).</div>
                )
              )}
            </div>
          )}
        </div>

        {/* ═══ الدورة الزراعيّة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Recycle className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="دورة زراعيّة" open={isOpen('rotation')} onToggle={() => toggle('rotation')} />
          {isOpen('rotation') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="rs-season" label="الموسم" value={rsSeason} onChange={setRsSeason} placeholder="2026-ربيع" width="w-24" />
                <LabeledInput id="rs-crop" label="المحصول" value={rsCrop} onChange={setRsCrop} placeholder="wheat" width="w-20" />
                <LabeledInput id="rs-family" label="العائلة" value={rsFamily} onChange={setRsFamily} placeholder="اختياريّ" width="w-20" />
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={rsLegume} onChange={(e) => setRsLegume(e.target.checked)} /> بقوليّ
                </label>
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={rsCover} onChange={(e) => setRsCover(e.target.checked)} /> غطاء
                </label>
                <button type="button" onClick={addSeason} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف موسماً</button>
              </div>
              {seasons.length === 0 ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أضِف مواسم التاريخ (الأقدم → الأحدث) لتقييم جودة التناوب.</div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {seasons.map((s, i) => (
                      <span key={`${s.season_id}-${i}`} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                        {s.season_id}: {s.crop_id}{s.is_legume ? ' · بقوليّ' : ''}{s.is_cover_crop ? ' · غطاء' : ''}
                      </span>
                    ))}
                    <button type="button" onClick={() => setSeasons([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                  </div>
                  {rotationQ.isLoading ? (
                    <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم التناوب…</div>
                  ) : disabledMsg(rotationQ.data?.disabled) ?? (
                    <>
                      {rotationQ.data?.direction && (
                        <div className="text-[11px]">
                          <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: feedbackDirectionBadge(rotationQ.data.direction).color, border: `1px solid ${T.line}` }}>
                            تغذية راجعة {feedbackDirectionBadge(rotationQ.data.direction).label_ar}
                          </span>
                        </div>
                      )}
                      <FactPills facts={rotFacts} />
                      {(rotationQ.data?.evidence_ar ?? []).map((e, i) => (
                        <div key={i} className="text-[11px]" style={{ color: T.muted }}>• {e}</div>
                      ))}
                      {rotationQ.data?.verdict_ar && <div className="text-[11px] font-semibold" style={{ color: T.ink }}>{rotationQ.data.verdict_ar}</div>}
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ دليل القرار (playbook) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="دليل قرارات" open={isOpen('playbook')} onToggle={() => toggle('playbook')} />
          {isOpen('playbook') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-1.5">
                {WEATHER_SIGNAL_OPTIONS.map((o) => {
                  const on = pbSignals.has(o.key);
                  return (
                    <button
                      key={o.key}
                      type="button"
                      onClick={() => setPbSignals((prev) => { const n = new Set(prev); if (n.has(o.key)) n.delete(o.key); else n.add(o.key); return n; })}
                      className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                      style={{ border: `1px solid ${on ? '#14532d' : T.line}`, color: on ? '#86efac' : T.muted, background: on ? 'rgba(20,83,45,.25)' : SUB_BG }}
                    >
                      {o.label_ar}
                    </button>
                  );
                })}
              </div>
              <LabeledInput id="pb-rec" label="توصية علويّة" value={pbRec} onChange={setPbRec} placeholder="اختياريّ" width="w-48" />
              {pbSignals.size === 0 ? (
                <div className="text-[11px]" style={{ color: T.faint }}>اختر إشارة طقس واحدة على الأقلّ لبناء دليل القرار.</div>
              ) : playbookQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ بناء دليل القرار…</div>
              ) : disabledMsg(playbookQ.data?.disabled) ?? (pb ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>{pb.main_judgement ?? '—'}</div>
                  <div className="text-[10px]" style={{ color: T.faint }}>الثقة: {pctFromFraction(pb.confidence)} · المراجعة: {pb.review_after ?? '—'}</div>
                  {(pb.do_today ?? []).map((x, i) => <div key={`d${i}`} className="text-[11px]" style={{ color: '#86efac' }}>افعل اليوم: {x}</div>)}
                  {(pb.avoid_now ?? []).map((x, i) => <div key={`a${i}`} className="text-[11px]" style={{ color: '#fdba74' }}>تجنّب الآن: {x}</div>)}
                  {(pb.escalate_if ?? []).map((x, i) => <div key={`e${i}`} className="text-[11px]" style={{ color: '#fca5a5' }}>صعّد إن: {x}</div>)}
                  {(pb.evidence ?? []).map((x, i) => <div key={`ev${i}`} className="text-[10px]" style={{ color: T.muted }}>— {x}</div>)}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ سلسلة Kc (لحقل + مقارنة موسمين) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Activity className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="سلسلة Kc" open={isOpen('kc')} onToggle={() => toggle('kc')} />
          {isOpen('kc') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {!fieldId ? noField : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <LabeledInput id="kc-crop" label="المحصول" value={kcCropId} onChange={setKcCropId} placeholder="اختياريّ للتصفية" width="w-24" />
                    <span className="inline-flex items-center gap-1">
                      <label htmlFor="kc-scen" className="text-[11px] font-bold" style={{ color: T.ink }}>السيناريو:</label>
                      <select id="kc-scen" value={kcScenario} onChange={(e) => setKcScenario(e.target.value)} className={inputCls} style={inputStyle}>
                        {KC_SCENARIO_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                      </select>
                    </span>
                  </div>
                  {/* السلسلة التاريخيّة */}
                  {kcSeriesQ.isLoading ? (
                    <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة سلسلة Kc…</div>
                  ) : disabledMsg(kcSeriesQ.data?.disabled) ?? (
                    kcRows.length > 0 ? (
                      <div className="flex flex-col gap-1">
                        {kcRows.map((r, i) => (
                          <span key={`${r.season_id}-${i}`} className="text-[11px] px-2 py-0.5 rounded-lg" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                            <span style={{ color: T.faint }}>{r.season_id} · {r.crop_id}:</span> ini {fmtNum(r.kc_ini, 2)} · mid {fmtNum(r.kc_mid, 2)} · end {fmtNum(r.kc_end, 2)}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[11px]" style={{ color: T.muted }}>لا سلسلة Kc مُخزَّنة لهذا الحقل بعد.</div>
                    )
                  )}
                  {/* مقارنة موسمين (لنفس الحقل/المحصول — الشكل يقارن موسمين لا حقلين) */}
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <span className="text-[11px] font-bold" style={{ color: T.ink }}>مقارنة موسمين:</span>
                    <LabeledInput id="kc-cur" label="الحاليّ" value={kcCur} onChange={setKcCur} placeholder="2026" width="w-20" />
                    <LabeledInput id="kc-prev" label="السابق" value={kcPrev} onChange={setKcPrev} placeholder="2025" width="w-20" />
                  </div>
                  {!kcCropId || !kcCur || !kcPrev ? (
                    <div className="text-[11px]" style={{ color: T.faint }}>أدخِل المحصول والموسمين للمقارنة.</div>
                  ) : kcCompareQ.isLoading ? (
                    <div className="text-[11px]" style={{ color: T.faint }}>جارٍ مقارنة الموسمين…</div>
                  ) : disabledMsg(kcCompareQ.data?.disabled) ?? (
                    kcStages.length > 0 ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        {kcStages.map((s) => (
                          <div key={s.stage} className="text-[11px]" style={{ color: T.muted }}>
                            <span className="font-semibold" style={{ color: T.ink }}>{s.stage}</span>: {fmtNum(s.previous, 2)} → {fmtNum(s.current, 2)} {trendArrow(s.direction)} (Δ {fmtNum(s.delta, 3)})
                          </div>
                        ))}
                        {kcCompareQ.data?.verdict_ar && <div className="text-[11px] font-semibold" style={{ color: T.ink }}>{kcCompareQ.data.verdict_ar}</div>}
                      </div>
                    ) : null
                  )}

                  {/* حفظ Kc المُشتقّ لموسم (upsert) — يتطلّب صلاحيّة إدارة الريّ خادميّاً؛
                      403 لغير المخوّل تُعرَض كما هي. الحقول الفارغة تُحفَظ NULL بصدق. */}
                  <div className="flex flex-wrap items-center gap-2 pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                    <span className="text-[11px] font-bold" style={{ color: T.ink }}>حفظ Kc لموسم:</span>
                    <LabeledInput id="kc-save-season" label="الموسم" value={kcSaveSeason} onChange={setKcSaveSeason} width="w-24" />
                    <LabeledInput id="kc-save-ini" label="Kc ini" value={kcSaveIni} onChange={setKcSaveIni} type="number" width="w-16" />
                    <LabeledInput id="kc-save-mid" label="Kc mid" value={kcSaveMid} onChange={setKcSaveMid} type="number" width="w-16" />
                    <LabeledInput id="kc-save-end" label="Kc end" value={kcSaveEnd} onChange={setKcSaveEnd} type="number" width="w-16" />
                    <button
                      type="button"
                      onClick={onPersistKc}
                      disabled={!kcSaveReady || persistKc.isPending}
                      className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40"
                      style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(15,23,42,.45)' }}
                    >
                      {persistKc.isPending ? '…' : 'احفظ'}
                    </button>
                    {persistKc.isSuccess && (
                      <span className="text-[11px]" role="status" style={{ color: '#86efac' }}>
                        حُفظ (kc_id: {persistKc.data?.kc_id ?? '—'})
                      </span>
                    )}
                    {persistKc.isError && (
                      <span className="text-[11px]" role="status" style={{ color: '#fca5a5' }}>
                        تعذّر الحفظ — قد يتطلّب صلاحيّة إدارة الريّ
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ تغذية راجعة نبات-تربة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Sprout className="w-4 h-4 text-lime-300" aria-hidden="true" />} title="تغذية راجعة نبات-تربة" open={isOpen('psf')} onToggle={() => toggle('psf')} />
          {isOpen('psf') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="psf-rot" label="تنوّع الدورة ٪" value={psfRot} onChange={setPsfRot} type="number" width="w-14" />
                <LabeledInput id="psf-leg" label="بقوليّات ٪" value={psfLeg} onChange={setPsfLeg} type="number" width="w-14" />
                <LabeledInput id="psf-cov" label="غطاء ٪" value={psfCover} onChange={setPsfCover} type="number" width="w-14" />
                <LabeledInput id="psf-host" label="تكرار العائل ٪" value={psfHost} onChange={setPsfHost} type="number" width="w-14" />
                <LabeledInput id="psf-soc" label="SOC ٪" value={psfSoc} onChange={setPsfSoc} type="number" width="w-14" />
                <LabeledInput id="psf-sal" label="ملوحة dS/m" value={psfSal} onChange={setPsfSal} type="number" width="w-14" />
              </div>
              {psfInput && Object.values(psfInput).every((v) => v == null) ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل مؤشّراً واحداً على الأقلّ (الغائب لا يُعامَل صفراً).</div>
              ) : psfQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقدير التغذية الراجعة…</div>
              ) : disabledMsg(psfQ.data?.disabled) ?? (psf ? (
                <>
                  {psf.direction && (
                    <span className="w-fit px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: feedbackDirectionBadge(psf.direction).color, border: `1px solid ${T.line}` }}>
                      اتّجاه {feedbackDirectionBadge(psf.direction).label_ar}
                    </span>
                  )}
                  <FactPills facts={psfFactsList} />
                  {(psf.drivers_positive_ar ?? []).map((d, i) => <div key={`p${i}`} className="text-[11px]" style={{ color: '#86efac' }}>+ {d}</div>)}
                  {(psf.drivers_negative_ar ?? []).map((d, i) => <div key={`n${i}`} className="text-[11px]" style={{ color: '#fca5a5' }}>− {d}</div>)}
                  {psf.verdict_ar && <div className="text-[11px] font-semibold" style={{ color: T.ink }}>{psf.verdict_ar}</div>}
                </>
              ) : null)}

              {/* اتّجاه متعدّد المواسم — يلتقط المؤشّرات الحاليّة كموسم في السلسلة */}
              <div className="flex flex-wrap items-center gap-2 pt-1" style={{ borderTop: `1px dashed ${T.line}` }}>
                <span className="text-[11px] font-bold" style={{ color: T.ink }}>اتّجاه المواسم:</span>
                <LabeledInput id="psf-trend-season" label="مُعرّف الموسم" value={trendSeasonId} onChange={setTrendSeasonId} width="w-24" />
                <button type="button" onClick={addTrendSeason} disabled={!trendSeasonId.trim()}
                  className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40"
                  style={{ border: `1px solid ${T.line}`, color: T.ink, background: 'rgba(15,23,42,.45)' }}>
                  + أضِف الموسم الحاليّ
                </button>
                {trendSeasons.length > 0 && (
                  <>
                    <span className="text-[11px]" style={{ color: T.muted }}>{trendSeasons.map((s) => s.season_id).join(' → ')}</span>
                    <button type="button" onClick={() => setTrendSeasons([])} className="text-[11px]" style={{ color: '#fca5a5' }}>مسح</button>
                    <button type="button" onClick={() => trendM.mutate(trendSeasons)} disabled={trendSeasons.length < 2 || trendM.isPending}
                      className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40"
                      style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
                      {trendM.isPending ? '…' : 'احسب الاتّجاه'}
                    </button>
                  </>
                )}
                {trendSeasons.length === 1 && (
                  <span className="text-[11px]" style={{ color: T.faint }}>يلزم موسمان على الأقلّ لاشتقاق اتّجاه.</span>
                )}
              </div>
              {trendM.data && !trendM.data.disabled && (
                <div className="flex flex-col gap-0.5">
                  {trendM.data.direction && (
                    <span className="w-fit px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: feedbackDirectionBadge(trendM.data.direction).color, border: `1px solid ${T.line}` }}>
                      اتّجاه {feedbackDirectionBadge(trendM.data.direction).label_ar}
                      {trendM.data.net_delta != null ? ` · Δ${fmtNum(trendM.data.net_delta, 2)}` : ''}
                    </span>
                  )}
                  {(trendM.data.drivers_ar ?? []).map((d, i) => <div key={`t${i}`} className="text-[11px]" style={{ color: T.muted }}>· {d}</div>)}
                  {trendM.data.verdict_ar && <div className="text-[11px] font-semibold" style={{ color: T.ink }}>{trendM.data.verdict_ar}</div>}
                </div>
              )}
              {trendM.data?.disabled && <div className="text-[11px]" style={{ color: T.muted }}>تحليل الاتّجاه غير مُفعَّل على هذا الخادم.</div>}
            </div>
          )}
        </div>

        {/* ═══ مقارنة المواسم ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<TrendingUp className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="مقارنة المواسم" open={isOpen('season')} onToggle={() => toggle('season')} />
          {isOpen('season') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="sc-crop" label="المحصول" value={scCropId} onChange={setScCropId} placeholder="wheat" width="w-20" />
                <LabeledInput id="sc-cur" label="الموسم الحاليّ" value={scCurId} onChange={setScCurId} placeholder="2026" width="w-16" />
                <LabeledInput id="sc-prev" label="السابق" value={scPrevId} onChange={setScPrevId} placeholder="2025" width="w-16" />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="sc-cy" label="غلّة حاليّة" value={scCurYield} onChange={setScCurYield} type="number" width="w-14" />
                <LabeledInput id="sc-py" label="غلّة سابقة" value={scPrevYield} onChange={setScPrevYield} type="number" width="w-14" />
                <LabeledInput id="sc-cw" label="ماء حاليّ" value={scCurWater} onChange={setScCurWater} type="number" width="w-14" />
                <LabeledInput id="sc-pw" label="ماء سابق" value={scPrevWater} onChange={setScPrevWater} type="number" width="w-14" />
              </div>
              {!seasonReady ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل المحصول ومعرّفَي الموسمين، ثمّ المقاييس المتاحة (الناقص يُتجاهَل).</div>
              ) : seasonQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ مقارنة المواسم…</div>
              ) : disabledMsg(seasonQ.data?.disabled) ?? (
                <>
                  {seasonRows.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      {seasonRows.map((m) => {
                        const bb = betterBadge(m.better);
                        return (
                          <div key={m.metric} className="text-[11px]" style={{ color: T.muted }}>
                            <span className="font-semibold" style={{ color: T.ink }}>{m.label_ar}</span>: {fmtNum(m.previous, 2)} → {fmtNum(m.current, 2)} {trendArrow(m.direction)}
                            {m.percent_change != null && <span style={{ color: T.faint }}> ({fmtNum(m.percent_change, 1)}٪)</span>}
                            {m.better != null && <span className="px-1 rounded" style={{ color: bb.color }}> {bb.label_ar}</span>}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-[11px]" style={{ color: T.muted }}>لا مقاييس متوفّرة على الجانبين للمقارنة.</div>
                  )}
                  {(seasonQ.data?.skipped_metrics ?? []).length > 0 && (
                    <div className="text-[10px]" style={{ color: T.faint }}>مقاييس مُتجاهَلة (ناقصة على جانب): {(seasonQ.data?.skipped_metrics ?? []).join('، ')}</div>
                  )}
                  {seasonQ.data?.verdict_ar && <div className="text-[11px] font-semibold" style={{ color: T.ink }}>{seasonQ.data.verdict_ar}</div>}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ تقييم تصعيد ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<UserCheck className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="تقييم تصعيد" open={isOpen('escalation')} onToggle={() => toggle('escalation')} />
          {isOpen('escalation') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="esc-src" label="المصدر" value={escSource} onChange={setEscSource} placeholder="rag / engine" width="w-24" />
                <LabeledInput id="esc-conf" label="الثقة ٪" value={escConf} onChange={setEscConf} type="number" width="w-14" />
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={escHasAnswer} onChange={(e) => setEscHasAnswer(e.target.checked)} /> توجد إجابة/سند
                </label>
              </div>
              <textarea
                value={escPoints}
                onChange={(e) => setEscPoints(e.target.value)}
                placeholder="نقاط المجهول (سطر لكلّ نقطة) — اختياريّ"
                rows={2}
                className="w-full px-2 py-1 rounded-lg text-[11px]"
                style={inputStyle}
              />
              {escQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ تقييم التصعيد…</div>
              ) : disabledMsg(escQ.data?.disabled) ?? (esc ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: escalationBadge(esc.level).color, border: `1px solid ${T.line}` }}>{escalationBadge(esc.level).label_ar}</span>
                    <span style={{ color: T.faint }}>الأولويّة: {priorityAr(esc.priority)}</span>
                    {esc.recipient_role_ar && <span style={{ color: T.muted }}>المستلِم: {esc.recipient_role_ar}</span>}
                  </div>
                  {esc.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{esc.reason_ar}</div>}
                  {(esc.uncertain_points_ar ?? []).map((p, i) => <div key={i} className="text-[10px]" style={{ color: T.faint }}>• {p}</div>)}
                  {esc.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{esc.honesty_note_ar}</div>}
                </div>
              ) : null)}
            </div>
          )}
        </div>

        {/* ═══ نسب أصل الحقل (lineage) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<GitBranch className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="نسب أصل الحقل" open={isOpen('lineage')} onToggle={() => toggle('lineage')} />
          {isOpen('lineage') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {!fieldId ? noField : lineageQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة نسب الحقل…</div>
              ) : disabledMsg(lineageQ.data?.disabled) ?? (
                <>
                  {lineageRows.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      {lineageRows.map((d, i) => (
                        <div key={d.decision_id ?? i} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <span className="font-bold" style={{ color: T.ink }}>{d.decision_type ?? '—'}</span>
                            {d.stage && <span style={{ color: T.faint }}>مرحلة: {d.stage}</span>}
                            <span style={{ color: T.faint }}>{shortDate(d.created_at)}</span>
                            <span style={{ color: T.muted }}>نتائج مربوطة: {outcomeCount(d)}</span>
                            {d.confidence != null && <span style={{ color: T.faint }}>ثقة {pctFromFraction(d.confidence)}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px]" style={{ color: T.muted }}>لا قرارات مُدامة لهذا الحقل بعد.</div>
                  )}
                  {(lineageQ.data?.orphan_outcomes ?? []).length > 0 && (
                    <div className="text-[10px]" style={{ color: '#fdba74' }}>نتائج بلا قرار مُدام (تُكشَف لا تُخفى): {(lineageQ.data?.orphan_outcomes ?? []).length}</div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
