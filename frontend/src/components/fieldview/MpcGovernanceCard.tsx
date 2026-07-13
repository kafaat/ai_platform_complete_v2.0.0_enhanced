import { Droplets, ShieldCheck, Layers, Ban } from 'lucide-react';
import { useMpcCapabilities } from '../../hooks/useApi';
import { T } from '../ds';

interface Props {
  /** يظهر في وضع الخبير فقط — نقطة العقد ثابتة (لا تعتمد على حقل مختار). */
  enabled?: boolean;
}

// القدرات المُنمذَجة (J1..J4) → تسمية عربيّة موجزة. مفتاح مجهول ⇒ يُعرَض كما هو (لا إخفاء).
const MODELED_AR: Record<string, string> = {
  crop_protection_raw: 'J1 · حماية المحصول (Dr ≤ RAW + إجهاد المراحل الحرجة)',
  water_and_deep_percolation_min: 'J2 · تقليل الماء والرشح العميق',
  yield_ky_forecast_horizon: 'J3 · غلّة Ky (FAO-33) على أفق التنبّؤ',
  water_cost_proxy: 'J4 · وكيل تكلفة الماء (m³ × سعر — لا إيراد)',
};

// الحقول المُؤجَّلة صراحةً → تسمية عربيّة (تُعلَن ولا تُلفَّق).
const NOT_MODELED_AR: Record<string, string> = {
  predicted_energy_kwh: 'طاقة متوقّعة (kWh) — طبقة الطاقة/المضخّة',
  source_well_id: 'معرّف البئر المصدر — نموذج الآبار',
  start_at: 'وقت البدء — أفق ساعيّ',
  duration_minutes: 'مدّة التشغيل — معدّل تطبيق/تدفّق',
  zone_id: 'قرار على مستوى المناطق',
  'economic_margin_delta.revenue': 'إيراد الهامش الاقتصاديّ (وكيل تكلفة فقط)',
  water_ledger_snapshot: 'لقطة دفتر الماء (تُوصَل في السلسلة)',
  forecast_source_hash: 'بصمة مصدر الطقس',
};

/** بطاقة حوكمة متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC) — شفافيّة قدرات
 *  قراءة فقط: السلّم المعجميّ المُنمذَج (J1≻J2≻J3≻J4) مقابل المُؤجَّل صراحةً (طاقة/آبار/
 *  أفق ساعيّ)، وإصدار الحلّال، وأنّه **توصية-فقط** بنيويّاً (لا تنفيذ تلقائيّ). تستهلك
 *  نقطة العقد `/api/v1/irrigation/mpc/capabilities` مباشرةً — لا مدخلات ولا تلفيق. عند
 *  تعذّر القراءة (503/شبكة) تُظهِر حالة فارغة صادقة لا قيمة مُختلَقة. */
export default function MpcGovernanceCard({ enabled = true }: Props) {
  const { data, isLoading, isError } = useMpcCapabilities(enabled);

  if (!enabled) return null;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="mpc-governance"
      aria-label="حوكمة متحكّم الريّ الهرميّ"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplets className="w-4 h-4 text-sky-300" aria-hidden="true" /> متحكّم الريّ الهرميّ (توصية-فقط)
        </span>
      </div>

      {isLoading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة قدرات الحلّال…</div>
      ) : isError || !data ? (
        <div className="text-[11px]" style={{ color: T.muted }}>
          تعذّر قراءة قدرات متحكّم الريّ (المنصّة/العقد غير متاح الآن) — لا قيمة مُختلَقة.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {/* الإصدار + الطابع التوصويّ البنيويّ */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]" style={{ color: T.muted }}>
            <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold" style={{ color: T.ok, background: T.okBg }}>
              {data.recommendation_only ? 'توصية-فقط' : 'تنفيذيّ'}
            </span>
            {!data.execution_allowed && (
              <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-semibold"
                style={{ color: T.faint, border: `1px solid ${T.line}` }}>
                <ShieldCheck className="w-3 h-3" aria-hidden="true" /> لا تنفيذ تلقائيّ
              </span>
            )}
            <span style={{ color: T.faint }}>الإصدار {data.solver_version}</span>
          </div>

          {/* القدرات المُنمذَجة (السلّم المعجميّ) */}
          {data.modeled_capabilities.length > 0 && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                <Layers className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" /> مُنمذَج (السلّم المعجميّ):
              </span>
              {data.modeled_capabilities.map((c) => (
                <div key={c} className="text-[10px]" style={{ color: T.ok }}>✓ {MODELED_AR[c] ?? c}</div>
              ))}
            </div>
          )}

          {/* المُؤجَّل صراحةً — صدق: يُعلَن ولا يُلفَّق */}
          {data.not_modeled.length > 0 && (
            <div className="flex flex-col gap-1 rounded-xl border p-2" style={{ borderColor: T.line, background: 'rgba(15,23,42,.35)' }}>
              <span className="inline-flex items-center gap-1.5 text-[11px] font-bold" style={{ color: T.ink }}>
                <Ban className="w-3.5 h-3.5" style={{ color: '#fdba74' }} aria-hidden="true" /> مُؤجَّل صراحةً:
              </span>
              {data.not_modeled.map((c) => (
                <div key={c} className="text-[10px]" style={{ color: '#fdba74' }}>⟲ {NOT_MODELED_AR[c] ?? c}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
