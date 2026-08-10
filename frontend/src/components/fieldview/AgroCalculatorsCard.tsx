import { useMemo, useState } from 'react';
import { Calculator, Sprout, Thermometer, Ruler, Droplets, Mountain, ListChecks } from 'lucide-react';
import {
  useSeedGerminationRate, useSeedStorageCheck, useSeedSowingDepth, useSeedCriteria,
  usePostharvestMoistureCheck, useCoffeeSiteSuitability,
} from '../../hooks/useApi';
import {
  buildGerminationParams, buildStorageCheckParams, buildSowingDepthParams,
  buildMoistureCheckParams, buildCoffeeSiteParams,
  moistureStatusColor, coffeeRatingColor,
} from '../../lib/agroCalculators';
import type { BuildResult } from '../../lib/agroCalculators';
import { T } from '../ds';

interface Props {
  /** تسمية محصول الحقل النشط — تملأ حقل «المحصول» في فحص رطوبة الحبوب مبدئيّاً. */
  cropLabel?: string | null;
  enabled?: boolean;
}

/** يحسم نتيجة بناء: يستدعي فقط عند صحّة كلّ المُدخلات، ويُظهر سبب الرفض العربيّ
 *  عندما بدأ المستخدم الإدخال — لا استدعاء بقيم ناقصة/فاسدة ولا خطأ قبل أن يكتب. */
function useBuilt<P>(build: () => BuildResult<P>, touched: boolean): { params: P | null; error: string | null } {
  return useMemo(() => {
    if (!touched) return { params: null, error: null };
    const r = build();
    return r.ok ? { params: r.payload, error: null } : { params: null, error: r.error };
  }, [touched, build]);
}

function NumInput({ id, label, value, onChange, width = 'w-20', step = '0.1', placeholder = 'من قياس' }: {
  id: string; label: string; value: string; onChange: (v: string) => void;
  width?: string; step?: string; placeholder?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <label htmlFor={id} className="font-bold text-[11px]" style={{ color: T.ink }}>{label}</label>
      <input
        id={id}
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${width} px-2 py-0.5 rounded-lg text-[11px]`}
        style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
      />
    </span>
  );
}

function LocalError({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="text-[10px]" style={{ color: '#fdba74' }}>{error}</div>;
}

/** حاسبات قياس حقليّة للخبير الزراعيّ: إنبات/تخزين/عمق بذر · رطوبة حبوب قبل
 *  التخزين · ملاءمة ارتفاع للبنّ. صدق: المُدخلات قياسات حقيقيّة من المستخدم
 *  (تحقّق صارم محليّاً)، والأحكام/النصائح (*_ar) تُعرَض حرفيّاً من الخادم —
 *  الألوان للحالات المعروفة فقط. */
export default function AgroCalculatorsCard({ cropLabel, enabled = true }: Props) {
  // 1) إنبات البذور
  const [sprouted, setSprouted] = useState('');
  const [totalSeeds, setTotalSeeds] = useState('');
  const germBuilt = useBuilt(
    () => buildGerminationParams({ sprouted, total: totalSeeds }),
    sprouted.trim() !== '' && totalSeeds.trim() !== '',
  );
  const germQ = useSeedGerminationRate(germBuilt.params);

  // 2) تخزين البذور (قاعدة المئة)
  const [tempC, setTempC] = useState('');
  const [humidity, setHumidity] = useState('');
  const storBuilt = useBuilt(
    () => buildStorageCheckParams({ tempC, humidityPct: humidity }),
    tempC.trim() !== '' && humidity.trim() !== '',
  );
  const storQ = useSeedStorageCheck(storBuilt.params);

  // 3) عمق البذر
  const [seedSize, setSeedSize] = useState('');
  const [precision, setPrecision] = useState(false);
  const depthBuilt = useBuilt(
    () => buildSowingDepthParams({ seedSizeMm: seedSize, precision }),
    seedSize.trim() !== '',
  );
  const depthQ = useSeedSowingDepth(depthBuilt.params);

  // 4) رطوبة الحبوب قبل التخزين
  const [moistCrop, setMoistCrop] = useState(cropLabel ?? '');
  const [moisture, setMoisture] = useState('');
  const moistBuilt = useBuilt(
    () => buildMoistureCheckParams({ crop: moistCrop, moisturePct: moisture }),
    moisture.trim() !== '',
  );
  const moistQ = usePostharvestMoistureCheck(moistBuilt.params);

  // 5) ملاءمة موقع البنّ (ارتفاع)
  const [altitude, setAltitude] = useState('');
  const coffeeBuilt = useBuilt(
    () => buildCoffeeSiteParams({ altitudeM: altitude }),
    altitude.trim() !== '',
  );
  const coffeeQ = useCoffeeSiteSuitability(coffeeBuilt.params);

  // 6) معايير اختيار البذور — مرجع عند الطلب
  const [showCriteria, setShowCriteria] = useState(false);
  const criteriaQ = useSeedCriteria(enabled && showCriteria);

  if (!enabled) return null;

  const moistColor = moistureStatusColor(moistQ.data?.status);
  const coffeeColor = coffeeRatingColor(coffeeQ.data?.rating);

  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="agro-calculators" aria-label="حاسبات قياس حقليّة">
      <div className="inline-flex items-center gap-2 text-sm font-bold mb-2" style={{ color: T.ink }}>
        <Calculator className="w-4 h-4 text-emerald-300" aria-hidden="true" /> حاسبات قياس حقليّة
        <span className="text-[11px]" style={{ color: T.faint }}>· من قياساتك أنت — لا افتراضات</span>
      </div>

      <div className="flex flex-col gap-2.5">
        {/* إنبات البذور */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <Sprout className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>اختبار الإنبات:</span>
            <NumInput id="agro-germ-sprouted" label="المُنبِت" value={sprouted} onChange={setSprouted} step="1" width="w-16" />
            <NumInput id="agro-germ-total" label="من إجمالي" value={totalSeeds} onChange={setTotalSeeds} step="1" width="w-16" placeholder="100" />
            {germQ.data && (germQ.data.supported ? (
              <span style={{ color: T.ink }}>
                {germQ.data.germination_pct != null ? `${germQ.data.germination_pct}٪ — ` : ''}{germQ.data.verdict_ar}
              </span>
            ) : (
              <span style={{ color: T.faint }}>{germQ.data.message_ar}</span>
            ))}
          </div>
          <LocalError error={germBuilt.error} />
          {germQ.data?.supported && germQ.data.method_ar && (
            <div className="text-[10px]" style={{ color: T.faint }}>{germQ.data.method_ar}</div>
          )}
        </div>

        {/* تخزين البذور — قاعدة المئة */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <Thermometer className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>تخزين البذور:</span>
            <NumInput id="agro-stor-temp" label="حرارة المخزن (°م)" value={tempC} onChange={setTempC} />
            <NumInput id="agro-stor-rh" label="رطوبة نسبيّة %" value={humidity} onChange={setHumidity} />
            {storQ.data && (
              <span style={{ color: storQ.data.good_storage ? '#86efac' : '#fdba74' }}>{storQ.data.verdict_ar}</span>
            )}
          </div>
          <LocalError error={storBuilt.error} />
          {storQ.data && (
            <div className="text-[10px]" style={{ color: T.faint }}>{storQ.data.rule_ar} · {storQ.data.tip_ar}</div>
          )}
        </div>

        {/* عمق البذر */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <Ruler className="w-3.5 h-3.5 shrink-0 text-amber-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>عمق البذر:</span>
            <NumInput id="agro-depth-size" label="حجم البذرة (مم)" value={seedSize} onChange={setSeedSize} />
            <label htmlFor="agro-depth-precision" className="inline-flex items-center gap-1 cursor-pointer">
              <input
                id="agro-depth-precision"
                type="checkbox"
                checked={precision}
                onChange={(e) => setPrecision(e.target.checked)}
              />
              زراعة دقيقة
            </label>
            {depthQ.data && (depthQ.data.supported ? (
              <span style={{ color: T.ink }}>{depthQ.data.advice_ar}</span>
            ) : (
              <span style={{ color: T.faint }}>{depthQ.data.message_ar}</span>
            ))}
          </div>
          <LocalError error={depthBuilt.error} />
          {depthQ.data?.supported && depthQ.data.note_ar && (
            <div className="text-[10px]" style={{ color: T.faint }}>{depthQ.data.principle_ar} · {depthQ.data.note_ar}</div>
          )}
        </div>

        {/* رطوبة الحبوب قبل التخزين */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <Droplets className="w-3.5 h-3.5 shrink-0 text-sky-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>رطوبة الحبوب قبل التخزين:</span>
            <span className="inline-flex items-center gap-1.5">
              <label htmlFor="agro-moist-crop" className="font-bold text-[11px]" style={{ color: T.ink }}>المحصول</label>
              <input
                id="agro-moist-crop"
                type="text"
                value={moistCrop}
                onChange={(e) => setMoistCrop(e.target.value)}
                placeholder="قمح، ذرة…"
                className="w-24 px-2 py-0.5 rounded-lg text-[11px]"
                style={{ border: `1px solid ${T.line}`, background: 'rgba(2,6,23,.5)', color: T.ink }}
              />
            </span>
            <NumInput id="agro-moist-pct" label="رطوبة مقيسة %" value={moisture} onChange={setMoisture} />
            {moistQ.data && (moistQ.data.supported ? (
              <span style={moistColor ? { color: moistColor } : { color: T.ink }}>
                {moistQ.data.status_ar}
                {moistQ.data.safe_max_pct != null ? ` (الحدّ ≤${moistQ.data.safe_max_pct}٪)` : ''}
              </span>
            ) : (
              <span style={{ color: T.faint }}>{moistQ.data.message_ar}</span>
            ))}
          </div>
          <LocalError error={moistBuilt.error} />
          {moistQ.data?.supported && moistQ.data.advice_ar && (
            <div className="text-[10px]" style={{ color: T.muted }}>{moistQ.data.advice_ar}</div>
          )}
        </div>

        {/* ملاءمة موقع للبنّ */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: T.muted }}>
            <Mountain className="w-3.5 h-3.5 shrink-0 text-emerald-300" aria-hidden="true" />
            <span className="font-bold" style={{ color: T.ink }}>ملاءمة الموقع للبنّ:</span>
            <NumInput id="agro-coffee-alt" label="الارتفاع (م)" value={altitude} onChange={setAltitude} step="10" width="w-24" placeholder="من GPS" />
            {coffeeQ.data && (
              <span style={coffeeColor ? { color: coffeeColor } : { color: T.ink }}>{coffeeQ.data.rating_ar}</span>
            )}
          </div>
          <LocalError error={coffeeBuilt.error} />
          {coffeeQ.data && (
            <div className="text-[10px]" style={{ color: T.muted }}>
              {coffeeQ.data.reason_ar}
              <span style={{ color: T.faint }}> · المدى المثالي: {coffeeQ.data.optimal_range_ar}</span>
            </div>
          )}
        </div>

        {/* معايير اختيار البذور — مرجع قرار */}
        <div className="rounded-xl border p-2 flex flex-col gap-1.5" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
          <button
            type="button"
            onClick={() => setShowCriteria((v) => !v)}
            className="inline-flex items-center gap-2 text-[11px] font-bold self-start"
            style={{ color: T.ink }}
          >
            <ListChecks className="w-3.5 h-3.5 text-amber-300" aria-hidden="true" />
            معايير اختيار البذور المحسّنة {showCriteria ? '▴' : '▾'}
          </button>
          {showCriteria && (criteriaQ.isLoading ? (
            <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة المعايير…</div>
          ) : criteriaQ.data ? (
            <div className="flex flex-col gap-1">
              {criteriaQ.data.criteria_ar.map((c) => (
                <div key={c.factor_ar} className="text-[11px]" style={{ color: T.muted }}>
                  <span className="font-bold" style={{ color: T.ink }}>{c.factor_ar}:</span> {c.detail_ar}
                </div>
              ))}
              <div className="text-[10px]" style={{ color: T.faint }}>{criteriaQ.data.source_guidance_ar}</div>
              <div className="text-[10px]" style={{ color: '#fdba74' }}>{criteriaQ.data.caution_ar}</div>
              <div className="text-[10px]" style={{ color: T.faint }}>{criteriaQ.data.disclaimer_ar}</div>
            </div>
          ) : null)}
        </div>

        {/* إخلاءات مسؤوليّة الحاسبات — من الخادم حرفيّاً */}
        {(germQ.data?.disclaimer_ar || storQ.data?.disclaimer_ar || depthQ.data?.disclaimer_ar) && (
          <div className="text-[10px]" style={{ color: T.faint }}>
            {[germQ.data?.disclaimer_ar, storQ.data?.disclaimer_ar, depthQ.data?.disclaimer_ar]
              .filter(Boolean).join(' · ')}
          </div>
        )}
      </div>
    </section>
  );
}
