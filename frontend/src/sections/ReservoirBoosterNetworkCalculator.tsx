import { useState } from 'react';
import { emptyHourlyDraft, HourlyInputs, hourlyPayload, HourlySummary } from './HourlyNetworkPlanning';
import { Network } from 'lucide-react';
import { useTenantId } from '../hooks/useAuth';
import {
  calculateReservoirBoosterNetwork,
  type IrrigationNetworkResult,
  type NetworkIrrigationSystemType,
} from '../services/api/irrigationNetworkCalculator';

const num = (v: string, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback;
const show = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—';

function F({ label, value, onChange, unit }: {label:string;value:string;onChange:(v:string)=>void;unit?:string}) {
  return <label className="space-y-1 text-xs text-slate-400"><span>{label}</span><div className="flex rounded-lg border border-slate-700 bg-slate-950"><input type="number" min="0" step="any" value={value} onChange={e=>onChange(e.target.value)} className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-slate-100 outline-hidden"/>{unit && <span className="border-r border-slate-700 px-2 py-2 text-slate-500">{unit}</span>}</div></label>;
}

const systemLabels: Record<NetworkIrrigationSystemType, string> = {
  none: 'بدون جهاز — بركة وبوستر وخط فقط',
  center_pivot: 'محور مركزي',
  linear_move: 'حركة خطية',
  reel: 'بكرة ري / مدفع متنقل',
  sprinkler: 'رشاشات ثابتة',
  drip: 'تنقيط',
  valve_network: 'شبكة صمامات ومناطق',
};

export default function ReservoirBoosterNetworkCalculator({ fieldId, seasonId }: {fieldId:string;seasonId?:string|null}) {
  const tenantId = useTenantId();
  return <ReservoirNetworkForm key={JSON.stringify([tenantId, fieldId, seasonId])} tenantId={tenantId} fieldId={fieldId} seasonId={seasonId} />;
}

function ReservoirNetworkForm({ tenantId, fieldId, seasonId }: {tenantId:ReturnType<typeof useTenantId>;fieldId:string;seasonId?:string|null}) {
  const [systemType,setSystemType]=useState<NetworkIrrigationSystemType>('none');
  const [busy,setBusy]=useState(false); const [error,setError]=useState<string|null>(null); const [result,setResult]=useState<IrrigationNetworkResult|null>(null);
  const [hourly,setHourly]=useState(false);
  const [hourlyValues,setHourlyValues]=useState(emptyHourlyDraft);
  const [f,setF]=useState({volume:'11000',well1:'80',well2:'80',well3:'80',reservoirCapacity:'4000',reservoirCurrent:'3500',reservoirMinimum:'500',reservoirEvaporation:'0',reservoirSeepage:'0',boosterFlow:'230',boosterHead:'70',boosterMotor:'60',boosterPumpEfficiency:'0.78',boosterMotorEfficiency:'0.92',pipeLength:'1000',diameter:'250',c:'140',elevation:'8',minorLoss:'5',safety:'5',systemName:'نظام الري 1',systemFlow:'230',systemPressure:'3.2',radius:'399',arc:'360',machineLength:'400',travelLength:'1000',hoseLength:'400',hoseDiameter:'110',zoneCount:'8',concurrentZones:'2',emitterCount:'12000',emitterFlow:'4',sprinklerCount:'40',sprinklerFlow:'5.75',wettedArea:'50'});
  // Any edit invalidates the previous result (+ its digest); clear it so nothing stale shows.
  const invalidate=()=>{if(result)setResult(null);if(error)setError(null);};
  const set=(k:string,v:string)=>{setF(p=>({...p,[k]:v}));invalidate();};
  const changeSystem=(v:NetworkIrrigationSystemType)=>{setSystemType(v);invalidate();};
  const hasSystem=systemType!=='none';

  async function run(){
    if(!tenantId){setError('هوية المستأجر غير متاحة.');return;}
    setBusy(true);setError(null);setResult(null);
    let hourlyScenario;
    try { if(hourly) hourlyScenario=hourlyPayload(hourlyValues,fieldId); } catch(e) {setError(e instanceof Error ? e.message : 'تعذر قراءة الساعات');setBusy(false);return;}
    try{setResult(await calculateReservoirBoosterNetwork({
      ...(hourlyScenario && {hourlyScenario}),tenantId,fieldId,seasonId,requiredGrossVolumeM3:num(f.volume),wellFlowsM3h:[num(f.well1),num(f.well2),num(f.well3)],
      reservoirCapacityM3:num(f.reservoirCapacity),reservoirCurrentM3:num(f.reservoirCurrent),reservoirMinimumM3:num(f.reservoirMinimum),
      reservoirEvaporationM3h:num(f.reservoirEvaporation),reservoirSeepageM3h:num(f.reservoirSeepage),
      boosterFlowM3h:num(f.boosterFlow),boosterHeadM:num(f.boosterHead),boosterMotorKw:num(f.boosterMotor),boosterPumpEfficiency:num(f.boosterPumpEfficiency),boosterMotorEfficiency:num(f.boosterMotorEfficiency),
      pipeLengthM:num(f.pipeLength),pipeDiameterMm:num(f.diameter),hazenWilliamsC:num(f.c),elevationChangeM:num(f.elevation),minorLossM:num(f.minorLoss),safetyMarginM:num(f.safety),
      systemType,systemName:f.systemName,systemFlowM3h:hasSystem?num(f.systemFlow):undefined,systemPressureBar:hasSystem?num(f.systemPressure):undefined,
      radiusM:systemType==='center_pivot'?num(f.radius):undefined,operatingArcDeg:systemType==='center_pivot'?num(f.arc):undefined,
      machineLengthM:systemType==='linear_move'?num(f.machineLength):undefined,travelLengthM:systemType==='linear_move'?num(f.travelLength):undefined,
      hoseLengthM:systemType==='reel'?num(f.hoseLength):undefined,hoseDiameterMm:systemType==='reel'?num(f.hoseDiameter):undefined,
      zoneCount:['drip','valve_network'].includes(systemType)?num(f.zoneCount):undefined,concurrentZones:['drip','valve_network'].includes(systemType)?num(f.concurrentZones):undefined,
      emitterCount:systemType==='drip'?num(f.emitterCount):undefined,emitterFlowLph:systemType==='drip'?num(f.emitterFlow):undefined,
      sprinklerCount:systemType==='sprinkler'?num(f.sprinklerCount):undefined,sprinklerFlowM3h:systemType==='sprinkler'?num(f.sprinklerFlow):undefined,
      wettedAreaHa:hasSystem?num(f.wettedArea):undefined,
    }));}
    catch(e){const d=(e as {response?:{data?:{detail?:unknown}}})?.response?.data?.detail;setError(typeof d==='string'?d:Array.isArray(d)?d.map(x=>(x as {msg?:string}).msg).filter(Boolean).join('، '):'تعذر حساب شبكة الري.');}finally{setBusy(false);}
  }

  return <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" aria-label="حاسبة شبكة الري متعددة الأنظمة">
    <div className="mb-4 flex items-center gap-2"><Network className="h-5 w-5 text-cyan-300"/><div><h2 className="font-bold text-slate-100">البركة والبوستر وشبكة الري متعددة الأنظمة</h2><p className="text-xs text-slate-500">حساب مستقل للحقل المحدد: ثلاثة آبار وبركة وبوستر واحد. يمكن أن تشمل الشبكة محوراً أو جهاز ري آخر؛ إضافة جهاز الري اختيارية. القيم الابتدائية أمثلة حسابية وليست قياسات ميدانية.</p></div></div>
    <fieldset disabled={busy} className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">الماء والآبار</h3><F label="الحجم المطلوب" value={f.volume} onChange={v=>set('volume',v)} unit="م³"/><div className="grid grid-cols-3 gap-2"><F label="بئر 1" value={f.well1} onChange={v=>set('well1',v)} unit="م³/ساعة"/><F label="بئر 2" value={f.well2} onChange={v=>set('well2',v)} unit="م³/ساعة"/><F label="بئر 3" value={f.well3} onChange={v=>set('well3',v)} unit="م³/ساعة"/></div></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">بركة التجميع</h3><F label="السعة" value={f.reservoirCapacity} onChange={v=>set('reservoirCapacity',v)} unit="م³"/><F label="الحجم الحالي" value={f.reservoirCurrent} onChange={v=>set('reservoirCurrent',v)} unit="م³"/><F label="الحد الأدنى" value={f.reservoirMinimum} onChange={v=>set('reservoirMinimum',v)} unit="م³"/><F label="فاقد التبخر" value={f.reservoirEvaporation} onChange={v=>set('reservoirEvaporation',v)} unit="م³/ساعة"/><F label="فاقد التسرب" value={f.reservoirSeepage} onChange={v=>set('reservoirSeepage',v)} unit="م³/ساعة"/><p className="text-xs text-slate-400">الصفر افتراض للحساب، وليس قياسًا للفواقد. أدخل تقديرًا موثقًا إن توفر.</p></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">البوستر والخط</h3><F label="تدفق البوستر" value={f.boosterFlow} onChange={v=>set('boosterFlow',v)} unit="م³/ساعة"/><F label="Head التصميمي" value={f.boosterHead} onChange={v=>set('boosterHead',v)} unit="م"/><F label="قدرة المحرك" value={f.boosterMotor} onChange={v=>set('boosterMotor',v)} unit="kW"/><F label="كفاءة المضخة (0–1)" value={f.boosterPumpEfficiency} onChange={v=>set('boosterPumpEfficiency',v)}/><F label="كفاءة المحرك (0–1)" value={f.boosterMotorEfficiency} onChange={v=>set('boosterMotorEfficiency',v)}/><div className="grid grid-cols-2 gap-2"><F label="طول الخط" value={f.pipeLength} onChange={v=>set('pipeLength',v)} unit="م"/><F label="قطر الخط" value={f.diameter} onChange={v=>set('diameter',v)} unit="مم"/></div></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">نوع نظام الري</h3><select value={systemType} onChange={e=>changeSystem(e.target.value as NetworkIrrigationSystemType)} className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-slate-100">{Object.entries(systemLabels).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>{hasSystem&&<div className="space-y-2 rounded-xl border border-emerald-900/60 bg-emerald-950/10 p-3"><label className="text-xs text-slate-400">اسم النظام<input value={f.systemName} onChange={e=>set('systemName',e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"/></label><div className="grid grid-cols-2 gap-2"><F label="التدفق التصميمي" value={f.systemFlow} onChange={v=>set('systemFlow',v)} unit="م³/ساعة"/><F label="ضغط الدخول" value={f.systemPressure} onChange={v=>set('systemPressure',v)} unit="bar"/><F label="المساحة المروية" value={f.wettedArea} onChange={v=>set('wettedArea',v)} unit="هكتار"/>
      {systemType==='center_pivot'&&<><F label="نصف القطر" value={f.radius} onChange={v=>set('radius',v)} unit="م"/><F label="قوس التشغيل" value={f.arc} onChange={v=>set('arc',v)} unit="°"/></>}
      {systemType==='linear_move'&&<><F label="طول الجهاز" value={f.machineLength} onChange={v=>set('machineLength',v)} unit="م"/><F label="طول المسار" value={f.travelLength} onChange={v=>set('travelLength',v)} unit="م"/></>}
      {systemType==='reel'&&<><F label="طول الخرطوم" value={f.hoseLength} onChange={v=>set('hoseLength',v)} unit="م"/><F label="قطر الخرطوم" value={f.hoseDiameter} onChange={v=>set('hoseDiameter',v)} unit="مم"/></>}
      {['drip','valve_network'].includes(systemType)&&<><F label="عدد المناطق" value={f.zoneCount} onChange={v=>set('zoneCount',v)}/><F label="مناطق متزامنة" value={f.concurrentZones} onChange={v=>set('concurrentZones',v)}/></>}
      {systemType==='drip'&&<><F label="عدد النقاطات" value={f.emitterCount} onChange={v=>set('emitterCount',v)}/><F label="تصريف النقاط" value={f.emitterFlow} onChange={v=>set('emitterFlow',v)} unit="لتر/ساعة"/></>}
      {systemType==='sprinkler'&&<><F label="عدد الرشاشات" value={f.sprinklerCount} onChange={v=>set('sprinklerCount',v)}/><F label="تصريف الرشاش" value={f.sprinklerFlow} onChange={v=>set('sprinklerFlow',v)} unit="م³/ساعة"/></>}
      </div></div>}<button disabled={busy} onClick={run} className="w-full rounded-xl bg-cyan-400 px-4 py-3 text-sm font-bold text-slate-950 disabled:opacity-50">{busy?'جارٍ الحساب…':'احسب الشبكة'}</button>{error&&<p className="rounded-lg border border-rose-800 bg-rose-950/30 p-2 text-xs text-rose-300">{error}</p>}</div>
      <div className="space-y-2 lg:col-span-4"><label><input type="checkbox" checked={hourly} onChange={e=>{setHourly(e.target.checked);invalidate();}}/> محاكاة البوستر الشمسي ساعة بساعة</label>
        {hourly && <HourlyInputs value={hourlyValues} onChange={v=>{setHourlyValues(v);invalidate();}}/>}</div>
    </fieldset>
    {result?.reservoir_balance.hourly_scenario && <HourlySummary plan={result.reservoir_balance.hourly_scenario}/>}
    {result&&<div className="mt-5 border-t border-slate-800 pt-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5 text-sm"><div className="rounded-xl bg-slate-900 p-3">الحالة: <b>{result.status}</b></div><div className="rounded-xl bg-slate-900 p-3">النظام: <b>{result.machine_mode==='none'?'غير مضاف':String(result.selected_machines[0]?.system_type ?? 'مضاف')}</b></div><div className="rounded-xl bg-slate-900 p-3">صافي البركة: <b>{show(result.reservoir_balance.net_change_m3_h)} م³/ساعة</b></div><div className="rounded-xl bg-slate-900 p-3">الضغط المطلوب: <b>{show(result.booster.required_pressure_bar)} bar</b></div><div className="rounded-xl bg-slate-900 p-3">قدرة البوستر: <b>{show(result.booster.input_power_kw)} kW</b></div></div>{Object.prototype.hasOwnProperty.call(result.reservoir_balance, 'forecast_end_volume_m3') && <section aria-label="توقع موازنة الخزان" className="mt-3 space-y-2 rounded-xl border border-slate-700 p-3 text-sm">
      <h3 className="font-semibold text-cyan-300">توقع موازنة الخزان</h3>
      <div className="grid gap-2 sm:grid-cols-3">
        {Object.prototype.hasOwnProperty.call(result.booster, 'requested_energy_kwh') && <p>طاقة البوستر المطلوبة تقديريًا: <b>{show(result.booster.requested_energy_kwh)} kWh</b> (للبوستر فقط؛ ليست طاقة مستهلكة فعليًا أو ضمانًا لإكمال الري)</p>}
        <p>حجم نهاية التشغيل: <b>{show(result.reservoir_balance.forecast_end_volume_m3)} م³</b></p>
        <p>فائض التدفق فوق السعة: <b>{show(result.reservoir_balance.forecast_excess_inflow_m3)} م³</b></p>
        <p>العجز عن الاحتياطي الأدنى: <b>{show(result.reservoir_balance.forecast_shortfall_to_minimum_m3)} م³</b></p>
      </div>
      {result.reservoir_balance.forecast_end_volume_m3 === null && <p role="status">لا يمكن إكمال التشغيل المطلوب مع الحفاظ على الاحتياطي الأدنى.</p>}
      <p className="text-xs text-slate-400">إسقاط بمعدلات ثابتة طوال زمن التشغيل المطلوب، وليس محاكاة زمنية أو قياسًا أو إذن تشغيل. الفائض يحتاج إدارة، ولا يثبت حدوث فيضان.</p>
    </section>}{(result.blocking_constraints.length>0||result.warnings.length>0)&&<ul className="mt-3 list-disc rounded-xl border border-amber-800/50 bg-amber-950/20 p-4 pr-8 text-xs text-amber-200">{[...result.blocking_constraints,...result.warnings].map(x=><li key={x}>{x}</li>)}</ul>}</div>}
  </section>;
}
