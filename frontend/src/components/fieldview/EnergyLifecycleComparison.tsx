import { useRef, useState } from 'react';
import { kongApi } from '../../services/api/client';
import { getAuthScope } from '../../lib/authStorage';

const labels = {grid:'الشبكة', diesel:'الديزل', solar:'الشمس'};
type CostRow = {source:keyof typeof labels;capex:number;annual_opex:number;discounted_cost:number;incremental_roi_pct:number|null};
type Comparison = {currency:string;options:CostRow[]};
const template = {
  currency: 'YER', horizon_years: 10, discount_rate: 0.05, baseline: 'grid',
  options: Object.keys(labels).map(source=>({
    source, source_ref:'', annual_delivered_m3:null,annual_energy_kwh:null,
    energy_price_per_kwh:null,annual_maintenance:null,
    boq:[{item:'',unit:'',quantity:null,unit_price:null,service_life_years:null}],
  })),
};

export default function EnergyLifecycleComparison({ authScope, areaHa }: {authScope:string;areaHa:number}) {
  const [input,setInput]=useState('');
  const [comparison,setComparison]=useState<Comparison|null>(null);
  const [error,setError]=useState('');
  const revision=useRef(0);
  async function compare(){
    const request=++revision.current;
    setError('');setComparison(null);
    try {
      const scenario=JSON.parse(input);
      const {data}=await kongApi.post('/api/v1/economics/feasibility',{
        area_ha:areaHa, yield_t_per_ha:0, price_per_t:0, lifecycle_scenario:scenario,
      },{expectedAuthScope:authScope});
      if(request!==revision.current || getAuthScope()!==authScope) return;
      const result=data?.lifecycle_scenario as Comparison|undefined;
      if(!result || result.options?.length!==3) throw new Error('incomplete response');
      setComparison(result);
    } catch {
      if(request===revision.current && getAuthScope()===authScope) setError('تعذرت المقارنة. تحقق من ملف عروض الأسعار والعملة ومصدر كل بديل.');
    }
  }
  return <details className="mt-4 border-t border-slate-700 pt-3"><summary>مقارنة دورة حياة الشبكة والديزل والطاقة الشمسية</summary>
    <p>أدخل عروض الأسعار بعملة واحدة. تشمل تكلفة الطاقة لكل kWh كلفة الوقود المحوّل إلى كهرباء للديزل. يتطلب العائد المقارن حجم مياه سنويًا متساويًا.</p>
    <button type="button" onClick={()=>{revision.current++;setInput(JSON.stringify(template,null,2));setComparison(null);setError('');}}>تحميل قالب إدخال الأسعار</button>
    <label className="block">بنود الكميات والأسعار والافتراضات (JSON)
      <textarea dir="ltr" className="block w-full bg-slate-900" rows={8} value={input} onChange={e=>{revision.current++;setInput(e.target.value);setComparison(null);setError('');}}/></label>
    <button type="button" disabled={!input.trim()} onClick={compare}>قارن تكاليف الطاقة</button>
    {error && <p role="alert">{error}</p>}
    {comparison && <table><caption>تقديرات بالعملة {comparison.currency}</caption><thead><tr>{['المصدر','تكلفة التأسيس','التشغيل السنوي','التكلفة المخصومة','العائد الإضافي %'].map(x=><th key={x}>{x}</th>)}</tr></thead>
      <tbody>{comparison.options.map(r=><tr key={r.source}><th>{labels[r.source]}</th>{[r.capex,r.annual_opex,r.discounted_cost,r.incremental_roi_pct].map((n,i)=><td key={i}>{n==null?'—':n.toLocaleString('ar')}</td>)}</tr>)}</tbody></table>}
  </details>;
}
