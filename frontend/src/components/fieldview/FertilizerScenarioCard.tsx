import { useState } from 'react';
import { useTenantId } from '../../hooks/useAuth';
import { useNutrient4rPlan } from '../../hooks/useWaterFieldOps';
import {
  acceptedFertilizerEstimate, buildFertilizerScenario,
  type FertilizerScenarioForm, type FertilizerScenarioInput,
} from '../../lib/fertilizerScenario';
import { fmtNum } from '../../lib/waterFieldOps';
import { T } from '../ds';

const numericFields = [
  ['target_yield_t_ha', 'الغلة المستهدفة (طن/هكتار)'],
  ['uptake_kg_per_t', 'امتصاص المغذي (كغ/طن)'],
  ['soil_supply_kg_ha', 'إمداد التربة (كغ/هكتار)'],
  ['fertilizer_grade_pct', 'تركيز المغذي في المنتج (%)'],
  ['use_efficiency', 'كفاءة الاستخدام (0.1–1)'],
] as const;

function ScenarioForm() {
  const [form, setForm] = useState<FertilizerScenarioForm>({
    input_basis: 'synthetic', nutrient_basis: 'N', source_ref: '',
    target_yield_t_ha: '', uptake_kg_per_t: '', soil_supply_kg_ha: '',
    fertilizer_grade_pct: '', use_efficiency: '',
  });
  const [submitted, setSubmitted] = useState<FertilizerScenarioInput | null>(null);
  const update = <K extends keyof FertilizerScenarioForm>(key: K, value: FertilizerScenarioForm[K]) => {
    setSubmitted(null);
    setForm(previous => ({ ...previous, [key]: value }));
  };
  const candidate = buildFertilizerScenario(form);
  // Separate from the approved field-sample query. This request never carries a field ID.
  const query = useNutrient4rPlan(submitted ? { fertilizer_scenario: submitted } : null, null);
  const estimate = submitted && !query.isError && !query.isLoading
    ? acceptedFertilizerEstimate(query.data?.fertilizer_scenario, submitted) : null;
  return (
    <section aria-label="محاكاة كمية السماد" className="flex flex-col gap-2 rounded-lg border p-2" style={{ borderColor: T.line }}>
      <b style={{ color: T.ink }}>محاكاة كمية السماد التجاري (4R)</b>
      <p className="text-[11px]" style={{ color: T.muted }}>
        افتراضات مستقلة عن عينة الحقل المعتمدة. لا تمثل وصفة أو تفويض تنفيذ أو مطابقة محلية.
        أدخل كل القيم على أساس المغذي نفسه؛ مرجع المصدر يُذكر ولا يُتحقق منه هنا.
      </p>
      <label>أساس المدخلات
        <select value={form.input_basis} onChange={e => update('input_basis', e.target.value === 'synthetic' ? 'synthetic' : 'operator_supplied')}>
          <option value="synthetic">اصطناعية</option>
          <option value="operator_supplied">مدخلات المشغّل</option>
        </select>
      </label>
      <label>أساس المغذي
        <select value={form.nutrient_basis} onChange={e => update('nutrient_basis', e.target.value as FertilizerScenarioForm['nutrient_basis'])}>
          <option value="N">N</option><option value="P2O5">P₂O₅</option><option value="K2O">K₂O</option>
        </select>
      </label>
      <label>مرجع الافتراضات
        <input value={form.source_ref} maxLength={500} onChange={e => update('source_ref', e.target.value)} />
      </label>
      {numericFields.map(([key, label]) => (
        <label key={key}>{label}
          <input type="number" step="any" value={form[key]} onChange={e => update(key, e.target.value)} />
        </label>
      ))}
      <button type="button" disabled={!candidate || query.isFetching}
        onClick={() => { if (candidate) setSubmitted(candidate); }}>
        احسب التقدير على الخادم
      </button>
      {submitted && query.isLoading && <p role="status">جارٍ الحساب…</p>}
      {submitted && query.isError && <p role="alert">تعذّر الحساب على الخادم. لا يوجد تقدير معتمد.</p>}
      {submitted && !query.isLoading && !query.isError && !estimate && (
        <p role="status">لم يُعد الخادم تقديرًا مطابقًا للمدخلات مع حدود الاعتماد المطلوبة.</p>
      )}
      {estimate && submitted && (
        <dl aria-label="تقدير الخادم" className="grid grid-cols-2 gap-1">
          <dt>المغذي المطلوب ({submitted.nutrient_basis}، كغ/هكتار)</dt>
          <dd>{fmtNum(estimate.nutrient_to_apply_kg_ha, 2)}</dd>
          <dt>السماد التجاري (كغ/هكتار)</dt>
          <dd>{fmtNum(estimate.product_kg_ha, 2)}</dd>
          <dt>مرجع الافتراضات (غير متحقق)</dt><dd>{submitted.source_ref}</dd>
        </dl>
      )}
    </section>
  );
}

export default function FertilizerScenarioCard() {
  const tenantId = useTenantId();
  // A tenant change unmounts the scenario and clears both assumptions and result.
  return tenantId ? <ScenarioForm key={tenantId} /> : null;
}
