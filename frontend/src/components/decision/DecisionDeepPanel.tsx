import { useMemo, useState } from 'react';
import {
  BadgeDollarSign, BookOpenCheck, Compass, Layers, PenLine, Scale, Send, Trash2,
} from 'lucide-react';
import {
  useDecisionEconomics, useDecisionExplainDeep, useDecisionForLocation,
  useExecuteDispatch, useRecordDecision, useResolveDecisionPolicies, useUnifiedDecision,
} from '../../hooks/useDecisionDeep';
import {
  EXECUTE_CONFIRM_PHRASE,
  buildForLocationParams, buildUnifiedRequest, executeConfirmed,
  executionStatusColor, executionStatusLabel, explainSourceLabel, hasLocationInput,
  isFeatureDisabled404, moneyLabel, numLabel, parseDecisionValue, percentLabel,
  unifiedStateColor, unifiedStateLabel, urgencyLabel,
  type ForLocationParams, type UnifiedSignalInput,
} from '../../lib/decisionDeep';
import { T } from '../ds';

// خيارات المفردات المعروفة للخادم فقط — لا نخترع قيماً (الخادم يطبّع المجهول بتحفّظ).
const DOMAINS = ['weather', 'soil', 'irrigation', 'pest', 'economics', 'yield'];
const URGENCIES = ['none', 'low', 'moderate', 'high', 'critical'];
const ACTIONS = ['irrigation', 'fertigation', 'spray', 'harvest', 'other'];
const RISKS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const sectionStyle = { borderColor: T.line, background: 'rgba(2,6,23,.35)' } as const;
const buttonStyle = { border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' } as const;

/** رسالة خطأ صادقة موحّدة: 404 على النقاط المحروسة = «الميزة غير مُفعَّلة»،
 *  وغيره خطأ حقيقيّ مع نصّه ودعوة صريحة لإعادة المحاولة — لا أرقام مُختلقة. */
function HonestError({ error, gated }: { error: unknown; gated: boolean }) {
  if (gated && isFeatureDisabled404(error)) {
    return (
      <div className="mt-2 text-[11px]" role="status" style={{ color: T.muted }}>
        غير مُفعَّل — هذه النقطة خلف علم <span className="font-mono">SAHOOL_DECISION_DISPATCH</span> (مُطفأ في هذه البيئة).
      </div>
    );
  }
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="mt-2 text-[11px]" role="status" style={{ color: '#fdba74' }}>
      تعذّر الطلب — {msg}. أعد المحاولة.
    </div>
  );
}

/** لوحة القرار العميق: القرار الموحّد (dry-run) + قرار الموقع وشرحه + الاقتصاد
 *  + استشارة السياسات + إدامة القرار + التنفيذ المحروس. صدق: كلّ الأحكام
 *  (state/halt_reasons/reason_ar/audit) من الخادم حرفيّاً؛ 404 على النقاط
 *  المحروسة ⇒ «غير مُفعَّل»؛ الغائب «—» لا صفر. التنفيذ خلف تأكيد مكتوب —
 *  وحراسة الواجهة بصريّة فقط: الحاكم الفعليّ صلاحيّات الخادم
 *  (RECOMMENDATION_REQUEST) وحواجزه ومفتاح إيقاف الطوارئ. */
export default function DecisionDeepPanel() {
  // ── القرار الموحّد ──
  const unifiedM = useUnifiedDecision();
  const [uFieldId, setUFieldId] = useState('');
  const [uSignals, setUSignals] = useState<UnifiedSignalInput[]>([]);
  const [uMinMm, setUMinMm] = useState('');
  const [uBudgetMm, setUBudgetMm] = useState('');
  // مسودّة إشارة واحدة تُضاف إلى القائمة (الخادم يصالح المتوازيات).
  const [sigDomain, setSigDomain] = useState('irrigation');
  const [sigAction, setSigAction] = useState('irrigate');
  const [sigUrgency, setSigUrgency] = useState('moderate');
  const [sigWaterMm, setSigWaterMm] = useState('');
  const [sigHalt, setSigHalt] = useState(false);
  const [sigReason, setSigReason] = useState('');

  const addSignal = () => {
    const water = sigWaterMm.trim() === '' ? undefined : Number(sigWaterMm);
    setUSignals((prev) => [...prev, {
      domain: sigDomain,
      action: sigAction.trim() || 'none',
      urgency: sigUrgency,
      // water_mm فقط إن أُدخل رقم صالح — لا معاملات مُختلقة.
      params: water != null && Number.isFinite(water) ? { water_mm: water } : {},
      halt: sigHalt,
      reason_ar: sigReason.trim(),
      confidence: 1.0,
    }]);
    setSigReason(''); setSigWaterMm(''); setSigHalt(false);
  };

  const runUnified = () => {
    if (!uFieldId.trim() || uSignals.length === 0) return;
    unifiedM.mutate(buildUnifiedRequest({
      fieldId: uFieldId, signals: uSignals, minMmForYield: uMinMm, waterBudgetMm: uBudgetMm,
    }));
  };

  // ── قرار الموقع + الشرح (نفس المعاملات — الشرح يشتقّ القرار خادميّاً) ──
  const [locName, setLocName] = useState('');
  const [locLat, setLocLat] = useState('');
  const [locLon, setLocLon] = useState('');
  const [locPh, setLocPh] = useState('');
  const [locEc, setLocEc] = useState('');
  const [locArea, setLocArea] = useState('');
  const [locParams, setLocParams] = useState<ForLocationParams | null>(null);
  const [explainParams, setExplainParams] = useState<ForLocationParams | null>(null);
  const forLocQ = useDecisionForLocation(locParams);
  const explainQ = useDecisionExplainDeep(explainParams);

  const draftParams = useMemo(() => buildForLocationParams({
    location: locName, lat: locLat, lon: locLon, soilPh: locPh, soilEcDsm: locEc, areaHa: locArea,
  }), [locName, locLat, locLon, locPh, locEc, locArea]);
  const canAsk = hasLocationInput(draftParams);

  // ── الاقتصاد (قراءة — تُحدَّث المعاملات عند الطلب) ──
  const [ecoArea, setEcoArea] = useState('');
  const [ecoCost, setEcoCost] = useState('');
  const [ecoOpts, setEcoOpts] = useState<{ areaHa?: number; waterCostPerM3?: number }>({});
  const economicsQ = useDecisionEconomics(ecoOpts);
  const applyEco = () => setEcoOpts({
    areaHa: ecoArea.trim() === '' ? undefined : Number(ecoArea) || undefined,
    waterCostPerM3: ecoCost.trim() === '' ? undefined : Number(ecoCost) || undefined,
  });

  // ── استشارة السياسات ──
  const resolveM = useResolveDecisionPolicies();
  const [polAction, setPolAction] = useState('irrigation');
  const [polRisk, setPolRisk] = useState('MEDIUM');
  const [polCrop, setPolCrop] = useState('');

  // ── إدامة قرار (تسجيل صادق — لا تنفيذ ولا نتيجة مُختلقة) ──
  const recordM = useRecordDecision();
  const [recType, setRecType] = useState('');
  const [recFieldId, setRecFieldId] = useState('');
  const [recRegion, setRecRegion] = useState('');
  const [recConfidence, setRecConfidence] = useState('');
  const [recValueText, setRecValueText] = useState('');
  const [recParseError, setRecParseError] = useState<string | null>(null);
  const runRecord = () => {
    const parsed = parseDecisionValue(recValueText);
    if (!parsed.ok) { setRecParseError(parsed.error_ar); return; }
    setRecParseError(null);
    const conf = recConfidence.trim() === '' ? undefined : Number(recConfidence);
    recordM.mutate({
      decision_type: recType.trim(),
      decision_value: parsed.value,
      field_id: recFieldId.trim() || undefined,
      region: recRegion.trim() || undefined,
      // الثقة الناقصة تُدام NULL خادميّاً — لا نرسل رقماً مُختلقاً.
      confidence: conf != null && Number.isFinite(conf) ? conf : undefined,
    });
  };

  // ── التنفيذ المحروس ──
  // حراسة بصريّة: هذا القسم موجَّه لمدير التشغيل — الخادم يفرض
  // RECOMMENDATION_REQUEST + الحواجز + مفتاح إيقاف الطوارئ (fail-closed)؛
  // الواجهة لا تتجاوزه ولا تدّعي نجاحاً: حكم الخادم يُعرَض حرفيّاً.
  const executeM = useExecuteDispatch();
  const [exRecId, setExRecId] = useState('');
  const [exAction, setExAction] = useState('irrigation');
  const [exRisk, setExRisk] = useState('MEDIUM');
  const [exFieldId, setExFieldId] = useState('');
  const [exDeviceId, setExDeviceId] = useState('');
  const [exCommand, setExCommand] = useState('');
  const [exConfirm, setExConfirm] = useState('');
  const exReady = !!exRecId.trim() && executeConfirmed(exConfirm);
  const runExecute = () => {
    if (!exReady) return;
    executeM.mutate({
      recommendation_id: exRecId.trim(),
      action_type: exAction,
      risk_level: exRisk,
      field_id: exFieldId.trim() || undefined,
      device_id: exDeviceId.trim() || undefined,
      command: exCommand.trim() || undefined,
    });
  };

  return (
    <div className="flex flex-col gap-3" data-testid="decision-deep">
      <div className="grid gap-3 md:grid-cols-2">
        {/* القرار الموحّد — مصالحة إشارات المجالات (معاينة dry-run، لا تنفيذ) */}
        <section className="rounded-2xl border p-3" style={sectionStyle}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <Layers className="w-4 h-4 text-emerald-300" aria-hidden="true" /> القرار الموحّد (مصالحة المجالات)
            <span className="text-[11px] font-normal" style={{ color: T.faint }}>· معاينة فقط — لا تنفيذ</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input value={uFieldId} onChange={(e) => setUFieldId(e.target.value)} placeholder="معرّف الحقل" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={uMinMm} onChange={(e) => setUMinMm(e.target.value)} placeholder="حدّ أدنى للغلّة (مم، اختياريّ)" className="w-44 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={uBudgetMm} onChange={(e) => setUBudgetMm(e.target.value)} placeholder="ميزانيّة ماء (مم، اختياريّ)" className="w-40 px-2 py-1 rounded-lg" style={inputStyle} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <select value={sigDomain} onChange={(e) => setSigDomain(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <input value={sigAction} onChange={(e) => setSigAction(e.target.value)} placeholder="الإجراء (irrigate…)" className="w-32 px-2 py-1 rounded-lg" style={inputStyle} />
            <select value={sigUrgency} onChange={(e) => setSigUrgency(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {URGENCIES.map((u) => <option key={u} value={u}>{urgencyLabel(u)}</option>)}
            </select>
            <input type="number" value={sigWaterMm} onChange={(e) => setSigWaterMm(e.target.value)} placeholder="ماء (مم)" className="w-24 px-2 py-1 rounded-lg" style={inputStyle} />
            <label className="inline-flex items-center gap-1">
              <input type="checkbox" checked={sigHalt} onChange={(e) => setSigHalt(e.target.checked)} /> خطّ أحمر (halt)
            </label>
            <input value={sigReason} onChange={(e) => setSigReason(e.target.value)} placeholder="السبب (عربيّ)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <button type="button" onClick={addSignal} className="px-2.5 py-1 rounded-lg font-semibold" style={buttonStyle}>أضِف إشارة</button>
          </div>
          {uSignals.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {uSignals.map((s, i) => (
                <span key={`${s.domain}-${i}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px]" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                  {s.domain} · {s.action} · {urgencyLabel(s.urgency)}{s.halt ? ' · ⛔' : ''}
                  <button type="button" aria-label="احذف الإشارة" onClick={() => setUSignals((prev) => prev.filter((_, j) => j !== i))}>
                    <Trash2 className="w-3 h-3" aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={runUnified}
            disabled={!uFieldId.trim() || uSignals.length === 0 || unifiedM.isPending}
            className="mt-2 px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50 text-[11px]"
            style={buttonStyle}
          >
            {unifiedM.isPending ? 'جارٍ المصالحة…' : 'صالِح القرار (بلا تنفيذ)'}
          </button>
          {unifiedM.isError && <HonestError error={unifiedM.error} gated />}
          {unifiedM.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div>
                <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: unifiedStateColor(unifiedM.data.state) }}>
                  {unifiedStateLabel(unifiedM.data.state)}
                </span>
                <span className="mr-1" style={{ color: T.faint }}> · ثقة {percentLabel(unifiedM.data.confidence)}</span>
                {unifiedM.data.dry_run && <span style={{ color: T.faint }}> · معاينة فقط — لم يُنفَّذ شيء</span>}
              </div>
              {unifiedM.data.rationale_ar && <div>{unifiedM.data.rationale_ar}</div>}
              {(unifiedM.data.halt_reasons ?? []).map((h) => (
                <div key={h} style={{ color: '#fca5a5' }}>⛔ {h}</div>
              ))}
              {(unifiedM.data.reconciliations_ar ?? []).map((r) => (
                <div key={r} style={{ color: T.faint }}>⚖ {r}</div>
              ))}
              {(unifiedM.data.action_plan ?? []).map((a, i) => (
                <div key={`${a.action}-${i}`} style={{ color: T.ink }}>
                  {a.action} <span style={{ color: T.faint }}>({urgencyLabel(a.urgency)} · {a.domains.join('، ')})</span>
                  {a.rationale_ar ? <span style={{ color: T.muted }}> — {a.rationale_ar}</span> : null}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* قرار الموقع (for-location) + الشرح (explain) — استشاريّ، لا يُوزَّع للتنفيذ */}
        <section className="rounded-2xl border p-3" style={sectionStyle}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <Compass className="w-4 h-4 text-sky-300" aria-hidden="true" /> قرار الموقع + شرحه
            <span className="text-[11px] font-normal" style={{ color: T.faint }}>· استشاريّ — لا يُنفَّذ</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input value={locName} onChange={(e) => setLocName(e.target.value)} placeholder="محافظة/مديريّة" className="w-32 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={locLat} onChange={(e) => setLocLat(e.target.value)} placeholder="lat" className="w-20 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={locLon} onChange={(e) => setLocLon(e.target.value)} placeholder="lon" className="w-20 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={locPh} onChange={(e) => setLocPh(e.target.value)} placeholder="pH التربة" className="w-24 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={locEc} onChange={(e) => setLocEc(e.target.value)} placeholder="EC (dS/m)" className="w-24 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={locArea} onChange={(e) => setLocArea(e.target.value)} placeholder="مساحة (هـ)" className="w-24 px-2 py-1 rounded-lg" style={inputStyle} />
            <button type="button" onClick={() => setLocParams(draftParams)} disabled={!canAsk} className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50" style={buttonStyle}>
              اطلب القرار
            </button>
            <button type="button" onClick={() => setExplainParams(draftParams)} disabled={!canAsk} className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50" style={buttonStyle}>
              اشرح القرار
            </button>
          </div>
          {!canAsk && <div className="mt-1 text-[11px]" style={{ color: T.faint }}>أدخِل اسم موقع أو زوج إحداثيّات (lat+lon).</div>}
          {forLocQ.isLoading && <div className="mt-2 text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>}
          {forLocQ.isError && <HonestError error={forLocQ.error} gated={false} />}
          {forLocQ.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              {!forLocQ.data.supported ? (
                <div style={{ color: '#fdba74' }}>
                  {forLocQ.data.message_ar ?? forLocQ.data.needs_clarification_ar ?? 'الموقع غير مدعوم.'}
                  {(forLocQ.data.example_districts_ar ?? []).length > 0 && (
                    <span style={{ color: T.faint }}> — أمثلة: {(forLocQ.data.example_districts_ar ?? []).join('، ')}</span>
                  )}
                </div>
              ) : (
                <>
                  {forLocQ.data.decision_summary_ar && <div style={{ color: T.ink }}>{forLocQ.data.decision_summary_ar}</div>}
                  {(forLocQ.data.suited_crops_ar ?? []).length > 0 && <div>الأنسب: {(forLocQ.data.suited_crops_ar ?? []).join('، ')}</div>}
                  {(forLocQ.data.avoid_ar ?? []).length > 0 && <div style={{ color: '#fdba74' }}>تجنّب: {(forLocQ.data.avoid_ar ?? []).join('، ')}</div>}
                  {forLocQ.data.water_strategy_ar && <div>💧 {forLocQ.data.water_strategy_ar}</div>}
                  {forLocQ.data.salinity_alert_ar && <div style={{ color: '#fca5a5' }}>{forLocQ.data.salinity_alert_ar}</div>}
                  {forLocQ.data.alkalinity_alert_ar && <div style={{ color: '#fca5a5' }}>{forLocQ.data.alkalinity_alert_ar}</div>}
                  {(forLocQ.data.seasonal_risks_ar?.high_severity_ar ?? []).length > 0 && (
                    <div style={{ color: '#fdba74' }}>مخاطر عالية: {(forLocQ.data.seasonal_risks_ar?.high_severity_ar ?? []).join('، ')}</div>
                  )}
                  {(forLocQ.data.next_actions_ar ?? []).map((n) => <div key={n} style={{ color: T.faint }}>← {n}</div>)}
                  {forLocQ.data.disclaimer_ar && <div style={{ color: T.faint }}>{forLocQ.data.disclaimer_ar}</div>}
                </>
              )}
            </div>
          )}
          {explainQ.isLoading && <div className="mt-2 text-[11px]" style={{ color: T.faint }}>جارٍ الشرح…</div>}
          {explainQ.isError && <HonestError error={explainQ.error} gated={false} />}
          {explainQ.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px] rounded-lg p-2" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
              <div className="inline-flex items-center gap-1 font-bold" style={{ color: T.ink }}>
                <BookOpenCheck className="w-3.5 h-3.5" aria-hidden="true" /> الشرح
                <span className="font-normal" style={{ color: T.faint }}>· المصدر: {explainSourceLabel(explainQ.data.explanation_source)}</span>
              </div>
              {/* الشرح يُعرَض حرفيّاً كما صاغه الخادم — لا تلخيص ولا تعديل. */}
              <div className="whitespace-pre-wrap">{explainQ.data.explanation_ar}</div>
              {explainQ.data.note_ar && <div style={{ color: T.faint }}>{explainQ.data.note_ar}</div>}
              {explainQ.data.disclaimer_ar && <div style={{ color: T.faint }}>{explainQ.data.disclaimer_ar}</div>}
            </div>
          )}
        </section>

        {/* الاقتصاد — ترجمة الأثر إلى قيمة (الخادم يحسب فقط مع المساحة/التكلفة) */}
        <section className="rounded-2xl border p-3" style={sectionStyle}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <BadgeDollarSign className="w-4 h-4 text-amber-300" aria-hidden="true" /> اقتصاد القرار (ماء موفَّر ⇒ تكلفة متجنَّبة)
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input type="number" value={ecoArea} onChange={(e) => setEcoArea(e.target.value)} placeholder="مساحة (هـ، اختياريّ)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={ecoCost} onChange={(e) => setEcoCost(e.target.value)} placeholder="تكلفة م³ (اختياريّ)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <button type="button" onClick={applyEco} className="px-2.5 py-1 rounded-lg font-semibold" style={buttonStyle}>حدّث</button>
          </div>
          {economicsQ.isLoading ? (
            <div className="mt-2 text-[11px]" style={{ color: T.faint }}>جارٍ القراءة…</div>
          ) : economicsQ.isError ? (
            <HonestError error={economicsQ.error} gated={false} />
          ) : economicsQ.data?.disabled ? (
            <div className="mt-2 text-[11px]" style={{ color: T.muted }}>
              غير مُفعَّل — اضبط <span className="font-mono">SAHOOL_DECISION_DISPATCH</span> لعرض الترجمة الاقتصاديّة.
            </div>
          ) : economicsQ.data ? (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div style={{ color: T.ink }}>
                قرارات نُفِّذت: <b>{economicsQ.data.executed_decisions}</b>
                <span style={{ color: T.faint }}> · نسبة نجاح {percentLabel(economicsQ.data.success_rate)}</span>
              </div>
              <div>ماء موفَّر: {numLabel(economicsQ.data.water_saved_mm)} مم · {numLabel(economicsQ.data.water_saved_m3)} م³</div>
              <div>قيمة متجنَّبة: {moneyLabel(economicsQ.data.water_cost_avoided, economicsQ.data.currency)}</div>
              {(economicsQ.data.notes_ar ?? []).map((n) => <div key={n} style={{ color: T.faint }}>ℹ {n}</div>)}
            </div>
          ) : null}
        </section>

        {/* استشارة السياسات — dry-run نقيّ: أيّ أثر حوكمة ينطبق على السياق؟ */}
        <section className="rounded-2xl border p-3" style={sectionStyle}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <Scale className="w-4 h-4 text-violet-300" aria-hidden="true" /> استشارة السياسات (dry-run)
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <select value={polAction} onChange={(e) => setPolAction(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={polRisk} onChange={(e) => setPolRisk(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {RISKS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <input value={polCrop} onChange={(e) => setPolCrop(e.target.value)} placeholder="محصول (اختياريّ)" className="w-32 px-2 py-1 rounded-lg" style={inputStyle} />
            <button
              type="button"
              onClick={() => resolveM.mutate({ action_type: polAction, risk_level: polRisk, crop: polCrop.trim() || undefined })}
              disabled={resolveM.isPending}
              className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50"
              style={buttonStyle}
            >
              {resolveM.isPending ? 'جارٍ الاستشارة…' : 'استشِر'}
            </button>
          </div>
          {resolveM.isError && <HonestError error={resolveM.error} gated />}
          {resolveM.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div>
                <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: resolveM.data.auto_block ? '#fca5a5' : '#86efac' }}>
                  {resolveM.data.auto_block ? 'حجب آليّ' : 'لا حجب آليّاً'}
                </span>
                <span className="mr-1" style={{ color: T.faint }}>
                  {' '}· موافقات مطلوبة: {resolveM.data.require_approvals}
                  {' '}· سقف ماء: {resolveM.data.water_cap_pct != null ? `${resolveM.data.water_cap_pct}٪` : '—'}
                </span>
              </div>
              {(resolveM.data.applied_policy_ids ?? []).length === 0
                ? <div style={{ color: T.faint }}>لا سياسة منطبقة على هذا السياق — تبقى الحواجز الافتراضيّة.</div>
                : (resolveM.data.reasons_ar ?? []).map((r) => <div key={r}>⚖ {r}</div>)}
              {resolveM.data.dry_run && <div style={{ color: T.faint }}>استشارة فقط — لا كتابة.</div>}
            </div>
          )}
        </section>

        {/* إدامة قرار — تسجيل رأس القرار للتدقيق/النَّسَب. صدق: يسجّل فقط، لا نتيجة */}
        <section className="rounded-2xl border p-3" style={sectionStyle}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <PenLine className="w-4 h-4 text-emerald-300" aria-hidden="true" /> إدامة قرار (سجلّ النَّسَب)
            <span className="text-[11px] font-normal" style={{ color: T.faint }}>· يسجّل القرار فقط — لا يُنفّذه ولا يقيس نتيجته</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input value={recType} onChange={(e) => setRecType(e.target.value)} placeholder="نوع القرار (irrigation_plan…)" className="w-44 px-2 py-1 rounded-lg" style={inputStyle} />
            <input value={recFieldId} onChange={(e) => setRecFieldId(e.target.value)} placeholder="معرّف الحقل (اختياريّ)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <input value={recRegion} onChange={(e) => setRecRegion(e.target.value)} placeholder="المنطقة (اختياريّ)" className="w-28 px-2 py-1 rounded-lg" style={inputStyle} />
            <input type="number" value={recConfidence} onChange={(e) => setRecConfidence(e.target.value)} placeholder="ثقة 0–1 (اختياريّ)" className="w-28 px-2 py-1 rounded-lg" style={inputStyle} />
          </div>
          <textarea
            value={recValueText}
            onChange={(e) => setRecValueText(e.target.value)}
            placeholder='قيمة القرار كما عُرِضت (JSON) — تُدام كما هي، مثال: {"action":"irrigate","water_mm":20}'
            rows={3}
            className="mt-2 w-full px-2 py-1 rounded-lg text-[11px] font-mono"
            dir="ltr"
            style={inputStyle}
          />
          <button
            type="button"
            onClick={runRecord}
            disabled={!recType.trim() || recordM.isPending}
            className="mt-2 px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50 text-[11px]"
            style={buttonStyle}
          >
            {recordM.isPending ? 'جارٍ الإدامة…' : 'أدِم القرار (تسجيل فقط)'}
          </button>
          {recParseError && <div className="mt-2 text-[11px]" role="status" style={{ color: '#fdba74' }}>{recParseError}</div>}
          {recordM.isError && <HonestError error={recordM.error} gated={false} />}
          {recordM.data && (
            <div className="mt-2 text-[11px]" style={{ color: T.muted }}>
              {recordM.data.persisted
                ? <>أُديم برقم <span className="font-mono" style={{ color: T.ink }}>{recordM.data.decision_id}</span> — اربط به قياس النتيجة لاحقاً.</>
                : 'لم يؤكَّد الحفظ من الخادم.'}
            </div>
          )}
        </section>

        {/* التنفيذ المحروس — لمدير التشغيل؛ تأكيد مكتوب + حكم الخادم حرفيّاً */}
        <section className="rounded-2xl border p-3" style={{ ...sectionStyle, borderColor: '#7c2d12' }}>
          <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
            <Send className="w-4 h-4 text-orange-300" aria-hidden="true" /> تنفيذ قرار توزيع (محروس)
            <span className="text-[11px] font-normal" style={{ color: T.faint }}>· يُدرِج READY في طابور المُشغِّل فقط — لا إطلاق مباشراً للأجهزة</span>
          </div>
          <div className="text-[11px] mb-2" style={{ color: T.muted }}>
            الحواجز والموافقات ومفتاح إيقاف الطوارئ يفرضها الخادم (fail-closed) —
            قرار محجوب/بانتظار موافقة يُسجَّل ولا يُنفَّذ.
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <input value={exRecId} onChange={(e) => setExRecId(e.target.value)} placeholder="معرّف التوصية" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <select value={exAction} onChange={(e) => setExAction(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={exRisk} onChange={(e) => setExRisk(e.target.value)} className="px-2 py-1 rounded-lg" style={inputStyle}>
              {RISKS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <input value={exFieldId} onChange={(e) => setExFieldId(e.target.value)} placeholder="معرّف الحقل (اختياريّ)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <input value={exDeviceId} onChange={(e) => setExDeviceId(e.target.value)} placeholder="جهاز (لقرار READY)" className="w-36 px-2 py-1 rounded-lg" style={inputStyle} />
            <input value={exCommand} onChange={(e) => setExCommand(e.target.value)} placeholder="أمر (لقرار READY)" className="w-32 px-2 py-1 rounded-lg" style={inputStyle} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <label className="inline-flex items-center gap-1">
              اكتب «{EXECUTE_CONFIRM_PHRASE}» للتأكيد:
              <input value={exConfirm} onChange={(e) => setExConfirm(e.target.value)} className="w-20 px-2 py-1 rounded-lg" style={inputStyle} />
            </label>
            <button
              type="button"
              onClick={runExecute}
              disabled={!exReady || executeM.isPending}
              className="px-2.5 py-1 rounded-lg font-semibold disabled:opacity-50"
              style={{ border: '1px solid #7c2d12', color: '#fdba74', background: 'rgba(15,23,42,.45)' }}
            >
              {executeM.isPending ? 'جارٍ التنفيذ…' : 'نفّذ عبر الموزِّع المحروس'}
            </button>
          </div>
          {executeM.isError && <HonestError error={executeM.error} gated />}
          {executeM.data && (
            <div className="mt-2 flex flex-col gap-1 text-[11px]" style={{ color: T.muted }}>
              <div>
                <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: executionStatusColor(executeM.data.status) }}>
                  {executionStatusLabel(executeM.data.status)}
                </span>
                <span className="mr-1" style={{ color: T.faint }}> · حالة التوزيع: {executeM.data.dispatch_state}</span>
                {executeM.data.replayed && <span style={{ color: T.faint }}> · أُعيد قرار حيّ قائم — لم يُدرَج جديد</span>}
              </div>
              {/* حكم الخادم وأسبابه تُعرَض حرفيّاً — بما فيها الحجب/مفتاح الطوارئ. */}
              {executeM.data.reason_ar && <div>{executeM.data.reason_ar}</div>}
              {Array.isArray(executeM.data.audit?.halt_breaches) && (executeM.data.audit?.halt_breaches ?? []).length > 0 && (
                <div style={{ color: '#fca5a5' }}>
                  خروق حاجبة: {(executeM.data.audit?.halt_breaches ?? []).map(String).join('، ')}
                </div>
              )}
              {typeof executeM.data.audit?.required_approvals === 'number' && (
                <div style={{ color: T.faint }}>
                  موافقات: {executeM.data.audit?.approvals_collected ?? '—'}/{executeM.data.audit?.required_approvals}
                </div>
              )}
              {executeM.data.decision_id && (
                <div style={{ color: T.faint }}>أثر التدقيق: <span className="font-mono">{executeM.data.decision_id}</span></div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
