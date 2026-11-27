import EnergyLifecycleComparison from './EnergyLifecycleComparison';
import { useRef, useState } from 'react';
import { kongApi } from '../../services/api/client';
import { useCostCategories } from '../../hooks/useManagerConsole';
import { getAuthScope } from '../../lib/authStorage';

type Pump = 'grid' | 'diesel' | 'solar';
const COMMON = [
  ['yield_t_per_ha', 'الغلة المتوقعة (طن/هكتار)'],
  ['price_per_t', 'سعر الطن المتوقع (عملة تقديرك)'],
  ['pumped_m3_per_ha', 'حجم الضخ الموسمي (م³/هكتار)'],
  ['well_depth_m', 'عمق البئر المستخدم في التقدير (م)'],
] as const;
const SPECIFIC: Record<Pump, ReadonlyArray<readonly [string, string]>> = {
  grid: [['grid_price_usd_per_kwh', 'سعر الكهرباء (USD/kWh)'], ['grid_efficiency', 'كفاءة الضخ (0–1)']],
  diesel: [['diesel_price_usd_per_liter', 'سعر الديزل (USD/L)'], ['diesel_kwh_per_liter', 'طاقة العمود المتاحة (kWh/L)'], ['pump_efficiency', 'كفاءة الضخ (0–1)']],
  solar: [['solar_capital_usd', 'رأس المال (USD)'], ['solar_lifetime_years', 'العمر (سنوات)'], ['solar_maintenance_annual_pct', 'الصيانة السنوية (كسر عشري)'], ['solar_m3_per_year', 'حجم الضخ السنوي قبل فاقد الغبار عند عمق مرجعي 100 متر (م³)'], ['solar_dust_derate_pct', 'فاقد الغبار (كسر عشري)']],
};
type Estimate = {
  status: 'estimated' | 'not_evaluated';
  currency: string;
  scope: string;
  included_in_feasibility: boolean;
  estimate?: { cost_low_usd: number; cost_mid_usd: number; cost_high_usd: number; total_m3: number };
};

export default function PumpingCostScenarioCard({ areaHa, authScope }: { areaHa: number | null; authScope: string }) {
  const [pump, setPump] = useState<Pump>('grid');
  const [basis, setBasis] = useState<'synthetic' | 'operator_estimate'>('operator_estimate');
  const [source, setSource] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Estimate | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  const capabilities = useCostCategories(Boolean(authScope), 0);
  const fields = [...COMMON, ...SPECIFIC[pump]];
  function invalidate() {
    revision.current += 1;
    setResult(null);
    setError('');
    setBusy(false);
  }
  async function calculate() {
    invalidate();
    const id = revision.current;
    if (!authScope || getAuthScope() !== authScope) return;
    if (areaHa == null || !Number.isFinite(areaHa) || areaHa <= 0 || !source.trim() ||
        fields.some(([k]) => !values[k]?.trim() || !Number.isFinite(Number(values[k])) || Number(values[k]) < 0)) {
      setError('أدخل مساحة صالحة وجميع القيم ومصدر التقدير.');
      return;
    }
    const numeric = Object.fromEntries(fields.map(([k]) => [k, Number(values[k])]));
    const { yield_t_per_ha, price_per_t, ...scenario } = numeric;
    setBusy(true);
    try {
      const { data } = await kongApi.post('/api/v1/economics/feasibility', {
        area_ha: areaHa, yield_t_per_ha, price_per_t,
        water_cost_scenario: { ...scenario, pump_type: pump, input_basis: basis, source_ref: source.trim() },
      }, { expectedAuthScope: authScope });
      if (id !== revision.current || getAuthScope() !== authScope) return;
      const value = data?.water_cost_scenario as Estimate | undefined;
      if (!value || value.currency !== 'USD' || value.scope !== 'well_pumping_only' ||
          value.included_in_feasibility !== false ||
          (value.status === 'estimated' && (!value.estimate ||
            ![value.estimate.cost_low_usd, value.estimate.cost_mid_usd, value.estimate.cost_high_usd, value.estimate.total_m3].every(Number.isFinite))) ||
          !['estimated', 'not_evaluated'].includes(value.status)) {
        setError('لم يرجع الخادم تقديراً صالحاً.');
        return;
      }
      setResult(value);
    } catch {
      if (id === revision.current && getAuthScope() === authScope) setError('تعذر التقييم؛ تحقق من المدخلات أو الاتصال.');
    } finally {
      if (id === revision.current && getAuthScope() === authScope) setBusy(false);
    }
  }
  if (!authScope || capabilities.isFetching || capabilities.isError ||
      capabilities.data?.supports_well_pumping_scenario !== true) return null;

  return (
    <section className="mb-3 rounded-xl border border-slate-700 p-3 text-sm text-slate-200" aria-label="سيناريو تكلفة ضخ الآبار">
      <h3 className="font-semibold">سيناريو تكلفة ضخ الآبار الموسمية</h3>
      <p className="text-xs text-slate-400">تقدير بالدولار منفصل عن الربحية والسجل الفعلي. يستثني البوستر والتوزيع؛ العمق ليس الرأس الديناميكي المقاس. لا يمثل محاكاة شمسية ساعية.</p>
      <label className="block">مصدر الطاقة
        <select value={pump} onChange={e => { invalidate(); setPump(e.target.value as Pump); setValues({}); }} className="bg-slate-900">
          <option value="grid">كهرباء</option><option value="diesel">ديزل</option><option value="solar">شمسي</option>
        </select>
      </label>
      <label className="block">نوع المدخلات
        <select value={basis} onChange={e => { invalidate(); setBasis(e.target.value as typeof basis); }} className="bg-slate-900">
          <option value="operator_estimate">تقدير المشغل</option><option value="synthetic">اصطناعي للاختبار</option>
        </select>
      </label>
      <label className="block">مرجع التقدير<input value={source} maxLength={512} onChange={e => { invalidate(); setSource(e.target.value); }} className="block bg-slate-900" /></label>
      <div className="grid grid-cols-2 gap-2">
        {fields.map(([key, label]) => <label key={key} className="text-xs">{label}
          <input type="number" min="0" step="any" value={values[key] ?? ''} onChange={e => { invalidate(); setValues(v => ({ ...v, [key]: e.target.value })); }} className="block w-full bg-slate-900" />
        </label>)}
      </div>
      <button type="button" disabled={busy} onClick={() => void calculate()} className="mt-2 rounded border border-slate-500 p-2">{busy ? 'جارٍ الحساب…' : 'احسب تكلفة الضخ'}</button>
      {error && <p role="alert">{error}</p>}
      {result?.status === 'not_evaluated' && <p role="status">لم يكتمل تقييم تكلفة الضخ.</p>}
      {result?.status === 'estimated' && result.estimate && <div role="status">
        <p>النطاق الموسمي (USD): {result.estimate.cost_low_usd} – {result.estimate.cost_high_usd}</p>
        <p>التقدير الأوسط (USD): {result.estimate.cost_mid_usd}</p>
        <p>حجم الضخ (م³): {result.estimate.total_m3}</p>
      </div>}
      {capabilities.data?.supports_energy_lifecycle && areaHa != null && areaHa > 0 && <EnergyLifecycleComparison key={authScope} authScope={authScope} areaHa={areaHa}/>}
    </section>
  );
}
