import { useMemo, useState } from 'react';
import {
  Activity, BrainCircuit, ChevronDown, ChevronLeft, ClipboardCheck, Gauge,
  GitMerge, Layers, Map as MapIcon, ScrollText, ShieldCheck, SlidersHorizontal,
} from 'lucide-react';
import {
  useActivationStatus, useCalibrationFeedback, useConfidenceGate, useCorroborate,
  useCoverageReport, useExternalPriorBlend, useMapLayers, usePredictionCalibration,
  useRecordObservation, useThresholdSuggestions,
} from '../../hooks/useLearningEvidence';
import {
  activationBadge, activationFacts, biasBadge, blendFacts, blendReady, calibrationFacts,
  coverageEntries, escalationBadge, fmtNum, feedbackActionBadge, gateBadge, mapLayers,
  observationReady, overrideEntries, parseMeasure, pctFromFraction, suggestionBadge,
  thresholdSuggestionRows, tierBadge, ENGINE_OPTIONS, EVIDENCE_LEVEL_OPTIONS,
  EVIDENCE_TYPE_OPTIONS, OBS_CONFIDENCE_OPTIONS, OBS_SOURCE_OPTIONS,
} from '../../lib/learningEvidence';
import type {
  ConfidenceGateInput, CorroborationInput, EngineSignalInput, EvidenceItemInput,
  EvidenceRecordInput, ExternalPriorBlendInput, Fact, ObservationInput,
} from '../../lib/learningEvidence';
import { useTenantId } from '../../hooks/useAuth';
import { T } from '../ds';

interface Props {
  /** الحقل النشط — لسياق المشاهدة (field_id) والتصفية. null ⇒ يبقى المسار عامّاً/يُعطَّل قسم الحقل. */
  fieldId?: string | null;
  /** تسمية محصول الحقل — سياق عرض/إدخال افتراضيّ (لا حكم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

// ألوان بطاقات فرعيّة داكنة مطابقة لـWaterHarvestingCard/AgroAnalyticsCard (الطبقة الداكنة).
const CARD_BG = 'rgba(15,23,42,.35)';
const SUB_BG = 'rgba(2,6,23,.5)';

type SectionKey =
  | 'activation' | 'calibration' | 'blend' | 'policy' | 'feedback'
  | 'corroborate' | 'gate' | 'observation' | 'layers' | 'coverage';

/** رأس قسم قابل للطيّ — العنوان والأيقونة وسهم الحالة (RTL: يسار = مفتوح). */
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

/** وسم حقيقة صغير (label: value) — نفس أسلوب البطاقات المجاورة. */
function FactPills({ facts }: { facts: Fact[] }) {
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

/** وسم قرار/حالة صغير (لون من الخادم، النصّ من الخادم أو التسمية العرضيّة). */
function StatusPill({ label_ar, color }: { label_ar: string; color: string }) {
  return (
    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color, border: `1px solid ${T.line}` }}>
      {label_ar}
    </span>
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

/**
 * بطاقة التعلّم والدليل (Learning & Evidence): تكشف طبقة backend يتيمة (P3، سطح المرشد
 * الزراعيّ) — بوّابة تفعيل التعلّم · معايرة التنبّؤ · مزج سابقة خارجيّة · اقتراح عتبات السياسة
 * · تغذية راجعة المعايرة · تظافر القرائن · بوّابة الثقة · تسجيل مشاهدة (كتابة) · طبقات
 * الخريطة · تغطية المؤشّرات. صدق صارم: كلّ الأحكام والنصوص من الخادم تُعرَض حرفيّاً (لا
 * يُعاد الحكم)؛ أعلام الحوكمة (auto_adjust=false/calibrated=false/can_activate) تُعرَض كما
 * جاءت؛ الأقسام قابلة للطيّ واستعلاماتها كسولة (لا تُطلَق قبل فتح القسم وتوفّر المدخلات)؛
 * 404 ⇒ حالة «غير مُفعَّل» صادقة؛ التسجيل مسار كتابة صريح (نموذج إرسال مع تأكيد op_id).
 */
export default function LearningEvidenceCard({ fieldId, cropLabel, enabled = true }: Props) {
  const tenantId = useTenantId();
  const [open, setOpen] = useState<Set<SectionKey>>(new Set());
  const isOpen = (k: SectionKey) => open.has(k);
  const toggle = (k: SectionKey) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });

  // ── بوّابة تفعيل التعلّم (لا مُدخل — قراءة حالة المستأجِر) ──
  const activationQ = useActivationStatus(isOpen('activation'));
  const actFacts = useMemo(() => activationFacts(activationQ.data), [activationQ.data]);

  // ── معايرة التنبّؤ (crop_id اختياريّ للتصفية؛ افتراضه علامة الحقل) ──
  const [calCrop, setCalCrop] = useState('');
  const calibrationQ = usePredictionCalibration(
    isOpen('calibration') ? (calCrop.trim() || cropLabel || null) : null,
    isOpen('calibration'),
  );
  const calFacts = useMemo(() => calibrationFacts(calibrationQ.data), [calibrationQ.data]);

  // ── مزج سابقة خارجيّة (قيم يُدخِلها المستخدم — لا اختراع) ──
  const [extPrior, setExtPrior] = useState('');
  const [locEst, setLocEst] = useState('');
  const [nLocal, setNLocal] = useState('');
  const [cropInYemen, setCropInYemen] = useState(true);
  const [extCred, setExtCred] = useState('');
  const blendInput = useMemo<ExternalPriorBlendInput>(() => ({
    external_prior: parseMeasure(extPrior),
    local_estimate: parseMeasure(locEst),
    n_local: parseMeasure(nLocal) ?? 0,
    crop_grown_in_yemen: cropInYemen,
    // فارغ ⇒ افتراض الخادم 0.5 (سقف مصداقيّة السابقة الخارجيّة). لا نُرسِل تخميناً.
    external_credibility: parseMeasure(extCred) ?? 0.5,
  }), [extPrior, locEst, nLocal, cropInYemen, extCred]);
  const blendQ = useExternalPriorBlend(isOpen('blend') && blendReady(blendInput) ? blendInput : null);
  const bFacts = useMemo(() => blendFacts(blendQ.data), [blendQ.data]);

  // ── اقتراح عتبات السياسة (لا مُدخل — من نتائج تنبيهات المستأجِر) ──
  const policyQ = useThresholdSuggestions(isOpen('policy'));
  const policyRows = useMemo(() => thresholdSuggestionRows(policyQ.data), [policyQ.data]);

  // ── تغذية راجعة المعايرة (يبني المستخدم سجلّات دليل المناطق) ──
  const [evRecords, setEvRecords] = useState<EvidenceRecordInput[]>([]);
  const [frRegion, setFrRegion] = useState('');
  const [frLevel, setFrLevel] = useState('none');
  const [frSamples, setFrSamples] = useState('');
  const [frRate, setFrRate] = useState(''); // ٪ ⇒ كسر
  const addRecord = () => {
    if (!frRegion.trim()) return;
    const rate = parseMeasure(frRate);
    setEvRecords((prev) => [...prev, {
      region: frRegion.trim(),
      evidence_level: frLevel,
      sample_count: parseMeasure(frSamples) ?? 0,
      success_rate: rate == null ? null : rate / 100,
      samples_to_verified: 0,
    }]);
    setFrRegion(''); setFrLevel('none'); setFrSamples(''); setFrRate('');
  };
  const feedbackQ = useCalibrationFeedback(
    isOpen('feedback') && evRecords.length > 0 ? evRecords : null,
  );

  // ── تظافر القرائن (يبني المستخدم قائمة قرائن) ──
  const [evidences, setEvidences] = useState<EvidenceItemInput[]>([]);
  const [cbType, setCbType] = useState('lab_field');
  const [cbAgrees, setCbAgrees] = useState(true);
  const [cbNote, setCbNote] = useState('');
  const [cbKey, setCbKey] = useState('general');
  const [cbTest, setCbTest] = useState('تربة');
  const addEvidence = () => {
    setEvidences((prev) => [...prev, { etype: cbType, agrees: cbAgrees, note_ar: cbNote.trim() }]);
    setCbNote('');
  };
  const corroborateInput = useMemo<CorroborationInput>(() => ({
    evidences,
    recommendation_key: cbKey.trim() || 'general',
    test_type_ar: cbTest.trim() || 'تربة',
  }), [evidences, cbKey, cbTest]);
  const corroborateQ = useCorroborate(
    isOpen('corroborate') && evidences.length > 0 ? corroborateInput : null,
  );

  // ── بوّابة الثقة (يبني المستخدم إشارات المحرّكات) ──
  const [signals, setSignals] = useState<EngineSignalInput[]>([]);
  const [sgEngine, setSgEngine] = useState('irrigation');
  const [sgHasRec, setSgHasRec] = useState(true);
  const [sgConf, setSgConf] = useState(''); // ٪ ⇒ كسر
  const [sgBlock, setSgBlock] = useState('');
  const addSignal = () => {
    const conf = parseMeasure(sgConf);
    setSignals((prev) => [...prev, {
      engine: sgEngine.trim() || 'engine',
      has_recommendation: sgHasRec,
      confidence: conf == null ? null : conf / 100,
      blocking_reason_ar: sgBlock.trim() || null,
      data_gaps_ar: [],
    }]);
    setSgConf(''); setSgBlock('');
  };
  const gateInput = useMemo<ConfidenceGateInput>(() => ({ signals }), [signals]);
  const gateQ = useConfidenceGate(isOpen('gate') && signals.length > 0 ? gateInput : null);

  // ── تسجيل مشاهدة (كتابة) — قياس حقيقيّ يُدخِله المستخدم ──
  const [obId, setObId] = useState('');
  const [obValue, setObValue] = useState('');
  const [obUnit, setObUnit] = useState('');
  const [obSource, setObSource] = useState('manual');
  const [obConf, setObConf] = useState('medium');
  const [obWhen, setObWhen] = useState('');
  const recordObs = useRecordObservation();
  const obsInput = useMemo<ObservationInput>(() => ({
    tenant_id: tenantId ?? '',
    farm_id: null,
    field_id: fieldId ?? null,
    observable_id: obId.trim(),
    value: parseMeasure(obValue),
    unit: obUnit.trim(),
    source: obSource,
    confidence: obConf,
    measured_at: obWhen.trim(),
    method: null,
  }), [tenantId, fieldId, obId, obValue, obUnit, obSource, obConf, obWhen]);
  const obsReady = observationReady(obsInput);
  const onRecordObs = () => { if (obsReady) recordObs.mutate(obsInput); };

  // ── طبقات الخريطة + تقرير التغطية (قراءات ثابتة) ──
  const layersQ = useMapLayers(isOpen('layers'));
  const layers = useMemo(() => mapLayers(layersQ.data), [layersQ.data]);
  const coverageQ = useCoverageReport(isOpen('coverage'));
  const linkedRows = useMemo(() => coverageEntries(coverageQ.data?.decision_linked), [coverageQ.data]);
  const displayRows = useMemo(() => coverageEntries(coverageQ.data?.display_or_context_only), [coverageQ.data]);

  if (!enabled) return null;

  const disabledMsg = (d?: boolean) => d
    ? <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على الخادم بعد.</div>
    : null;
  const loadingMsg = (t: string) => <div className="text-[11px]" style={{ color: T.faint }}>{t}</div>;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="learning-evidence"
      aria-label="التعلّم والدليل"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <BrainCircuit className="w-4 h-4 text-emerald-300" aria-hidden="true" /> التعلّم والدليل
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>
      <div className="text-[10px] mb-2" style={{ color: T.faint }}>
        أسطح إرشاديّة للمرشد الزراعيّ — أحكام الخادم تُعرَض حرفيّاً؛ لا توصية مُلزِمة تُصدَر هنا.
      </div>

      <div className="flex flex-col gap-2">
        {/* ═══ بوّابة تفعيل التعلّم ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Gauge className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="بوّابة تفعيل التعلّم" open={isOpen('activation')} onToggle={() => toggle('activation')} />
          {isOpen('activation') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {activationQ.isLoading ? loadingMsg('جارٍ قراءة حالة البوّابة…')
                : disabledMsg(activationQ.data?.disabled) ?? (activationQ.data ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <StatusPill {...activationBadge(activationQ.data.state)} />
                      {activationQ.data.state_ar && <span style={{ color: T.muted }}>{activationQ.data.state_ar}</span>}
                    </div>
                    <FactPills facts={actFacts} />
                    {(activationQ.data.blockers ?? []).map((b, i) => (
                      <div key={i} className="text-[11px]" style={{ color: '#fdba74' }}>• {b}</div>
                    ))}
                    {activationQ.data.can_activate === false && (
                      <div className="text-[10px]" style={{ color: T.faint }}>can_activate=false — خاملة بصدق حتى العتبة.</div>
                    )}
                    {activationQ.data.data_source_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{activationQ.data.data_source_note_ar}</div>}
                    {activationQ.data.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{activationQ.data.honesty_note_ar}</div>}
                  </>
                ) : null)}
            </div>
          )}
        </div>

        {/* ═══ معايرة التنبّؤ ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Activity className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="معايرة التنبّؤ" open={isOpen('calibration')} onToggle={() => toggle('calibration')} />
          {isOpen('calibration') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <LabeledInput id="cal-crop" label="المحصول (تصفية اختياريّة)" value={calCrop} onChange={setCalCrop} placeholder={cropLabel || 'الكلّ'} width="w-24" />
              {calibrationQ.isLoading ? loadingMsg('جارٍ تحليل الانحياز المنهجيّ…')
                : disabledMsg(calibrationQ.data?.disabled) ?? (calibrationQ.data ? (
                  <>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <StatusPill {...biasBadge(calibrationQ.data.bias_type)} />
                      {calibrationQ.data.can_calibrate === false && <span style={{ color: T.faint }}>can_calibrate=false (لا تصحيح)</span>}
                    </div>
                    <FactPills facts={calFacts} />
                    {calibrationQ.data.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{calibrationQ.data.reason_ar}</div>}
                    {calibrationQ.data.data_source_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{calibrationQ.data.data_source_note_ar}</div>}
                    {calibrationQ.data.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{calibrationQ.data.honesty_note_ar}</div>}
                  </>
                ) : null)}
            </div>
          )}
        </div>

        {/* ═══ مزج سابقة خارجيّة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<GitMerge className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="مزج سابقة خارجيّة" open={isOpen('blend')} onToggle={() => toggle('blend')} />
          {isOpen('blend') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="bl-ext" label="سابقة خارجيّة" value={extPrior} onChange={setExtPrior} type="number" width="w-20" />
                <LabeledInput id="bl-loc" label="تقدير محلّيّ" value={locEst} onChange={setLocEst} type="number" width="w-20" />
                <LabeledInput id="bl-n" label="عيّنات محلّيّة" value={nLocal} onChange={setNLocal} type="number" width="w-16" />
                <LabeledInput id="bl-cred" label="مصداقيّة (0-1)" value={extCred} onChange={setExtCred} type="number" width="w-16" />
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={cropInYemen} onChange={(e) => setCropInYemen(e.target.checked)} /> مزروع في اليمن
                </label>
              </div>
              {!blendReady(blendInput) ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل سابقة خارجيّة أو تقديراً محلّيّاً بعيّنة (لا مزج بلا قرينة).</div>
              ) : blendQ.isLoading ? loadingMsg('جارٍ مزج القرائن…')
                : disabledMsg(blendQ.data?.disabled) ?? (blendQ.data ? (
                  <>
                    {blendQ.data.applicable === false ? (
                      <div className="text-[11px]" style={{ color: '#fdba74' }}>غير منطبق: {blendQ.data.reason_ar}</div>
                    ) : (
                      <>
                        <FactPills facts={bFacts} />
                        {blendQ.data.matured != null && (
                          <div className="text-[10px]" style={{ color: T.faint }}>
                            {blendQ.data.prior_faded ? 'السابقة الخارجيّة تلاشت' : 'السابقة الخارجيّة لا تزال مؤثّرة'}
                          </div>
                        )}
                        {blendQ.data.escalation?.level && (
                          <div className="flex items-center gap-2 text-[11px]">
                            <StatusPill {...escalationBadge(blendQ.data.escalation.level)} />
                            {blendQ.data.escalation.reason_ar && <span style={{ color: T.muted }}>{blendQ.data.escalation.reason_ar}</span>}
                          </div>
                        )}
                        {blendQ.data.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{blendQ.data.reason_ar}</div>}
                      </>
                    )}
                    {blendQ.data.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{blendQ.data.honesty_note_ar}</div>}
                  </>
                ) : null)}
            </div>
          )}
        </div>

        {/* ═══ اقتراح عتبات السياسة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<SlidersHorizontal className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="اقتراح عتبات التنبيه" open={isOpen('policy')} onToggle={() => toggle('policy')} />
          {isOpen('policy') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {policyQ.isLoading ? loadingMsg('جارٍ اشتقاق الاقتراحات…')
                : disabledMsg(policyQ.data?.disabled) ?? (policyQ.data ? (
                  <>
                    {policyRows.length > 0 ? policyRows.map((r) => {
                      const b = suggestionBadge(r.suggestion);
                      const overrides = overrideEntries(r.suggested_overrides);
                      return (
                        <div key={r.alert_type} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                          <div className="flex flex-wrap items-center gap-2 text-[11px]">
                            <span className="font-bold" style={{ color: T.ink }}>{r.alert_type}</span>
                            <StatusPill {...b} />
                            <span style={{ color: T.faint }}>نافع {pctFromFraction(r.useful_rate)} · n={r.n ?? 0}</span>
                          </div>
                          {overrides.length > 0 && (
                            <div className="text-[10px]" style={{ color: T.muted }}>
                              عتبات مقترَحة: {overrides.map((o) => `${o.key}=${fmtNum(o.value, 2)}`).join('، ')}
                            </div>
                          )}
                          {r.rationale_ar && <div className="text-[11px]" style={{ color: T.muted }}>{r.rationale_ar}</div>}
                        </div>
                      );
                    }) : (
                      <div className="text-[11px]" style={{ color: T.muted }}>لا نتائج تنبيهات مُسجَّلة بعد — لا اقتراحات.</div>
                    )}
                    {policyQ.data.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{policyQ.data.note_ar}</div>}
                  </>
                ) : null)}
            </div>
          )}
        </div>

        {/* ═══ تغذية راجعة المعايرة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ClipboardCheck className="w-4 h-4 text-lime-300" aria-hidden="true" />} title="تغذية راجعة المعايرة" open={isOpen('feedback')} onToggle={() => toggle('feedback')} />
          {isOpen('feedback') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="fr-region" label="المنطقة" value={frRegion} onChange={setFrRegion} placeholder="sanaa" width="w-20" />
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="fr-level" className="text-[11px] font-bold" style={{ color: T.ink }}>مستوى الدليل:</label>
                  <select id="fr-level" value={frLevel} onChange={(e) => setFrLevel(e.target.value)} className={inputCls} style={inputStyle}>
                    {EVIDENCE_LEVEL_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="fr-n" label="عيّنات" value={frSamples} onChange={setFrSamples} type="number" width="w-14" />
                <LabeledInput id="fr-rate" label="نجاح ٪" value={frRate} onChange={setFrRate} type="number" width="w-14" />
                <button type="button" onClick={addRecord} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف منطقة</button>
              </div>
              {evRecords.length === 0 ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أضِف سجلّ دليل منطقة واحداً على الأقلّ لاشتقاق أولويّات المراجعة.</div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {evRecords.map((r, i) => (
                      <span key={`${r.region}-${i}`} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                        {r.region} · {r.evidence_level} · n={r.sample_count}
                      </span>
                    ))}
                    <button type="button" onClick={() => setEvRecords([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                  </div>
                  {feedbackQ.isLoading ? loadingMsg('جارٍ تحديد أولويّات المراجعة…')
                    : disabledMsg(feedbackQ.data?.disabled) ?? (feedbackQ.data ? (
                      <>
                        {/* أعلام الحوكمة حرفيّاً: لا تعديل آليّ، ليست معايرة */}
                        <div className="flex flex-wrap items-center gap-2 text-[10px]" style={{ color: '#fdba74' }}>
                          {feedbackQ.data.auto_adjust === false && <span>auto_adjust=false (لا تعديل آليّ)</span>}
                          {feedbackQ.data.calibrated === false && <span>calibrated=false (اقتراح مراجعة بشريّة)</span>}
                        </div>
                        {(feedbackQ.data.regions ?? []).map((rg, i) => (
                          <div key={`${rg.region}-${i}`} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                            <div className="flex flex-wrap items-center gap-2 text-[11px]">
                              <span className="font-bold" style={{ color: T.ink }}>{rg.region}</span>
                              <StatusPill {...feedbackActionBadge(rg.action)} />
                              {rg.success_rate != null && <span style={{ color: T.faint }}>نجاح {pctFromFraction(rg.success_rate)}</span>}
                            </div>
                            {rg.recommendation_ar && <div className="text-[11px]" style={{ color: T.muted }}>{rg.recommendation_ar}</div>}
                            {(rg.review_targets ?? []).length > 0 && <div className="text-[10px]" style={{ color: T.faint }}>معاملات للمراجعة: {(rg.review_targets ?? []).join('، ')}</div>}
                          </div>
                        ))}
                        {(feedbackQ.data.warnings_ar ?? []).map((w, i) => (
                          <div key={i} className="text-[10px]" style={{ color: '#fdba74' }}>⚠ {w}</div>
                        ))}
                      </>
                    ) : null)}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ تظافر القرائن ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ShieldCheck className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="تظافر القرائن" open={isOpen('corroborate')} onToggle={() => toggle('corroborate')} />
          {isOpen('corroborate') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="cb-type" className="text-[11px] font-bold" style={{ color: T.ink }}>القرينة:</label>
                  <select id="cb-type" value={cbType} onChange={(e) => setCbType(e.target.value)} className={inputCls} style={inputStyle}>
                    {EVIDENCE_TYPE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={cbAgrees} onChange={(e) => setCbAgrees(e.target.checked)} /> تتّفق
                </label>
                <LabeledInput id="cb-note" label="ملاحظة" value={cbNote} onChange={setCbNote} placeholder="اختياريّ" width="w-28" />
                <button type="button" onClick={addEvidence} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف قرينة</button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="cb-key" label="نوع التوصية" value={cbKey} onChange={setCbKey} placeholder="general / phosphorus" width="w-24" />
                <LabeledInput id="cb-test" label="نوع الفحص" value={cbTest} onChange={setCbTest} placeholder="تربة / مياه" width="w-16" />
              </div>
              {evidences.length === 0 ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أضِف قرينة واحدة على الأقلّ لتحديد درجة التوصية.</div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {evidences.map((e, i) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: e.agrees ? '#86efac' : '#fca5a5' }}>
                        {e.etype}{e.agrees ? ' ✓' : ' ✗'}
                      </span>
                    ))}
                    <button type="button" onClick={() => setEvidences([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                  </div>
                  {corroborateQ.isLoading ? loadingMsg('جارٍ تظافر القرائن…')
                    : disabledMsg(corroborateQ.data?.disabled) ?? (corroborateQ.data ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <StatusPill {...tierBadge(corroborateQ.data.tier)} />
                          {corroborateQ.data.tier_ar && <span style={{ color: T.muted }}>{corroborateQ.data.tier_ar}</span>}
                          <span style={{ color: T.faint }}>متّفقة {corroborateQ.data.n_agreeing ?? 0}/{corroborateQ.data.n_independent ?? 0}</span>
                        </div>
                        {corroborateQ.data.explanation_ar && <div className="text-[11px]" style={{ color: T.muted }}>{corroborateQ.data.explanation_ar}</div>}
                        {corroborateQ.data.nudge_ar && <div className="text-[11px]" style={{ color: '#fdba74' }}>{corroborateQ.data.nudge_ar}</div>}
                      </div>
                    ) : null)}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ بوّابة الثقة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ShieldCheck className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="بوّابة الثقة" open={isOpen('gate')} onToggle={() => toggle('gate')} />
          {isOpen('gate') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="sg-engine" className="text-[11px] font-bold" style={{ color: T.ink }}>المحرّك:</label>
                  <select id="sg-engine" value={sgEngine} onChange={(e) => setSgEngine(e.target.value)} className={inputCls} style={inputStyle}>
                    {ENGINE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <label className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
                  <input type="checkbox" checked={sgHasRec} onChange={(e) => setSgHasRec(e.target.checked)} /> أنتج توصية
                </label>
                <LabeledInput id="sg-conf" label="الثقة ٪" value={sgConf} onChange={setSgConf} type="number" width="w-14" />
                <LabeledInput id="sg-block" label="سبب الحجب" value={sgBlock} onChange={setSgBlock} placeholder="اختياريّ" width="w-28" />
                <button type="button" onClick={addSignal} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف إشارة</button>
              </div>
              {signals.length === 0 ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أضِف إشارة محرّك واحدة على الأقلّ لتقييم الثقة الموحّدة.</div>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {signals.map((s, i) => (
                      <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                        {s.engine} · {s.has_recommendation ? pctFromFraction(s.confidence) : 'بلا توصية'}
                      </span>
                    ))}
                    <button type="button" onClick={() => setSignals([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                  </div>
                  {gateQ.isLoading ? loadingMsg('جارٍ تقييم بوّابة الثقة…')
                    : disabledMsg(gateQ.data?.disabled) ?? (gateQ.data ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        <div className="flex flex-wrap items-center gap-2 text-[11px]">
                          <StatusPill {...gateBadge(gateQ.data.decision)} />
                          <span style={{ color: T.faint }}>ثقة {pctFromFraction(gateQ.data.overall_confidence)}</span>
                        </div>
                        {gateQ.data.reason_ar && <div className="text-[11px]" style={{ color: T.muted }}>{gateQ.data.reason_ar}</div>}
                        {gateQ.data.next_action_ar && <div className="text-[11px]" style={{ color: '#7dd3fc' }}>{gateQ.data.next_action_ar}</div>}
                      </div>
                    ) : null)}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ تسجيل مشاهدة (كتابة) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ScrollText className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="تسجيل مشاهدة" open={isOpen('observation')} onToggle={() => toggle('observation')} />
          {isOpen('observation') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="ob-id" label="المُشاهَد" value={obId} onChange={setObId} placeholder="soil_ph" width="w-24" />
                <LabeledInput id="ob-val" label="القيمة" value={obValue} onChange={setObValue} type="number" width="w-16" />
                <LabeledInput id="ob-unit" label="الوحدة" value={obUnit} onChange={setObUnit} placeholder="اختياريّ" width="w-14" />
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="ob-src" className="text-[11px] font-bold" style={{ color: T.ink }}>المصدر:</label>
                  <select id="ob-src" value={obSource} onChange={(e) => setObSource(e.target.value)} className={inputCls} style={inputStyle}>
                    {OBS_SOURCE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <span className="inline-flex items-center gap-1">
                  <label htmlFor="ob-conf" className="text-[11px] font-bold" style={{ color: T.ink }}>الثقة:</label>
                  <select id="ob-conf" value={obConf} onChange={(e) => setObConf(e.target.value)} className={inputCls} style={inputStyle}>
                    {OBS_CONFIDENCE_OPTIONS.map((o) => <option key={o.key} value={o.key}>{o.label_ar}</option>)}
                  </select>
                </span>
                <LabeledInput id="ob-when" label="وقت القياس (ISO)" value={obWhen} onChange={setObWhen} placeholder="2026-07-05T08:00:00Z" width="w-40" />
              </div>
              {!fieldId && <div className="text-[10px]" style={{ color: T.faint }}>لا حقل مختار — ستُسجَّل المشاهدة بلا field_id.</div>}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={onRecordObs}
                  disabled={!obsReady || recordObs.isPending}
                  className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40"
                  style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(15,23,42,.45)' }}
                >
                  {recordObs.isPending ? '…' : 'سجّل المشاهدة'}
                </button>
                {!obsReady && <span className="text-[10px]" style={{ color: T.faint }}>يلزم مُشاهَد + قيمة + وقت قياس.</span>}
                {recordObs.isSuccess && (
                  <span className="text-[11px]" role="status" style={{ color: '#86efac' }}>
                    {recordObs.data?.message_ar ?? 'سُجّلت'} (op_id: {recordObs.data?.op_id ?? '—'})
                  </span>
                )}
                {recordObs.isError && (
                  <span className="text-[11px]" role="status" style={{ color: '#fca5a5' }}>
                    تعذّر التسجيل — قد يتطلّب صلاحيّة تسجيل المشاهدات أو تطابق المستأجِر
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ═══ طبقات الخريطة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="طبقات الخريطة" open={isOpen('layers')} onToggle={() => toggle('layers')} />
          {isOpen('layers') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {layersQ.isLoading ? loadingMsg('جارٍ قراءة طبقات الخريطة…')
                : disabledMsg(layersQ.data?.disabled) ?? (
                  layers.length > 0 ? (
                    <>
                      <div className="flex flex-col gap-1">
                        {layers.map((l) => (
                          <div key={l.id ?? l.name_ar} className="flex flex-col gap-0.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                            <div className="flex flex-wrap items-center gap-2 text-[11px]">
                              <span className="font-bold" style={{ color: T.ink }}>{l.name_ar ?? l.id}</span>
                              {l.category && <span style={{ color: T.faint }}>{l.category}</span>}
                              {l.unit && <span style={{ color: T.faint }}>{l.unit}</span>}
                            </div>
                            {l.band_math && <div className="text-[10px] font-mono" style={{ color: T.muted }} dir="ltr">{l.band_math}</div>}
                            {l.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{l.note_ar}</div>}
                          </div>
                        ))}
                      </div>
                      {layersQ.data?.note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{layersQ.data.note_ar}</div>}
                    </>
                  ) : (
                    <div className="text-[11px]" style={{ color: T.muted }}>لا طبقات قابلة للرسم من الخادم بعد.</div>
                  )
                )}
            </div>
          )}
        </div>

        {/* ═══ تقرير تغطية المؤشّرات ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<MapIcon className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="تغطية المؤشّرات" open={isOpen('coverage')} onToggle={() => toggle('coverage')} />
          {isOpen('coverage') && (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {coverageQ.isLoading ? loadingMsg('جارٍ قراءة تقرير التغطية…')
                : disabledMsg(coverageQ.data?.disabled) ?? (coverageQ.data ? (
                  <>
                    {linkedRows.length > 0 && (
                      <div className="flex flex-col gap-0.5">
                        <div className="text-[11px] font-bold" style={{ color: '#86efac' }}>مربوط بالقرار</div>
                        {linkedRows.map((r) => (
                          <div key={r.index} className="text-[11px]" style={{ color: T.muted }}>
                            <span className="font-semibold" style={{ color: T.ink }} dir="ltr">{r.index}</span>: {r.desc}
                          </div>
                        ))}
                      </div>
                    )}
                    {displayRows.length > 0 && (
                      <div className="flex flex-col gap-0.5">
                        <div className="text-[11px] font-bold" style={{ color: T.faint }}>عرض/سياق فقط</div>
                        {displayRows.map((r) => (
                          <div key={r.index} className="text-[11px]" style={{ color: T.muted }}>
                            <span className="font-semibold" style={{ color: T.ink }} dir="ltr">{r.index}</span>: {r.desc}
                          </div>
                        ))}
                      </div>
                    )}
                    {coverageQ.data.honesty_note_ar && <div className="text-[10px]" style={{ color: T.faint }}>{coverageQ.data.honesty_note_ar}</div>}
                  </>
                ) : null)}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
