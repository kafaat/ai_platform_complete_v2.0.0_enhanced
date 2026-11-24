// تشغيل محاكاة الموسم (POST /api/v1/seasons/{id}/simulate) من أيّ شاشة تعرض sim_*.
// نُقِل من FieldManagementPage (غير مركَّبة في App.tsx) ليصير للتشغيل مدخلٌ مركَّب (F-U01).
// الخادم هو مصدر القواعد: الصلاحيّة (field:edit) والرفض (404/422/503) يُعرَضان كما عادا،
// ولا تُحسَب هنا قيمة ولا تُفترَض. الناتج تقدير نموذجيّ يُحفَظ على الموسم، لا توصية.
import { useEffect } from 'react';
import { Sprout, X } from 'lucide-react';
import { useSimulateSeason } from '@/hooks/useApi';
import { apiErrorMessage, type SeasonSimResult } from '@/services/api';

export interface SeasonSimulationInputs {
  fieldName?: string;
  cultivar?: string | null;
  sowingDate?: string | null;
  seasonEnd?: string | null;
  irrigationType?: string | null;
}

interface Props {
  seasonId: string;
  crops: string[];
  inputs?: SeasonSimulationInputs;
  onClose: () => void;
}

const num = (v: number | null | undefined) =>
  (typeof v === 'number' && Number.isFinite(v) ? Math.round(v).toLocaleString('ar') : '—');

export function SeasonSimulationDialog({ seasonId, crops, inputs, onClose }: Props) {
  const sim = useSimulateSeason();
  const r: SeasonSimResult | undefined = sim.data;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50" dir="rtl">
      <div role="dialog" aria-modal="true" aria-label="محاكاة الموسم"
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white max-h-[88vh] overflow-y-auto shadow-xl">
        <div className="flex items-center justify-between p-4 border-b border-slate-100">
          <div className="font-bold text-slate-800 text-sm flex items-center gap-2">
            <Sprout size={16} className="text-emerald-600" />
            محاكاة الموسم{inputs?.fieldName ? ` · ${inputs.fieldName}` : crops.length ? ` · ${crops.join('، ')}` : ''}
          </div>
          <button type="button" onClick={onClose} aria-label="إغلاق"
            className="text-slate-400 hover:text-slate-700"><X size={18} /></button>
        </div>

        <div className="p-4 space-y-3">
          {inputs && (
            <div>
              <div className="text-[11px] font-medium text-slate-500 mb-1.5">مدخلات الموسم كما هي مسجَّلة</div>
              <dl className="grid grid-cols-2 gap-2">
                <Input label="المحصول" value={crops.length ? crops.join('، ') : null} />
                <Input label="الصنف" value={inputs.cultivar} />
                <Input label="تاريخ البذار" value={inputs.sowingDate} />
                <Input label="نهاية الموسم" value={inputs.seasonEnd} missing="غير مسجَّلة" />
                <Input label="نوع الريّ" value={inputs.irrigationType} />
              </dl>
            </div>
          )}

          <ul className="text-[11px] text-slate-500 leading-relaxed list-disc pr-4 space-y-0.5">
            <li>نموذج محصوليّ (RUE/FAO-56) يُشغَّل على الخادم من الموسم المسجَّل وموقع الحقل وطقس نافذة الموسم التاريخيّ.</li>
            <li>النتيجة تقدير نموذجيّ بنطاق وثقة، وليست توصية ولا قياساً ميدانيّاً ولا تُنشئ مهمّة أو تنفيذاً.</li>
            <li>يُحفَظ الناتج على الموسم ويحلّ محلّ ناتج التشغيل السابق.</li>
            <li>يرفض الخادم التشغيل إن غاب تاريخ البذار أو إحداثيّات الحقل، أو تعدّدت محاصيل الموسم، أو تعذّر الطقس التاريخيّ؛ ولا تُعرَض حينها قيمة بديلة.</li>
          </ul>

          {sim.isError && (
            <div role="alert" className="rounded-lg p-3 text-xs bg-red-50 text-red-700 border border-red-100">
              تعذّرت المحاكاة — لا نتيجة تُعرَض. رسالة الخادم: {apiErrorMessage(sim.error, 'خطأ غير معروف.')}
            </div>
          )}

          {r && (
            <div className="space-y-3">
              {r.estimate_disclaimer_ar && (
                <p className="rounded-lg p-2 text-[11px] bg-amber-50 text-amber-800 border border-amber-100">
                  {r.estimate_disclaimer_ar}
                </p>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Stat label="الإنتاج المُقدَّر (kg/ha)"
                  value={r.yield_kg_ha == null ? 'غير متاح' : `${num(r.yield_low_kg_ha)} – ${num(r.yield_high_kg_ha)}`}
                  hint={r.yield_kg_ha != null
                    ? `المركزي ≈ ${num(r.yield_kg_ha)}`
                    : r.scenario_yield_kg_ha != null
                      ? `لا كمّيّات ريّ في سجلّ الموسم المرتبط بالمحاكاة — سيناريو «لو كان الريّ كافياً» ≈ ${num(r.scenario_yield_kg_ha)}، ليس تقديراً للموسم؛ سجلّ الريّ التشغيليّ للحقل لا يدخل المحاكاة بعد`
                      : `السبب: ${r.yield_status} — ليس صفراً مرصوداً`} />
                <Stat label="GDD التراكمي (°C·day)"
                  value={`${num(r.gdd_total)} / ${num(r.gdd_to_maturity)}`}
                  hint={r.maturity_reached == null ? 'النضج غير قابل للتقييم' : r.maturity_reached ? 'بلغ النضج' : 'لم يبلغ النضج'} />
                <Stat label="أقصى LAI (m²/m²)" value={r.lai_max?.toFixed(2) ?? '—'} hint="مؤشّر تقريبي" />
                <Stat label="احتياج الماء (mm)" value={num(r.water_need_mm)}
                  hint={r.water_need_mm == null ? 'ET₀ غير مكتمل؛ ليس صفرًا مرصودًا' : r.water_supply_mm != null ? `العرض ≈ ${num(r.water_supply_mm)}` : 'العرض غير معروف'} />
              </div>

              <div className="rounded-lg p-2 text-[11px] bg-slate-50 text-slate-600">
                الكتلة الحيويّة ≈ {num(r.biomass_kg_ha)} kg/ha · الثقة{' '}
                {/* An unavailable estimate has no confidence to show — never render it as 0٪. */}
                {r.yield_kg_ha == null ? 'غير متاحة' : `${Math.round(r.confidence * 100)}٪`}
                {!r.crop_recognized && ' · المحصول غير مُعرّف (نموذج عامّ)'}
              </div>

              <p className="text-[11px] text-slate-500 leading-relaxed">
                {r.simulation_engine ? `المحرّك: ${r.simulation_engine} · ` : ''}
                الأيّام المحاكاة: {r.window_days_simulated ?? r.days_simulated}
                {r.window_days_requested != null ? ` من ${r.window_days_requested} مطلوبة` : ''}
                {r.truncated ? ' (النافذة قُصَّت)' : ''}
                {r.manual_irrigation_used != null && ` · ريّ مسجَّل: ${r.manual_irrigation_used ? 'استُخدِم' : 'لم يُستخدَم'}`}
              </p>

              {/* The frontend can ship before the backend: an unavailable estimate from the
                  rue-fao56/1 engine still says «الثقة 0%» in its rationale. Never show that next
                  to «الثقة غير متاحة». */}
              <p className="text-[11px] text-slate-500 leading-relaxed">
                {r.yield_kg_ha == null
                  ? r.rationale_ar?.replace(/الثقة\s*0\s*[٪%]/g, 'الثقة غير متاحة')
                  : r.rationale_ar}
              </p>

              {r.limitations?.length > 0 && (
                <p className="text-[11px] text-slate-500">
                  قيود أعلنها الخادم: <span className="font-mono" dir="ltr">{r.limitations.join(' · ')}</span>
                </p>
              )}
              {r.assumptions_ar.length > 0 && (
                <ul className="text-[11px] text-slate-500 list-disc pr-4 space-y-0.5">
                  {r.assumptions_ar.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              )}
              {r.warnings_ar.length > 0 && (
                <ul className="text-[11px] list-disc pr-4 space-y-0.5 text-amber-700">
                  {r.warnings_ar.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-slate-100">
          <button type="button" onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs text-slate-600 hover:bg-slate-100">
            إغلاق
          </button>
          <button type="button" onClick={() => sim.mutate(seasonId)} disabled={sim.isPending}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50">
            {sim.isPending ? 'جارٍ التشغيل…' : r ? 'إعادة التشغيل' : 'تشغيل المحاكاة'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Input({ label, value, missing = 'غير مسجَّل' }: { label: string; value?: string | null; missing?: string }) {
  return (
    <div className="rounded-lg p-2 bg-slate-50">
      <dt className="text-[10px] text-slate-400">{label}</dt>
      <dd className={`text-xs mt-0.5 ${value ? 'text-slate-800 font-medium' : 'text-slate-400'}`}>{value || missing}</dd>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg p-2 bg-slate-50">
      <div className="text-[10px] text-slate-400">{label}</div>
      <div className="text-sm font-semibold text-slate-800 mt-0.5">{value}</div>
      {hint && <div className="text-[10px] text-slate-400 mt-0.5">{hint}</div>}
    </div>
  );
}
