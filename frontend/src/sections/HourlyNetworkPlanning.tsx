import type { HourlyNetworkPlan } from '../services/api/irrigationNetworkCalculator';

export type HourlyDraft = {
  source: string; start: string; capacity: string; derate: string; temperatureCoefficient: string;
  curve: string; hours: string;
};
export const emptyHourlyDraft: HourlyDraft = {
  source: '', start: '', capacity: '', derate: '', temperatureCoefficient: '', curve: '', hours: '',
};

function numbers(value: string, count: number) {
  const parts = value.split(',').map(s => s.trim());
  if (parts.length !== count || parts.some(s => !s || !Number.isFinite(Number(s)))) {
    throw new Error('أكمل أرقام كل سطر وافصل الأعمدة بفاصلة إنجليزية.');
  }
  return parts.map(Number);
}

export function hourlyPayload(draft: HourlyDraft, fieldId: string) {
  if (!draft.source.trim() || !draft.start || [draft.capacity, draft.derate, draft.temperatureCoefficient].some(s => !s.trim())) {
    throw new Error('أدخل مصدر البيانات ووقت البداية وخصائص المصفوفة الشمسية.');
  }
  return {
    source_ref: draft.source.trim(), start_at: new Date(draft.start + 'Z').toISOString(),
    pv: { capacity_kwp: Number(draft.capacity), derate: Number(draft.derate), temperature_coefficient_per_c: Number(draft.temperatureCoefficient) },
    curve: draft.curve.trim().split(/\r?\n/).map(line => {
      const [flow_m3_h, head_m, efficiency] = numbers(line, 3);
      return { flow_m3_h, head_m, efficiency };
    }),
    hours: draft.hours.trim().split(/\r?\n/).map(line => {
      const [demand_m3, ...rates] = numbers(line, 6);
      return { demand_m3, well_inflows_m3_h: Object.fromEntries(rates.slice(0,3).map((q,i)=>[`well:${fieldId}:${i+1}`,q])),
        irradiance_w_m2: rates[3], ambient_temp_c: rates[4] };
    }),
  };
}

export function HourlyInputs({ value, onChange }: {value: HourlyDraft; onChange: (value: HourlyDraft) => void}) {
  const fields = [
    ['source','مصدر المنحنى والتوقعات','text'],['start','بداية أول ساعة (UTC)','datetime-local'],
    ['capacity','القدرة الشمسية الاسمية (kWp)','number'],['derate','معامل خفض القدرة (0–1)','number'],
    ['temperatureCoefficient','معامل الحرارة لكل درجة مئوية','number'],
  ] as const;
  return <div className="grid gap-3">
    {fields.map(([key,label,type]) => <label key={key}>{label}<input className="block w-full bg-slate-900" type={type} step="any" value={value[key]} onChange={e=>onChange({...value,[key]:e.target.value})} /></label>)}
    <label>منحنى البوستر — سطر لكل نقطة (م³/ساعة، رأس بالمتر، كفاءة عشرية)
      <textarea dir="ltr" className="block w-full bg-slate-900" placeholder={'100,80,0.75\n200,65,0.80'} value={value.curve} onChange={e=>onChange({...value,curve:e.target.value})}/></label>
    <label>الساعات — الطلب (م³)، تدفق البئر 1، 2، 3 (م³/ساعة)، الإشعاع (W/m²)، الحرارة (°C)
      <textarea dir="ltr" className="block w-full bg-slate-900" placeholder="200,60,70,80,800,25" value={value.hours} onChange={e=>onChange({...value,hours:e.target.value})}/></label>
    <p>أدخل صفًا لكل ساعة متتالية. يجب أن يساوي مجموع الطلب الحجم المطلوب أعلاه.</p>
  </div>;
}

export function HourlySummary({plan}:{plan:HourlyNetworkPlan}) {
  return <section aria-label="نتائج المحاكاة الساعية" className="mt-3 rounded-xl border border-cyan-900 p-3">
    <p>العجز خلال الفترة <b>{plan.unmet_m3.toFixed(2)} م³</b> · رأس الضخ المطلوب {plan.required_tdh_m.toFixed(2)} م</p>
    <p>تقدير عند نقطة تشغيل ثابتة. قدرة الآبار الكهربائية خارج هذا الحساب.</p>
    {plan.constraints.length>0 && <p role="status">{plan.constraints.join('، ')}</p>}
    <div className="max-h-72 overflow-auto"><table><thead><tr>{['الساعة (UTC)','الشمس kW','المسلّم م³','نهاية البركة م³','فائض م³','البوستر kWh'].map(t=><th key={t}>{t}</th>)}</tr></thead>
    <tbody>{plan.hours.map(h=><tr key={h.at}><td>{h.at}</td>{[h.pv_kw,h.delivered_m3,h.end_storage_m3,h.spill_m3,h.energy_used_kwh].map((n,i)=><td key={i}>{n.toFixed(2)}</td>)}</tr>)}</tbody></table></div>
    <a download="sahool-duty.inp" href={'data:text/plain;charset=utf-8,'+encodeURIComponent(plan.epanet_duty_inp)}>تنزيل نموذج خط التوصيل لنقطة التشغيل بصيغة EPANET</a>
  </section>;
}
