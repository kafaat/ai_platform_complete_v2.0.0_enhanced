import { useMemo, useState } from 'react';
import { Droplets, ShieldAlert, Thermometer } from 'lucide-react';
import {
  useFieldIrrigationRecommendation,
  isRecommendationReady,
  type IrrigationRecommendationWeatherInput,
  type WaterStressClass,
  type IrrigationUrgency,
} from '../../hooks/useFieldIrrigationRecommendation';
import { fmtNum, parseMeasure } from '../../lib/irrigationDecisionAids';
import { T } from '../ds';

interface Props {
  /** مُعرّف الحقل — النقطة على مستوى الحقل (لا استدعاء بلا مُعرّف). */
  fieldId: string | null;
  /** تسمية محصول الحقل النشط — عرضيّة فقط (السياق الحقيقيّ يُحقَن من الخادم). */
  cropLabel?: string | null;
  enabled?: boolean;
}

const inputStyle = { border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink } as const;
const boxStyle = { borderColor: T.line, background: 'rgba(15,23,42,.35)' } as const;

/** ألوان صنف الإجهاد المائيّ — عرضيّة فقط (الحكم من الخادم). المجهول محايد. */
const STRESS_STYLE: Record<Exclude<WaterStressClass, null>, { label_ar: string; color: string }> = {
  normal: { label_ar: 'طبيعيّ', color: '#86efac' },
  watch: { label_ar: 'مراقبة', color: '#fdba74' },
  critical: { label_ar: 'حرِج', color: '#fca5a5' },
};

const URGENCY_AR: Record<IrrigationUrgency, string> = {
  none: 'لا إلحاح',
  low: 'إلحاح منخفض',
  moderate: 'إلحاح متوسّط',
  high: 'إلحاح مرتفع',
};

const TAW_SOURCE_AR: Record<string, string> = {
  soil_lab: 'مختبر تربة',
  texture_fallback: 'تقدير من القوام (احتياطيّ)',
};

/** «هل أروي الآن؟» — مرشَّح توصية ريّ واعٍ بالاستنزاف (WS-D.2) من الطقس (ET₀).
 *  صدق صارم: التوصية مرشَّحة لا مُنفَّذة (الملكيّة لخدمة القرار)؛ وحين تنقص بيانات
 *  الاستنزاف أو تكون الحالة غير متّسقة نعرض حالة متدهورة صادقة بلا أرقام مُلفّقة؛
 *  والنتيجة دائماً «غير معايَرة يمنيّاً» مع سرد الحدود. */
export default function IrrigationDecisionCard({ fieldId, cropLabel, enabled = true }: Props) {
  // — الطقس لحساب ET₀: الحرارة الصغرى/الكبرى إلزاميّة، والباقي اختياريّ (يُرسَل إن أُدخِل) —
  const [tMinInput, setTMinInput] = useState('');
  const [tMaxInput, setTMaxInput] = useState('');
  const [solarInput, setSolarInput] = useState('');
  const [rhInput, setRhInput] = useState('');
  const [windInput, setWindInput] = useState('');

  const weather = useMemo<IrrigationRecommendationWeatherInput | null>(() => {
    const tMin = parseMeasure(tMinInput);
    const tMax = parseMeasure(tMaxInput);
    if (tMin == null || tMax == null) return null; // ET₀ لا يُحسَب بلا حرارة حقيقيّة
    const solar = parseMeasure(solarInput);
    const rh = parseMeasure(rhInput);
    const wind = parseMeasure(windInput);
    return {
      t_min_c: tMin,
      t_max_c: tMax,
      day_of_year: Math.min(366, Math.max(1, Math.ceil((Date.now() - Date.UTC(new Date().getUTCFullYear(), 0, 0)) / 86_400_000))),
      ...(solar != null ? { solar_rad_mj_m2: solar } : {}),
      ...(rh != null ? { rh_mean_pct: rh } : {}),
      ...(wind != null ? { wind_2m_ms: wind } : {}),
    };
  }, [tMinInput, tMaxInput, solarInput, rhInput, windInput]);

  const { data, loading, error, refetch } = useFieldIrrigationRecommendation(
    fieldId,
    enabled ? weather : null,
    enabled,
  );

  if (!enabled) return null;

  const ready = isRecommendationReady(data);
  const rec = ready ? data.recommendation : null;
  const stress = rec?.water_stress_class ?? null;
  const stressStyle = stress ? STRESS_STYLE[stress] : null;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="irrigation-decision-recommendation"
      aria-label="مرشَّح توصية الريّ الواعي بالاستنزاف"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-sky-300" aria-hidden="true" /> مرشَّح توصية الريّ (واعٍ بالاستنزاف)
          {cropLabel && <span className="text-[11px]" style={{ color: T.faint }}>· {cropLabel}</span>}
        </span>
      </div>

      {/* مدخلات الطقس لحساب ET₀ — الحرارة الصغرى/الكبرى إلزاميّة، الباقي اختياريّ */}
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] mb-2 rounded-xl border p-2" style={boxStyle}>
        <Thermometer className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
        <label htmlFor="idr-tmin" className="font-bold" style={{ color: T.ink }}>الصغرى (°م):</label>
        <input id="idr-tmin" type="number" step="0.1" value={tMinInput} onChange={(e) => setTMinInput(e.target.value)} placeholder="من قياس" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
        <label htmlFor="idr-tmax" className="font-bold" style={{ color: T.ink }}>الكبرى (°م):</label>
        <input id="idr-tmax" type="number" step="0.1" value={tMaxInput} onChange={(e) => setTMaxInput(e.target.value)} placeholder="من قياس" className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
        <label htmlFor="idr-solar">إشعاع (MJ/م²، اختياري):</label>
        <input id="idr-solar" type="number" step="0.1" min="0" value={solarInput} onChange={(e) => setSolarInput(e.target.value)} className="w-16 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
        <label htmlFor="idr-rh">رطوبة (٪، اختياري):</label>
        <input id="idr-rh" type="number" step="1" min="0" max="100" value={rhInput} onChange={(e) => setRhInput(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
        <label htmlFor="idr-wind">ريح (م/ث، اختياري):</label>
        <input id="idr-wind" type="number" step="0.1" min="0" value={windInput} onChange={(e) => setWindInput(e.target.value)} className="w-14 px-2 py-0.5 rounded-lg text-[11px]" style={inputStyle} />
      </div>

      {/* الحالات — نعالج الثلاث بصدق: بلا مدخلات / تحميل / خطأ / متدهورة / جاهزة */}
      {!fieldId ? (
        <div className="text-[10px]" style={{ color: T.faint }}>لا حقل محدَّد.</div>
      ) : weather == null ? (
        <div className="text-[10px]" style={{ color: T.faint }}>أدخِل الحرارة الصغرى والكبرى (من قياس) ليحسب الخادم ET₀ ثمّ مرشَّح التوصية.</div>
      ) : loading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ توليد مرشَّح التوصية…</div>
      ) : error ? (
        <div className="text-[11px]" style={{ color: '#fca5a5' }}>
          تعذّر توليد مرشَّح التوصية من الخادم.
          <button type="button" onClick={() => refetch()} className="ms-1 underline" style={{ color: '#fca5a5' }}>أعد المحاولة</button>
        </div>
      ) : data ? (
        <div className="flex flex-col gap-2">
          {/* ── توصية جاهزة ── */}
          {ready && rec ? (
            <div className="flex flex-col gap-1.5 rounded-xl border p-2" style={boxStyle}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span
                  className="text-[12px] px-2.5 py-0.5 rounded-full font-bold"
                  style={{
                    border: `1px solid ${T.line}`,
                    color: rec.should_irrigate == null ? T.muted : rec.should_irrigate ? '#fca5a5' : '#86efac',
                  }}
                >
                  {rec.should_irrigate == null ? 'قرار غير محسوم' : rec.should_irrigate ? 'اروِ' : 'أجّل'}
                </span>
                {rec.target_refill_mm != null && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
                    ملء ~{fmtNum(rec.target_refill_mm, 1)} مم
                  </span>
                )}
                {stressStyle && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: stressStyle.color }}>
                    إجهاد: {stressStyle.label_ar}
                  </span>
                )}
                <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.muted }}>
                  {URGENCY_AR[rec.urgency] ?? rec.urgency}
                </span>
              </div>

              <div className="text-[11px]" style={{ color: T.ink }}>
                صافي الريّ المقترَح: <b>{fmtNum(rec.net_irrigation_mm, 1)} مم</b>
              </div>
              {rec.trigger_reason && <div className="text-[11px]" style={{ color: T.muted }}>سبب التحفيز: {rec.trigger_reason}</div>}

              {/* ملكيّة صريحة: مرشَّح لا مُنفَّذ */}
              <div className="text-[10px] px-2 py-1 rounded-lg" style={{ border: `1px dashed ${T.line}`, color: '#7dd3fc' }}>
                توصية مرشَّحة — القرار النهائيّ لخدمة القرار (لا مهمّة مُنفَّذة). {data.ownership}
              </div>
            </div>
          ) : (
            /* ── حالة متدهورة صادقة: insufficient_data / inconsistent_state ── */
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ ...boxStyle, borderColor: '#7c2d12' }}>
              <div className="inline-flex items-center gap-1.5 text-[12px] font-bold" style={{ color: '#fdba74' }}>
                <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />
                {data.status === 'insufficient_data'
                  ? 'بيانات الاستنزاف ناقصة — لا مرشَّح توصية'
                  : 'حالة غير متّسقة (Dr>TAW) — لا مرشَّح توصية'}
              </div>
              <div className="text-[10px]" style={{ color: T.faint }}>لا أرقام ريّ حتى تُستكمَل/تُصحَّح المدخلات (صدق: لا تلفيق).</div>
            </div>
          )}

          {/* مدخلات القرار كما أعلنها الخادم (شفافيّة المصدر) — تُعرَض في كلّ الحالات */}
          <div className="flex flex-wrap gap-1.5">
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              <span style={{ color: T.faint }}>الاستنزاف Dr:</span> {data.inputs.depletion_mm != null ? `${fmtNum(data.inputs.depletion_mm, 1)} مم` : '—'}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              <span style={{ color: T.faint }}>TAW:</span> {fmtNum(data.inputs.taw_mm, 1)} مم
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              <span style={{ color: T.faint }}>مصدر TAW:</span> {TAW_SOURCE_AR[data.inputs.taw_source] ?? data.inputs.taw_source}
            </span>
            <span className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: `1px solid ${T.line}`, color: T.ink }}>
              <span style={{ color: T.faint }}>المرحلة:</span> {data.inputs.stage}
            </span>
          </div>

          {/* دائماً: غير معايَر يمنيّاً + سرد الحدود (calibrated=false من الخادم) */}
          <div className="text-[10px]" style={{ color: '#fdba74' }}>⚠ غير معايَر يمنيّاً (calibrated=false).</div>
          {data.limitations.length > 0 && (
            <ul className="text-[10px] ps-4 list-disc" style={{ color: T.faint }}>
              {data.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}
