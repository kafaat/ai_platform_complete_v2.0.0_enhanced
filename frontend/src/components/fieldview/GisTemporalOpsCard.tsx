import { useMemo, useState } from 'react';
import {
  Beaker, CalendarClock, ChevronDown, ChevronLeft, Clock, FlaskConical,
  Hexagon, History, Link2, MapPin, Scissors, ShieldAlert,
} from 'lucide-react';
import {
  useGisBuffer, useGisSplit, useGisUnion, useGisValidate,
  useLineageLink, useReplayReconstruct, useSimulateWhatIf,
  useStageRiskCheck, useTemporalCheck, useTemporalCoherence, useTrialAnalyze,
  type TemporalMeasurementInput, type TrialBlockInput,
} from '../../hooks/useGisTemporalOps';
import {
  bufferFacts, coherenceFacts, parseJsonObject, replayFacts, severityColor,
  splitFacts, stageCheckHazards, temporalCheckFacts, temporalCheckIssues,
  trialFacts, unionFacts, validateFacts, whatIfFacts, type OpFact,
} from '../../lib/gisTemporalOps';
import { T } from '../ds';

interface Props {
  /** الحقل النشط — تحتاجه المحاكاة (field_id إلزاميّ) وتقبله عمليّات GIS بدل لصق الهندسة.
   *  null ⇒ حالة «اختر حقلاً» حيث السياق مرتبط بحقل. */
  fieldId?: string | null;
  /** تسمية محصول الحقل — سياق عرض/افتراض محصول للمحاكاة (لا حكم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

const CARD_BG = 'rgba(15,23,42,.35)';
const SUB_BG = 'rgba(2,6,23,.5)';

type SectionKey = 'gis' | 'temporal' | 'whatif' | 'stage' | 'replay' | 'lineage' | 'trial';

/** أقاليم مخاطر الخادم (مفاتيح API؛ الاسم العربيّ يعود من الردّ zone_name_ar). */
const ZONE_KEYS = ['tihama', 'western_highlands', 'central_highlands', 'eastern_plateau', 'inland_desert', 'southern_coast'];
/** مصادر البيانات الزمنيّة (قيم DataSource كما في temporal_arbitration.py). */
const SOURCE_KEYS = ['ndvi_sentinel', 'ndwi_sentinel', 'soil_moisture_sat', 'weather_eto', 'weather_rain', 'weather_temp', 'soil_lab', 'soil_sensor', 'user_observation', 'yield_harvest'];

/** رسالة خطأ صادقة من ردّ الخادم (detail) دون تلفيق — للـ422/403/5xx (لا 404 المُبتلَع). */
function errText(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return 'تعذّرت العمليّة — تحقّق من صحّة المُدخَل أو توفّر الخدمة.';
}

/** رأس قسم قابل للطيّ — RTL: سهم يسار = مفتوح. */
function SectionHeader({ icon, title, open, onToggle }: { icon: React.ReactNode; title: string; open: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center justify-between gap-2 rounded-xl border px-2.5 py-1.5" style={{ borderColor: T.line, background: CARD_BG }}>
      <span className="inline-flex items-center gap-2 text-[12px] font-bold" style={{ color: T.ink }}>{icon} {title}</span>
      {open ? <ChevronDown className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" /> : <ChevronLeft className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />}
    </button>
  );
}

function FactPills({ facts }: { facts: OpFact[] }) {
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

function LabeledInput({ id, label, value, onChange, type = 'text', placeholder, width = 'w-24' }: {
  id: string; label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; width?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1">
      <label htmlFor={id} className="text-[11px] font-bold" style={{ color: T.ink }}>{label}:</label>
      <input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder ?? 'من قياس'} className={`${width} ${inputCls}`} style={inputStyle} {...(type === 'number' ? { step: 'any' } : {})} />
    </span>
  );
}

/** منطقة لصق GeoJSON (LTR أحاديّ المسافة) — الحارس النقيّ يعرض خطأً صادقاً. */
function GeoTextarea({ value, onChange, placeholder, rows = 3 }: { value: string; onChange: (v: string) => void; placeholder: string; rows?: number }) {
  return (
    <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} rows={rows} className="w-full px-2 py-1 rounded-lg text-[11px] font-mono" style={inputStyle} dir="ltr" />
  );
}

/** زرّ حساب صريح — يمنع إطلاق العمليّة قبل جاهزيّة المُدخَل. */
function RunButton({ onClick, disabled, pending, label = 'احسب' }: { onClick: () => void; disabled: boolean; pending: boolean; label?: string }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled || pending} className="px-2 py-0.5 rounded-lg text-[11px] font-semibold disabled:opacity-40" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: 'rgba(15,23,42,.45)' }}>
      {pending ? '…' : label}
    </button>
  );
}

const disabledMsg = <div className="text-[11px]" style={{ color: T.muted }}>هذه الميزة غير مُفعَّلة على الخادم بعد (محروسة بعَلَم).</div>;

/**
 * بطاقة عمليّات GIS/الزمن (Agronomist P3): تعكس طبقة backend يتيمة لم يكن لها قارئ واجهة —
 * عمليّات نواة GIS الهندسيّة (buffer/union/split/validate، dry-run محروسة بعَلَم — تختلف عن
 * كتالوج OGC/STAC في GisExpertPage) · التحكيم الزمني (اتّساق + مرجع موحّد) · محاكاة ماذا-لو ·
 * مخاطر مرحلة موسميّة · إعادة بناء من الأحداث · رابط النَّسَب (محروس) · تحليل تجربة حقليّة.
 * صدق صارم: الأحكام/النصوص/الأرقام من الخادم حرفيّاً؛ الأقسام قابلة للطيّ والعمليّات لا تُطلَق
 * إلّا بضغطة صريحة (تفادي حساب PostGIS/WOFOST على مُدخَل نصفيّ)؛ 404 ⇒ «غير مُفعَّل» صادق؛
 * الهندسة تُلخَّص (نوع/رؤوس/أجزاء) لا تُرسَم كمحرّر؛ الأقسام المرتبطة بحقل تعرض «اختر حقلاً».
 */
export default function GisTemporalOpsCard({ fieldId, cropLabel, enabled = true }: Props) {
  const [open, setOpen] = useState<Set<SectionKey>>(new Set());
  const isOpen = (k: SectionKey) => open.has(k);
  const toggle = (k: SectionKey) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });

  // ── عمليّات نواة GIS ──
  const [vText, setVText] = useState('');
  const [vUseField, setVUseField] = useState(false);
  const validateMut = useGisValidate();
  const vGeo = useMemo(() => parseJsonObject(vText), [vText]);

  const [bText, setBText] = useState('');
  const [bUseField, setBUseField] = useState(false);
  const [bDist, setBDist] = useState('');
  const bufferMut = useGisBuffer();
  const bGeo = useMemo(() => parseJsonObject(bText), [bText]);
  const bDistNum = useMemo(() => { const n = Number(bDist); return bDist.trim() !== '' && Number.isFinite(n) ? n : null; }, [bDist]);

  const [sText, setSText] = useState('');
  const [sUseField, setSUseField] = useState(false);
  const [sBlade, setSBlade] = useState('');
  const splitMut = useGisSplit();
  const sGeo = useMemo(() => parseJsonObject(sText), [sText]);
  const sBladeGeo = useMemo(() => parseJsonObject(sBlade), [sBlade]);

  const [uTextA, setUTextA] = useState('');
  const [uTextB, setUTextB] = useState('');
  const [uUseFieldA, setUUseFieldA] = useState(false);
  const unionMut = useGisUnion();
  const uGeoA = useMemo(() => parseJsonObject(uTextA), [uTextA]);
  const uGeoB = useMemo(() => parseJsonObject(uTextB), [uTextB]);

  // ── التحكيم الزمني ──
  const [measurements, setMeasurements] = useState<TemporalMeasurementInput[]>([]);
  const [mSource, setMSource] = useState(SOURCE_KEYS[0]);
  const [mTs, setMTs] = useState('');
  const [mVal, setMVal] = useState('');
  const [tcCrop, setTcCrop] = useState('');
  const [tcStage, setTcStage] = useState('');
  const checkMut = useTemporalCheck();
  const addMeasurement = () => {
    if (!mTs.trim()) return;
    const v = Number(mVal);
    setMeasurements((prev) => [...prev, { source: mSource, timestamp: mTs.trim(), value: mVal.trim() !== '' && Number.isFinite(v) ? v : null }]);
    setMTs(''); setMVal('');
  };

  const [cohCur, setCohCur] = useState('');
  const [cohPlant, setCohPlant] = useState('');
  const [cohGdd, setCohGdd] = useState('');
  const coherenceMut = useTemporalCoherence();

  // ── محاكاة ماذا-لو (مرتبطة بحقل) ──
  const [wLat, setWLat] = useState('');
  const [wLon, setWLon] = useState('');
  const [wCrop, setWCrop] = useState('');
  const [wSoil, setWSoil] = useState('loam');
  const [wPlant, setWPlant] = useState('');
  const [wScenario, setWScenario] = useState('reduce_irrigation');
  const whatIfMut = useSimulateWhatIf();
  const wLatNum = Number(wLat); const wLonNum = Number(wLon);
  const wReady = !!fieldId && wLat.trim() !== '' && wLon.trim() !== '' && Number.isFinite(wLatNum) && Number.isFinite(wLonNum);

  // ── مخاطر المرحلة الموسميّة (GET) ──
  const [zone, setZone] = useState(ZONE_KEYS[0]);
  const [stageAr, setStageAr] = useState('');
  const stageQ = useStageRiskCheck(zone, stageAr.trim() || null, isOpen('stage'));

  // ── إعادة البناء من الأحداث ──
  const [rEntityType, setREntityType] = useState('field');
  const [rEvents, setREvents] = useState('');
  const replayMut = useReplayReconstruct();
  const rEventsParsed = useMemo<{ arr: Array<Record<string, unknown>> | null; error: string | null }>(() => {
    const t = rEvents.trim();
    if (t === '') return { arr: null, error: null };
    try {
      const p = JSON.parse(t);
      if (!Array.isArray(p)) return { arr: null, error: 'الأحداث يجب أن تكون مصفوفة JSON.' };
      return { arr: p as Array<Record<string, unknown>>, error: null };
    } catch { return { arr: null, error: 'JSON غير صالح — تحقّق من الصيغة.' }; }
  }, [rEvents]);

  // ── رابط النَّسَب (محروس) ──
  const [lRefType, setLRefType] = useState('decision');
  const [lRefId, setLRefId] = useState('');
  const [lLineageId, setLLineageId] = useState('');
  const lineageMut = useLineageLink();

  // ── تحليل التجربة الحقليّة ──
  const [blocks, setBlocks] = useState<TrialBlockInput[]>([]);
  const [tbNum, setTbNum] = useState('');
  const [tbTreat, setTbTreat] = useState('');
  const [tbCtrl, setTbCtrl] = useState('');
  const [tLabel, setTLabel] = useState('');
  const trialMut = useTrialAnalyze();
  const addBlock = () => {
    const n = Number(tbNum), tr = Number(tbTreat), ct = Number(tbCtrl);
    if (!Number.isFinite(n) || !Number.isFinite(tr) || !Number.isFinite(ct) || tbNum.trim() === '' || tbTreat.trim() === '' || tbCtrl.trim() === '') return;
    setBlocks((prev) => [...prev, { block_number: n, treatment_yield: tr, control_yield: ct }]);
    setTbNum(''); setTbTreat(''); setTbCtrl('');
  };

  if (!enabled) return null;

  const noField = <div className="text-[11px]" style={{ color: T.faint }}>اختر حقلاً لعرض هذا القسم.</div>;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="gis-temporal-ops" aria-label="عمليّات الهندسة والزمن">
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Hexagon className="w-4 h-4 text-sky-300" aria-hidden="true" /> عمليّات الهندسة والزمن (أدوات المهندس الزراعيّ)
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {/* ═══ عمليّات نواة GIS (dry-run، محروسة بعَلَم) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Hexagon className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="عمليّات هندسيّة (buffer/union/split/validate — معاينة)" open={isOpen('gis')} onToggle={() => toggle('gis')} />
          {isOpen('gis') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>معاينة dry-run في PostGIS دون كتابة fields.geom. الصق GeoJSON (Geometry/Feature/FeatureCollection بعنصر واحد) أو استعمل حدود الحقل المختار. النتيجة تُلخَّص (نوع/رؤوس/أجزاء) لا تُرسَم.</div>

              {/* validate */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>فحص/إصلاح الطوبولوجيا (ST_IsValid + ST_MakeValid)</div>
                {fieldId && <label className="text-[10px] inline-flex items-center gap-1" style={{ color: T.muted }}><input type="checkbox" checked={vUseField} onChange={(e) => setVUseField(e.target.checked)} /> استعمل حدود الحقل المختار</label>}
                {!vUseField && <GeoTextarea value={vText} onChange={setVText} placeholder='{"type":"Polygon","coordinates":[[[44,15],[44.1,15],[44.1,15.1],[44,15]]]}' />}
                {!vUseField && vGeo.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{vGeo.error}</div>}
                <RunButton pending={validateMut.isPending} disabled={vUseField ? !fieldId : !vGeo.obj} onClick={() => validateMut.mutate(vUseField && fieldId ? { field_id: fieldId } : { geometry: vGeo.obj })} label="افحص" />
                {validateMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(validateMut.error)}</div>}
                {validateMut.data?.disabled ? disabledMsg : validateMut.data ? (
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-[11px]"><span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: validateMut.data.is_valid ? '#86efac' : '#fca5a5', border: `1px solid ${T.line}` }}>{validateMut.data.is_valid ? 'صالح' : 'غير صالح'}</span></div>
                    <FactPills facts={validateFacts(validateMut.data)} />
                  </div>
                ) : null}
              </div>

              {/* buffer */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>توسيع/تقليص (ST_Buffer — بالأمتار على geography)</div>
                {fieldId && <label className="text-[10px] inline-flex items-center gap-1" style={{ color: T.muted }}><input type="checkbox" checked={bUseField} onChange={(e) => setBUseField(e.target.checked)} /> استعمل حدود الحقل المختار</label>}
                {!bUseField && <GeoTextarea value={bText} onChange={setBText} placeholder='هندسة GeoJSON…' rows={2} />}
                {!bUseField && bGeo.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{bGeo.error}</div>}
                <LabeledInput id="gis-buf-dist" label="المسافة (م، قد تكون سالبة)" value={bDist} onChange={setBDist} type="number" width="w-20" placeholder="مثلاً 10" />
                <RunButton pending={bufferMut.isPending} disabled={bDistNum == null || (bUseField ? !fieldId : !bGeo.obj)} onClick={() => bufferMut.mutate({ ...(bUseField && fieldId ? { field_id: fieldId } : { geometry: bGeo.obj }), distance_m: bDistNum as number })} />
                {bufferMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(bufferMut.error)}</div>}
                {bufferMut.data?.disabled ? disabledMsg : bufferMut.data ? <FactPills facts={bufferFacts(bufferMut.data)} /> : null}
              </div>

              {/* split */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>تقسيم بشفرة خطّيّة (ST_Split)</div>
                {fieldId && <label className="text-[10px] inline-flex items-center gap-1" style={{ color: T.muted }}><input type="checkbox" checked={sUseField} onChange={(e) => setSUseField(e.target.checked)} /> استعمل حدود الحقل المختار كهندسة مُستهدَفة</label>}
                {!sUseField && <GeoTextarea value={sText} onChange={setSText} placeholder='الهندسة المُستهدَفة (GeoJSON)…' rows={2} />}
                {!sUseField && sGeo.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{sGeo.error}</div>}
                <GeoTextarea value={sBlade} onChange={setSBlade} placeholder='شفرة القطع — خطّ فقط: {"type":"LineString","coordinates":[[44,15],[44.1,15.1]]}' rows={2} />
                {sBladeGeo.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{sBladeGeo.error}</div>}
                <RunButton pending={splitMut.isPending} disabled={!sBladeGeo.obj || (sUseField ? !fieldId : !sGeo.obj)} onClick={() => splitMut.mutate({ ...(sUseField && fieldId ? { field_id: fieldId } : { geometry: sGeo.obj }), blade: sBladeGeo.obj as object })} label="قسّم" />
                {splitMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(splitMut.error)}</div>}
                {splitMut.data?.disabled ? disabledMsg : splitMut.data ? <FactPills facts={splitFacts(splitMut.data)} /> : null}
              </div>

              {/* union */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>دمج هندستين (ST_Union / merge)</div>
                {fieldId && <label className="text-[10px] inline-flex items-center gap-1" style={{ color: T.muted }}><input type="checkbox" checked={uUseFieldA} onChange={(e) => setUUseFieldA(e.target.checked)} /> الهندسة الأولى = حدود الحقل المختار</label>}
                {!uUseFieldA && <GeoTextarea value={uTextA} onChange={setUTextA} placeholder='الهندسة الأولى (GeoJSON)…' rows={2} />}
                {!uUseFieldA && uGeoA.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{uGeoA.error}</div>}
                <GeoTextarea value={uTextB} onChange={setUTextB} placeholder='الهندسة الثانية (GeoJSON)…' rows={2} />
                {uGeoB.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{uGeoB.error}</div>}
                <RunButton pending={unionMut.isPending} disabled={!uGeoB.obj || (uUseFieldA ? !fieldId : !uGeoA.obj)} onClick={() => unionMut.mutate({ ...(uUseFieldA && fieldId ? { field_id_a: fieldId } : { geometry_a: uGeoA.obj }), geometry_b: uGeoB.obj })} label="ادمج" />
                {unionMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(unionMut.error)}</div>}
                {unionMut.data?.disabled ? disabledMsg : unionMut.data ? <FactPills facts={unionFacts(unionMut.data)} /> : null}
              </div>
            </div>
          )}
        </div>

        {/* ═══ التحكيم الزمني ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Clock className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="التحكيم الزمني (اتّساق + مرجع موحّد)" open={isOpen('temporal')} onToggle={() => toggle('temporal')} />
          {isOpen('temporal') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {/* check */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>اتّساق القراءات (لا NDVI قديم مع ET₀ حديث)</div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1"><label htmlFor="tc-src" className="text-[11px] font-bold" style={{ color: T.ink }}>المصدر:</label>
                    <select id="tc-src" value={mSource} onChange={(e) => setMSource(e.target.value)} className={inputCls} style={inputStyle}>{SOURCE_KEYS.map((k) => <option key={k} value={k}>{k}</option>)}</select></span>
                  <LabeledInput id="tc-ts" label="الوقت (ISO)" value={mTs} onChange={setMTs} placeholder="2026-06-01T00:00:00Z" width="w-40" />
                  <LabeledInput id="tc-val" label="القيمة" value={mVal} onChange={setMVal} type="number" width="w-16" placeholder="اختياريّ" />
                  <button type="button" onClick={addMeasurement} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف قراءة</button>
                </div>
                {measurements.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {measurements.map((m, i) => <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>{m.source} · {m.timestamp}{m.value != null ? ` · ${m.value}` : ''}</span>)}
                    <button type="button" onClick={() => setMeasurements([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <LabeledInput id="tc-crop" label="المحصول" value={tcCrop} onChange={setTcCrop} placeholder={cropLabel || 'اختياريّ'} width="w-24" />
                  <LabeledInput id="tc-stage" label="المرحلة" value={tcStage} onChange={setTcStage} placeholder="اختياريّ" width="w-24" />
                  <RunButton pending={checkMut.isPending} disabled={measurements.length === 0} onClick={() => checkMut.mutate({ measurements, crop: tcCrop.trim() || null, stage: tcStage.trim() || null })} label="افحص الاتّساق" />
                </div>
                {measurements.length === 0 && <div className="text-[11px]" style={{ color: T.faint }}>أضِف قراءتين على الأقلّ (مصدر + وقت) لفحص الاتّساق الزمني.</div>}
                {checkMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(checkMut.error)}</div>}
                {checkMut.data?.disabled ? disabledMsg : checkMut.data ? (
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-[11px]"><span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: checkMut.data.valid ? '#86efac' : '#fca5a5', border: `1px solid ${T.line}` }}>{checkMut.data.valid ? 'متّسق زمنيّاً' : 'يوجد تعارض زمني'}</span></div>
                    <FactPills facts={temporalCheckFacts(checkMut.data)} />
                    {temporalCheckIssues(checkMut.data).map((iss, i) => (
                      <div key={i} className="text-[11px]" style={{ color: T.muted }}>
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: severityColor(iss.severity), border: `1px solid ${T.line}` }}>{iss.severity ?? '—'}</span> {iss.message_ar ?? iss.code}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              {/* coherence */}
              <div className="flex flex-col gap-1.5 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                <div className="text-[11px] font-bold" style={{ color: T.ink }}>مرجع زمني موحّد + كشف انحراف GDD</div>
                <div className="flex flex-wrap items-center gap-2">
                  <LabeledInput id="coh-cur" label="التاريخ الحالي" value={cohCur} onChange={setCohCur} type="date" width="w-36" placeholder="" />
                  <LabeledInput id="coh-plant" label="تاريخ الزراعة" value={cohPlant} onChange={setCohPlant} type="date" width="w-36" placeholder="" />
                  <LabeledInput id="coh-gdd" label="أيّام GDD المعدودة" value={cohGdd} onChange={setCohGdd} type="number" width="w-16" placeholder="اختياريّ" />
                  <RunButton pending={coherenceMut.isPending} disabled={!cohCur.trim()} onClick={() => coherenceMut.mutate({ current_date: cohCur.trim(), planting_date: cohPlant.trim() || null, gdd_days_counted: cohGdd.trim() !== '' ? Number(cohGdd) : null })} />
                </div>
                {!cohCur.trim() && <div className="text-[11px]" style={{ color: T.faint }}>أدخِل التاريخ الحالي (YYYY-MM-DD) لبناء المرجع الزمني الموحّد.</div>}
                {coherenceMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(coherenceMut.error)}</div>}
                {coherenceMut.data?.disabled ? disabledMsg : coherenceMut.data ? (
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-[11px]"><span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: coherenceMut.data.coherence?.coherent ? '#86efac' : '#fca5a5', border: `1px solid ${T.line}` }}>{coherenceMut.data.coherence?.coherent ? 'متماسك' : 'انحراف دلاليّ'}</span></div>
                    <FactPills facts={coherenceFacts(coherenceMut.data)} />
                    {coherenceMut.data.coherence?.detail_ar && <div className="text-[11px]" style={{ color: T.muted }}>{coherenceMut.data.coherence.detail_ar}</div>}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>

        {/* ═══ محاكاة ماذا-لو (مرتبطة بحقل) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<FlaskConical className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="محاكاة ماذا-لو (WOFOST — أثر تقليل/إيقاف الريّ)" open={isOpen('whatif')} onToggle={() => toggle('whatif')} />
          {isOpen('whatif') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              {!fieldId ? noField : (
                <>
                  <div className="text-[10px]" style={{ color: T.faint }}>lat/lon إلزاميّان للطقس الحيّ — لا محاكاة بلا موقع (يعلن الخادم التعذّر بدل اختلاق أرقام).</div>
                  <div className="flex flex-wrap items-center gap-2">
                    <LabeledInput id="wi-lat" label="خط العرض" value={wLat} onChange={setWLat} type="number" width="w-20" placeholder="15.05" />
                    <LabeledInput id="wi-lon" label="خط الطول" value={wLon} onChange={setWLon} type="number" width="w-20" placeholder="45.55" />
                    <LabeledInput id="wi-crop" label="المحصول" value={wCrop} onChange={setWCrop} placeholder={cropLabel || 'قمح صلب'} width="w-24" />
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <LabeledInput id="wi-soil" label="نوع التربة" value={wSoil} onChange={setWSoil} placeholder="loam" width="w-20" />
                    <LabeledInput id="wi-plant" label="تاريخ الزراعة" value={wPlant} onChange={setWPlant} type="date" width="w-36" placeholder="" />
                    <span className="inline-flex items-center gap-1"><label htmlFor="wi-scn" className="text-[11px] font-bold" style={{ color: T.ink }}>السيناريو:</label>
                      <select id="wi-scn" value={wScenario} onChange={(e) => setWScenario(e.target.value)} className={inputCls} style={inputStyle}><option value="reduce_irrigation">تقليل الريّ</option><option value="no_irrigation">إيقاف الريّ</option></select></span>
                    <RunButton pending={whatIfMut.isPending} disabled={!wReady} onClick={() => whatIfMut.mutate({ field_id: fieldId, lat: wLatNum, lon: wLonNum, crop: wCrop.trim() || cropLabel || undefined, soil_type: wSoil.trim() || 'loam', planting_date: wPlant.trim() || null, scenario: wScenario })} label="حاكِ" />
                  </div>
                  {!wReady && <div className="text-[11px]" style={{ color: T.faint }}>أدخِل خطّي العرض والطول (إلزاميّان للطقس الحيّ).</div>}
                  {whatIfMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(whatIfMut.error)}</div>}
                  {whatIfMut.data?.disabled ? disabledMsg : whatIfMut.data ? (
                    whatIfMut.data.available ? (
                      <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                        {whatIfMut.data.recommended_action_helps != null && <div className="text-[11px]"><span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: whatIfMut.data.recommended_action_helps ? '#86efac' : '#fdba74', border: `1px solid ${T.line}` }}>{whatIfMut.data.recommended_action_helps ? 'الإجراء المقترَح يرفع المحصول >2%' : 'الإجراء المقترَح لا يُجدي بوضوح'}</span></div>}
                        <FactPills facts={whatIfFacts(whatIfMut.data)} />
                      </div>
                    ) : (
                      <div className="text-[11px]" style={{ color: T.muted }}>{whatIfMut.data.note_ar || whatIfMut.data.error || 'المحاكاة غير متاحة (طقس/نموذج).'}</div>
                    )
                  ) : null}
                </>
              )}
            </div>
          )}
        </div>

        {/* ═══ مخاطر المرحلة الموسميّة (GET) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<ShieldAlert className="w-4 h-4 text-amber-300" aria-hidden="true" />} title="مخاطر مرحلة نموّ في إقليم" open={isOpen('stage')} onToggle={() => toggle('stage')} />
          {isOpen('stage') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1"><label htmlFor="sr-zone" className="text-[11px] font-bold" style={{ color: T.ink }}>الإقليم:</label>
                  <select id="sr-zone" value={zone} onChange={(e) => setZone(e.target.value)} className={inputCls} style={inputStyle}>{ZONE_KEYS.map((k) => <option key={k} value={k}>{k}</option>)}</select></span>
                <LabeledInput id="sr-stage" label="المرحلة (عربيّ)" value={stageAr} onChange={setStageAr} placeholder="الإزهار / الحصاد …" width="w-28" />
              </div>
              {!stageAr.trim() ? (
                <div className="text-[11px]" style={{ color: T.faint }}>أدخِل مرحلة النموّ (مثلاً «الإزهار») لفحص مخاطرها في الإقليم.</div>
              ) : stageQ.isLoading ? (
                <div className="text-[11px]" style={{ color: T.faint }}>جارٍ فحص مخاطر المرحلة…</div>
              ) : stageQ.data?.disabled ? disabledMsg : stageQ.data ? (
                stageQ.data.supported === false ? (
                  <div className="text-[11px]" style={{ color: T.muted }}>{stageQ.data.message_ar || 'إقليم غير معروف.'}</div>
                ) : (
                  <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      {stageQ.data.zone_name_ar && <span className="font-bold" style={{ color: T.ink }}>{stageQ.data.zone_name_ar}</span>}
                      {stageQ.data.risk_level_ar && <span style={{ color: T.faint }}>{stageQ.data.risk_level_ar}</span>}
                    </div>
                    {stageCheckHazards(stageQ.data).map((h, i) => (
                      <div key={i} className="text-[11px]" style={{ color: T.muted }}>
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: severityColor(h.severity), border: `1px solid ${T.line}` }}>{h.severity ?? '—'}</span> {h.hazard_ar} — {h.risk_to_ar} <span style={{ color: T.faint }}>({h.season_ar})</span>
                      </div>
                    ))}
                    {stageQ.data.advice_ar && <div className="text-[11px]" style={{ color: T.muted }}>{stageQ.data.advice_ar}</div>}
                    {stageQ.data.disclaimer_ar && <div className="text-[10px]" style={{ color: T.faint }}>{stageQ.data.disclaimer_ar}</div>}
                  </div>
                )
              ) : null}
            </div>
          )}
        </div>

        {/* ═══ إعادة البناء من الأحداث ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<History className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="إعادة بناء الحالة من الأحداث (event replay)" open={isOpen('replay')} onToggle={() => toggle('replay')} />
          {isOpen('replay') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>إعادة بناء نقيّة من أحداث تُمرَّرها هنا (لا جلب من قاعدة الأحداث بعد). كلّ حدث: {'{event_type, occurred_at, payload}'}.</div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex flex-col gap-0.5 text-[10px]" style={{ color: T.faint }}>
                  نوع الكيان
                  <select value={rEntityType} onChange={(e) => setREntityType(e.target.value)} className="w-24 px-2 py-1 rounded-lg text-[11px]" style={inputStyle}>
                    <option value="field">field</option>
                  </select>
                </label>
                <div className="flex flex-col gap-0.5 text-[10px]" style={{ color: T.faint }}>
                  الحقل
                  <span className="w-40 px-2 py-1 rounded-lg font-mono text-[11px]" style={{ border: `1px solid ${T.line}`, color: fieldId ? T.ink : '#fbbf24', background: SUB_BG }}>
                    {fieldId ?? 'اختر حقلاً من أعلى مساحة العمل'}
                  </span>
                </div>
              </div>
              <GeoTextarea value={rEvents} onChange={setREvents} placeholder='[{"event_type":"FIELD_CREATED","occurred_at":"2026-01-01T00:00:00Z","payload":{}}]' />
              {rEventsParsed.error && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{rEventsParsed.error}</div>}
              <RunButton pending={replayMut.isPending} disabled={!fieldId || !rEntityType.trim() || !rEventsParsed.arr} onClick={() => fieldId && replayMut.mutate({ entity_type: rEntityType.trim(), entity_id: fieldId, events: rEventsParsed.arr as Array<Record<string, unknown>> })} label="أعِد البناء" />
              {replayMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(replayMut.error)}</div>}
              {replayMut.data?.disabled ? disabledMsg : replayMut.data ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="text-[11px] font-bold" style={{ color: T.ink }}>{replayMut.data.field_name || replayMut.data.entity_id}</div>
                  <FactPills facts={replayFacts(replayMut.data)} />
                  {replayMut.data.last_event_at && <div className="text-[10px]" style={{ color: T.faint }}>آخر حدث: {replayMut.data.last_event_at}</div>}
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* ═══ رابط النَّسَب (محروس بعَلَم) ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Link2 className="w-4 h-4 text-emerald-300" aria-hidden="true" />} title="رابط النَّسَب الموحّد (يربط مرجعاً بسلسلة lin_)" open={isOpen('lineage')} onToggle={() => toggle('lineage')} />
          {isOpen('lineage') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>ربط إضافيّ فوق المعرّفات القائمة (لا إعادة تسمية) — يُسَكّ lineage_id إن غاب. آمن متكرّر (idempotent).</div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1"><label htmlFor="ln-type" className="text-[11px] font-bold" style={{ color: T.ink }}>نوع المرجع:</label>
                  <select id="ln-type" value={lRefType} onChange={(e) => setLRefType(e.target.value)} className={inputCls} style={inputStyle}>{['decision', 'dispatch', 'command', 'execution', 'outcome'].map((k) => <option key={k} value={k}>{k}</option>)}</select></span>
                <LabeledInput id="ln-id" label="معرّف المرجع" value={lRefId} onChange={setLRefId} placeholder="dec_… / disp_…" width="w-28" />
                <LabeledInput id="ln-lin" label="سلسلة نَسَب (اختياريّ)" value={lLineageId} onChange={setLLineageId} placeholder="lin_… (يُسَكّ إن غاب)" width="w-36" />
                <RunButton pending={lineageMut.isPending} disabled={!lRefId.trim()} onClick={() => lineageMut.mutate({ ref_type: lRefType, ref_id: lRefId.trim(), lineage_id: lLineageId.trim() || null })} label="اربط" />
              </div>
              {!lRefId.trim() && <div className="text-[11px]" style={{ color: T.faint }}>أدخِل معرّف مرجع قائم (قرار/توزيع/أمر/تنفيذ/نتيجة) لربطه.</div>}
              {lineageMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(lineageMut.error)}</div>}
              {lineageMut.data?.disabled ? disabledMsg : lineageMut.data?.lineage_id ? (
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#86efac' }}>رُبِط: {lineageMut.data.lineage_id}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>{lineageMut.data.ref_type}:{lineageMut.data.ref_id}</span>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* ═══ تحليل التجربة الحقليّة ═══ */}
        <div className="flex flex-col gap-1.5">
          <SectionHeader icon={<Beaker className="w-4 h-4 text-sky-300" aria-hidden="true" />} title="تحليل تجربة مقترنة (t-test مزدوج + LSD)" open={isOpen('trial')} onToggle={() => toggle('trial')} />
          {isOpen('trial') && (
            <div className="flex flex-col gap-2 rounded-xl border p-2" style={{ borderColor: T.line, background: CARD_BG }}>
              <div className="text-[10px]" style={{ color: T.faint }}>أدخِل كتلاً مقترنة (معالجة مقابل شاهد). معيار SARE: ٤ كتل على الأقلّ للصحّة الإحصائيّة (الخادم يحكم).</div>
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="tr-num" label="رقم الكتلة" value={tbNum} onChange={setTbNum} type="number" width="w-14" />
                <LabeledInput id="tr-treat" label="غلّة المعالجة" value={tbTreat} onChange={setTbTreat} type="number" width="w-16" />
                <LabeledInput id="tr-ctrl" label="غلّة الشاهد" value={tbCtrl} onChange={setTbCtrl} type="number" width="w-16" />
                <button type="button" onClick={addBlock} className="text-[11px] px-2 py-0.5 rounded-lg font-semibold" style={{ border: `1px solid ${T.line}`, color: '#86efac', background: SUB_BG }}>+ أضِف كتلة</button>
              </div>
              {blocks.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {blocks.map((b, i) => <span key={i} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>#{b.block_number}: {b.treatment_yield} / {b.control_yield}</span>)}
                  <button type="button" onClick={() => setBlocks([])} className="text-[10px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: '#fca5a5' }}>مسح</button>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <LabeledInput id="tr-label" label="تسمية المعالجة" value={tLabel} onChange={setTLabel} placeholder="المعالجة الجديدة" width="w-32" />
                <RunButton pending={trialMut.isPending} disabled={blocks.length === 0} onClick={() => trialMut.mutate({ blocks, treatment_label_ar: tLabel.trim() || undefined })} label="حلّل" />
              </div>
              {blocks.length === 0 && <div className="text-[11px]" style={{ color: T.faint }}>أضِف كتلة واحدة على الأقلّ (الخادم يرفض ما دون ٤ كتل بحكم صادق).</div>}
              {trialMut.isError && <div className="text-[11px]" style={{ color: '#fca5a5' }}>{errText(trialMut.error)}</div>}
              {trialMut.data?.disabled ? disabledMsg : trialMut.data && !trialMut.data.disabled ? (
                <div className="flex flex-col gap-1 rounded-lg border p-1.5" style={{ borderColor: T.line, background: SUB_BG }}>
                  <div className="flex items-center gap-2 text-[11px]"><span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold" style={{ color: trialMut.data.is_significant ? '#86efac' : '#fdba74', border: `1px solid ${T.line}` }}>{trialMut.data.is_significant ? 'فرق دالّ إحصائيّاً' : 'الفرق غير دالّ'}</span></div>
                  <FactPills facts={trialFacts(trialMut.data)} />
                  {trialMut.data.verdict_ar && <div className="text-[11px]" style={{ color: T.muted }}>{trialMut.data.verdict_ar}</div>}
                  {trialMut.data.recommendation_ar && <div className="text-[11px]" style={{ color: T.muted }}>{trialMut.data.recommendation_ar}</div>}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
