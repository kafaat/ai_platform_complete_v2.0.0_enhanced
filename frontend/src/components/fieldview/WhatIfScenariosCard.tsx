import React, { useState } from 'react';
import { FlaskConical, Thermometer, CloudRain, CalendarDays, Waves } from 'lucide-react';
import {
  useScenarioTemperature, useScenarioRainfall, useScenarioPlantingDate, useScenarioWaterTwin,
} from '../../hooks/useApi';
import {
  buildPlantingPayload, buildRainfallPayload, buildTemperaturePayload, buildWaterTwinPayload,
  cropKeyFromLabel, fmtDelta, fmtNum, mmToCubicMeters,
  CROP_AR, GDD_CROPS, STAGE_AR, STAGES, UNCALIBRATED_NOTE_AR, WATER_CROPS,
  type ScenarioComparison,
} from '../../lib/whatIfScenarios';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  /** محصول الحقل النشط (عربيّ) — يقود الاختيار الافتراضيّ للمحصول (بلا تخمين لغير المعروف). */
  cropLabel?: string | null;
  /** مساحة الحقل (هكتار) — لتحويل «مم» إلى «م³» في توأم المياه؛ غيابها يعطّل التحويل لا يخمّنه. */
  areaHa?: number | null;
  enabled?: boolean;
}

type Tab = 'temperature' | 'rainfall' | 'planting' | 'watertwin';

const TABS: [Tab, string, typeof Thermometer][] = [
  ['temperature', 'حرارة', Thermometer],
  ['rainfall', 'مطر', CloudRain],
  ['planting', 'موعد الزراعة', CalendarDays],
  ['watertwin', 'توأم المياه', Waves],
];

/** سيناريوهات «ماذا لو» الفيزيائيّة (POST /api/v1/scenario/*): حرارة ±° · مطر موسميّ ·
 *  موعد زراعة (GDD) · توأم المياه (تأجيل/تحجيم الريّ FAO-56). كانت نقاط خلفيّة بلا واجهة.
 *  صدق: المدخلات افتراضات المستخدم («افتراضك») والمقارنات كلّها من الخادم؛ نصّ الصدق
 *  الخادميّ (summary_ar) يُعرَض كما هو مع لافتة «محاكاة افتراضات — ليست تنبّؤاً معايَراً». */
export default function WhatIfScenariosCard({ fieldId, cropLabel, areaHa, enabled = true }: Props) {
  const [tab, setTab] = useState<Tab>('temperature');
  const [buildErr, setBuildErr] = useState<string | null>(null);

  const inferredCrop = cropKeyFromLabel(cropLabel);
  // حرارة
  const [crop, setCrop] = useState(inferredCrop ?? 'wheat');
  const [stage, setStage] = useState('mid');
  const [tMin, setTMin] = useState('');
  const [tMax, setTMax] = useState('');
  const [shift, setShift] = useState('');
  const tempM = useScenarioTemperature();
  // مطر
  const [rainBase, setRainBase] = useState('');
  const [rainScen, setRainScen] = useState('');
  const rainM = useScenarioRainfall();
  // موعد الزراعة (GDD)
  const [gddCrop, setGddCrop] = useState(
    inferredCrop && (GDD_CROPS as readonly string[]).includes(inferredCrop) ? inferredCrop : 'wheat',
  );
  const [horizon, setHorizon] = useState('30');
  const [bTMin, setBTMin] = useState('');
  const [bTMax, setBTMax] = useState('');
  const [sTMin, setSTMin] = useState('');
  const [sTMax, setSTMax] = useState('');
  const plantM = useScenarioPlantingDate();
  // توأم المياه
  const [taw, setTaw] = useState('');
  const [rawMm, setRawMm] = useState('');
  const [dep0, setDep0] = useState('0');
  const [twinDays, setTwinDays] = useState('14');
  const [etc, setEtc] = useState('');
  const [irrDepth, setIrrDepth] = useState('');
  const [irrEvery, setIrrEvery] = useState('7');
  const [twinKind, setTwinKind] = useState<'delay' | 'scale'>('delay');
  const [delayDays, setDelayDays] = useState('3');
  const [scaleFactor, setScaleFactor] = useState('0.8');
  const twinM = useScenarioWaterTwin();

  if (!enabled || !fieldId) return null;

  const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
  const runStyle = { border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' } as const;

  const serverErr = (e: unknown): string => {
    const r = e as { response?: { status?: number; data?: { detail?: unknown } } };
    const detail = typeof r?.response?.data?.detail === 'string' ? r.response.data.detail : null;
    return detail ?? `تعذّر تشغيل السيناريو${r?.response?.status ? ` (${r.response.status})` : ''}.`;
  };

  const runTemperature = () => {
    setBuildErr(null);
    const r = buildTemperaturePayload({ crop, stage, tMinC: tMin, tMaxC: tMax, tempShiftC: shift });
    if (!r.ok) { setBuildErr(r.error); return; }
    tempM.mutate(r.payload);
  };
  const runRainfall = () => {
    setBuildErr(null);
    const r = buildRainfallPayload({ crop, stage, tMinC: tMin, tMaxC: tMax, rainBaselineMm: rainBase, rainScenarioMm: rainScen });
    if (!r.ok) { setBuildErr(r.error); return; }
    rainM.mutate(r.payload);
  };
  const runPlanting = () => {
    setBuildErr(null);
    const r = buildPlantingPayload({
      crop: gddCrop, horizonDays: horizon,
      baselineTMinC: bTMin, baselineTMaxC: bTMax, scenarioTMinC: sTMin, scenarioTMaxC: sTMax,
    });
    if (!r.ok) { setBuildErr(r.error); return; }
    plantM.mutate(r.payload);
  };
  const runWaterTwin = () => {
    setBuildErr(null);
    const r = buildWaterTwinPayload({
      tawMm: taw, rawMm, initialDepletionMm: dep0, horizonDays: twinDays,
      dailyEtcMm: etc, irrigationDepthMm: irrDepth, irrigationIntervalDays: irrEvery,
      kind: twinKind, delayDays, scaleFactor,
    });
    if (!r.ok) { setBuildErr(r.error); return; }
    twinM.mutate(r.payload);
  };

  const labeled = (label: string, node: React.ReactNode) => (
    <label className="inline-flex items-center gap-1">
      <span className="text-[10px]" style={{ color: T.faint }}>{label}</span>
      {node}
    </label>
  );
  const numInput = (value: string, set: (v: string) => void, aria: string, width = 'w-20', step = 'any') => (
    <input
      type="number" step={step} value={value} onChange={(e) => set(e.target.value)}
      placeholder="افتراضك" className={`${width} px-2 py-1 rounded-lg text-[11px]`} style={inputStyle} aria-label={aria}
    />
  );
  const cropStageSelects = (
    <>
      {labeled('المحصول', (
        <select value={crop} onChange={(e) => setCrop(e.target.value)} className="px-2 py-1 rounded-lg text-[11px]" style={inputStyle} aria-label="المحصول">
          {WATER_CROPS.map((c) => <option key={c} value={c}>{CROP_AR[c] ?? c}</option>)}
        </select>
      ))}
      {labeled('المرحلة', (
        <select value={stage} onChange={(e) => setStage(e.target.value)} className="px-2 py-1 rounded-lg text-[11px]" style={inputStyle} aria-label="مرحلة النموّ">
          {STAGES.map((s) => <option key={s} value={s}>{STAGE_AR[s] ?? s}</option>)}
        </select>
      ))}
      {labeled('حرارة دنيا °م', numInput(tMin, setTMin, 'الحرارة الدنيا'))}
      {labeled('قصوى °م', numInput(tMax, setTMax, 'الحرارة القصوى'))}
    </>
  );

  const runBtn = (onClick: () => void, pending: boolean) => (
    <button type="button" onClick={onClick} disabled={pending} className="px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50" style={runStyle}>
      {pending ? 'جارٍ الحساب…' : 'شغّل السيناريو'}
    </button>
  );

  // نتائج: جدول المقارنات الخادميّ كما هو — لا دلتا تُحسَب في الواجهة.
  const comparisonsTable = (rows: ScenarioComparison[]) => (
    <table className="w-full text-[11px] mt-1">
      <thead>
        <tr style={{ color: T.faint }}>
          <th className="text-right font-semibold py-0.5">المؤشّر</th>
          <th className="font-semibold">الأساس</th>
          <th className="font-semibold">افتراضك</th>
          <th className="font-semibold">الفرق</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.metric_ar} className="border-t" style={{ borderColor: T.line, color: T.muted }}>
            <td className="py-0.5 text-right" style={{ color: T.ink }}>{c.metric_ar}</td>
            <td className="text-center">{fmtNum(c.baseline)} {c.unit}</td>
            <td className="text-center">{fmtNum(c.scenario)} {c.unit}</td>
            <td className="text-center font-semibold" style={{ color: c.delta === 0 ? T.muted : '#fdba74' }}>{fmtDelta(c.delta)} {c.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const resultBlock = (
    data: { comparisons: ScenarioComparison[]; summary_ar: string } | undefined,
    extra?: React.ReactNode | null,
  ) => data ? (
    <div className="mt-2 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
      {/* نصّ الصدق الخادميّ يُعرَض بارزاً كما ورد (summary_ar يتضمّن إخلاء المسؤوليّة) */}
      <div className="text-[11px] font-bold" style={{ color: '#fde68a' }}>{data.summary_ar}</div>
      {comparisonsTable(data.comparisons)}
      {extra}
      <div className="mt-1 text-[10px]" style={{ color: T.faint }}>{UNCALIBRATED_NOTE_AR}</div>
    </div>
  ) : null;

  const twinData = twinM.data;
  const twinIrrigationDelta = twinData?.comparisons.find((c) => c.metric_ar === 'إجماليّ الريّ')?.delta ?? null;
  const twinDeltaM3 = mmToCubicMeters(twinIrrigationDelta, areaHa ?? null);

  const activeErr =
    (tab === 'temperature' && tempM.error) || (tab === 'rainfall' && rainM.error)
    || (tab === 'planting' && plantM.error) || (tab === 'watertwin' && twinM.error) || null;

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="what-if-scenarios" aria-label="سيناريوهات ماذا لو">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <FlaskConical className="w-4 h-4 text-emerald-300" aria-hidden="true" /> ماذا لو؟ — محاكاة افتراضات
        </span>
        <div className="inline-flex items-center gap-1 rounded-xl p-0.5" style={{ background: T.card, border: `1px solid ${T.line}` }}>
          {TABS.map(([t, label, Icon]) => (
            <button
              key={t} type="button" onClick={() => { setTab(t); setBuildErr(null); }}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-bold"
              style={{ background: tab === t ? '#14532d' : 'transparent', color: tab === t ? '#bbf7d0' : T.muted }}
            >
              <Icon className="w-3 h-3" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'temperature' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {cropStageSelects}
            {labeled('تحوّل ±°م', numInput(shift, setShift, 'تحوّل الحرارة'))}
            {runBtn(runTemperature, tempM.isPending)}
          </div>
          {resultBlock(tempM.data)}
        </div>
      )}

      {tab === 'rainfall' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {cropStageSelects}
            {labeled('مطر الأساس مم', numInput(rainBase, setRainBase, 'مطر الأساس'))}
            {labeled('مطر الافتراض مم', numInput(rainScen, setRainScen, 'مطر الافتراض'))}
            {runBtn(runRainfall, rainM.isPending)}
          </div>
          {resultBlock(rainM.data)}
        </div>
      )}

      {tab === 'planting' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {labeled('المحصول (GDD)', (
              <select value={gddCrop} onChange={(e) => setGddCrop(e.target.value)} className="px-2 py-1 rounded-lg text-[11px]" style={inputStyle} aria-label="محصول GDD">
                {GDD_CROPS.map((c) => <option key={c} value={c}>{CROP_AR[c] ?? c}</option>)}
              </select>
            ))}
            {labeled('نافذة (يوم)', numInput(horizon, setHorizon, 'نافذة المقارنة', 'w-16', '1'))}
            {labeled('الأساس: دنيا °م', numInput(bTMin, setBTMin, 'حرارة الأساس الدنيا'))}
            {labeled('قصوى °م', numInput(bTMax, setBTMax, 'حرارة الأساس القصوى'))}
            {labeled('البديل: دنيا °م', numInput(sTMin, setSTMin, 'حرارة البديل الدنيا'))}
            {labeled('قصوى °م', numInput(sTMax, setSTMax, 'حرارة البديل القصوى'))}
            {runBtn(runPlanting, plantM.isPending)}
          </div>
          <div className="text-[10px]" style={{ color: T.faint }}>
            الافتراض: حرارة ثابتة على النافذة لكلّ موعد — مقارنة GDD لا توقيت فعليّاً.
          </div>
          {resultBlock(plantM.data, plantM.data ? (
            <div className="mt-1 text-[11px]" style={{ color: T.muted }}>
              مرحلة الأساس: <b style={{ color: T.ink }}>{plantM.data.baseline_stage}</b>
              {' · '}مرحلة البديل: <b style={{ color: T.ink }}>{plantM.data.scenario_stage}</b>
            </div>
          ) : null)}
        </div>
      )}

      {tab === 'watertwin' && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {labeled('TAW مم', numInput(taw, setTaw, 'TAW'))}
            {labeled('RAW مم', numInput(rawMm, setRawMm, 'RAW'))}
            {labeled('نضوب ابتدائيّ مم', numInput(dep0, setDep0, 'النضوب الابتدائيّ'))}
            {labeled('أفق (يوم)', numInput(twinDays, setTwinDays, 'أفق المحاكاة', 'w-16', '1'))}
            {labeled('ETc يوميّ مم', numInput(etc, setEtc, 'ETc اليوميّ'))}
            {labeled('عمق الريّة مم', numInput(irrDepth, setIrrDepth, 'عمق الريّة'))}
            {labeled('كلّ (يوم)', numInput(irrEvery, setIrrEvery, 'تكرار الريّ', 'w-14', '1'))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {labeled('البديل', (
              <select value={twinKind} onChange={(e) => setTwinKind(e.target.value as 'delay' | 'scale')} className="px-2 py-1 rounded-lg text-[11px]" style={inputStyle} aria-label="نوع البديل">
                <option value="delay">تأجيل الريّ</option>
                <option value="scale">تحجيم العمق</option>
              </select>
            ))}
            {twinKind === 'delay'
              ? labeled('تأجيل (يوم)', numInput(delayDays, setDelayDays, 'أيّام التأجيل', 'w-14', '1'))
              : labeled('معامل العمق', numInput(scaleFactor, setScaleFactor, 'معامل العمق', 'w-16', '0.05'))}
            {runBtn(runWaterTwin, twinM.isPending)}
          </div>
          {resultBlock(twinData, twinData ? (
            <div className="mt-1 text-[11px]" style={{ color: T.muted }}>
              أيّام إجهاد: الأساس <b style={{ color: T.ink }}>{fmtNum(twinData.baseline.stress_days, 0)}</b>
              {' ⇐ '}البديل <b style={{ color: '#fdba74' }}>{fmtNum(twinData.scenario.stress_days, 0)}</b>
              {' · '}رطوبة ختاميّة: {fmtNum(twinData.baseline.final_soil_moisture_pct, 1)}٪ ⇐ {fmtNum(twinData.scenario.final_soil_moisture_pct, 1)}٪
              {twinDeltaM3 != null && (
                <span>{' · '}فرق ماء الريّ للمساحة ≈ <b style={{ color: T.ink }}>{fmtNum(twinDeltaM3)}</b> م³</span>
              )}
            </div>
          ) : null)}
        </div>
      )}

      {buildErr && <div className="mt-2 text-[11px]" role="alert" style={{ color: '#fdba74' }}>{buildErr}</div>}
      {activeErr && <div className="mt-2 text-[11px]" role="alert" style={{ color: '#fca5a5' }}>{serverErr(activeErr)}</div>}
    </section>
  );
}
