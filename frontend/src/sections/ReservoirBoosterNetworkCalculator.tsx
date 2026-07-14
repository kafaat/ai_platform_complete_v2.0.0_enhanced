import { useState } from 'react';
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
  return <label className="space-y-1 text-xs text-slate-400"><span>{label}</span><div className="flex rounded-lg border border-slate-700 bg-slate-950"><input type="number" min="0" step="any" value={value} onChange={e=>onChange(e.target.value)} className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-slate-100 outline-none"/>{unit && <span className="border-r border-slate-700 px-2 py-2 text-slate-500">{unit}</span>}</div></label>;
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
  const [systemType,setSystemType]=useState<NetworkIrrigationSystemType>('none');
  const [busy,setBusy]=useState(false); const [error,setError]=useState<string|null>(null); const [result,setResult]=useState<IrrigationNetworkResult|null>(null);
  const [f,setF]=useState({volume:'11000',well1:'80',well2:'80',well3:'80',reservoirCapacity:'4000',reservoirCurrent:'3500',reservoirMinimum:'500',boosterFlow:'230',boosterHead:'70',boosterMotor:'60',pipeLength:'1000',diameter:'250',c:'140',elevation:'8',minorLoss:'5',safety:'5',systemName:'نظام الري 1',systemFlow:'230',systemPressure:'3.2',radius:'399',arc:'360',machineLength:'400',travelLength:'1000',hoseLength:'400',hoseDiameter:'110',zoneCount:'8',concurrentZones:'2',emitterCount:'12000',emitterFlow:'4',sprinklerCount:'40',sprinklerFlow:'5.75',wettedArea:'50'});
  // Any edit invalidates the previous result (+ its digest); clear it so nothing stale shows.
  const invalidate=()=>{if(result)setResult(null);if(error)setError(null);};
  const set=(k:string,v:string)=>{setF(p=>({...p,[k]:v}));invalidate();};
  const changeSystem=(v:NetworkIrrigationSystemType)=>{setSystemType(v);invalidate();};
  const hasSystem=systemType!=='none';

  async function run(){
    if(!tenantId){setError('هوية المستأجر غير متاحة.');return;}
    setBusy(true);setError(null);
    try{setResult(await calculateReservoirBoosterNetwork({
      tenantId,fieldId,seasonId,requiredGrossVolumeM3:num(f.volume),wellFlowsM3h:[num(f.well1),num(f.well2),num(f.well3)],
      reservoirCapacityM3:num(f.reservoirCapacity),reservoirCurrentM3:num(f.reservoirCurrent),reservoirMinimumM3:num(f.reservoirMinimum),
      boosterFlowM3h:num(f.boosterFlow),boosterHeadM:num(f.boosterHead),boosterMotorKw:num(f.boosterMotor),boosterPumpEfficiency:.78,boosterMotorEfficiency:.92,
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
    <div className="mb-4 flex items-center gap-2"><Network className="h-5 w-5 text-cyan-300"/><div><h2 className="font-bold text-slate-100">البركة والبوستر وشبكة الري متعددة الأنظمة</h2><p className="text-xs text-slate-500">إضافة جهاز الري اختيارية. اختر محوراً أو تنقيطاً أو رشاشات أو حركة خطية أو بكرة أو شبكة صمامات.</p></div></div>
    <div className="grid gap-4 lg:grid-cols-4">
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">الماء والآبار</h3><F label="الحجم المطلوب" value={f.volume} onChange={v=>set('volume',v)} unit="م³"/><div className="grid grid-cols-3 gap-2"><F label="بئر 1" value={f.well1} onChange={v=>set('well1',v)} unit="م³/ساعة"/><F label="بئر 2" value={f.well2} onChange={v=>set('well2',v)} unit="م³/ساعة"/><F label="بئر 3" value={f.well3} onChange={v=>set('well3',v)} unit="م³/ساعة"/></div></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">بركة التجميع</h3><F label="السعة" value={f.reservoirCapacity} onChange={v=>set('reservoirCapacity',v)} unit="م³"/><F label="الحجم الحالي" value={f.reservoirCurrent} onChange={v=>set('reservoirCurrent',v)} unit="م³"/><F label="الحد الأدنى" value={f.reservoirMinimum} onChange={v=>set('reservoirMinimum',v)} unit="م³"/></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">البوستر والخط</h3><F label="تدفق البوستر" value={f.boosterFlow} onChange={v=>set('boosterFlow',v)} unit="م³/ساعة"/><F label="Head التصميمي" value={f.boosterHead} onChange={v=>set('boosterHead',v)} unit="م"/><F label="قدرة المحرك" value={f.boosterMotor} onChange={v=>set('boosterMotor',v)} unit="kW"/><div className="grid grid-cols-2 gap-2"><F label="طول الخط" value={f.pipeLength} onChange={v=>set('pipeLength',v)} unit="م"/><F label="قطر الخط" value={f.diameter} onChange={v=>set('diameter',v)} unit="مم"/></div></div>
      <div className="space-y-2"><h3 className="text-sm font-semibold text-cyan-300">نوع نظام الري</h3><select value={systemType} onChange={e=>changeSystem(e.target.value as NetworkIrrigationSystemType)} className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-3 text-sm text-slate-100">{Object.entries(systemLabels).map(([v,l])=><option key={v} value={v}>{l}</option>)}</select>{hasSystem&&<div className="space-y-2 rounded-xl border border-emerald-900/60 bg-emerald-950/10 p-3"><label className="text-xs text-slate-400">اسم النظام<input value={f.systemName} onChange={e=>set('systemName',e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"/></label><div className="grid grid-cols-2 gap-2"><F label="التدفق التصميمي" value={f.systemFlow} onChange={v=>set('systemFlow',v)} unit="م³/ساعة"/><F label="ضغط الدخول" value={f.systemPressure} onChange={v=>set('systemPressure',v)} unit="bar"/><F label="المساحة المروية" value={f.wettedArea} onChange={v=>set('wettedArea',v)} unit="هكتار"/>
      {systemType==='center_pivot'&&<><F label="نصف القطر" value={f.radius} onChange={v=>set('radius',v)} unit="م"/><F label="قوس التشغيل" value={f.arc} onChange={v=>set('arc',v)} unit="°"/></>}
      {systemType==='linear_move'&&<><F label="طول الجهاز" value={f.machineLength} onChange={v=>set('machineLength',v)} unit="م"/><F label="طول المسار" value={f.travelLength} onChange={v=>set('travelLength',v)} unit="م"/></>}
      {systemType==='reel'&&<><F label="طول الخرطوم" value={f.hoseLength} onChange={v=>set('hoseLength',v)} unit="م"/><F label="قطر الخرطوم" value={f.hoseDiameter} onChange={v=>set('hoseDiameter',v)} unit="مم"/></>}
      {['drip','valve_network'].includes(systemType)&&<><F label="عدد المناطق" value={f.zoneCount} onChange={v=>set('zoneCount',v)}/><F label="مناطق متزامنة" value={f.concurrentZones} onChange={v=>set('concurrentZones',v)}/></>}
      {systemType==='drip'&&<><F label="عدد النقاطات" value={f.emitterCount} onChange={v=>set('emitterCount',v)}/><F label="تصريف النقاط" value={f.emitterFlow} onChange={v=>set('emitterFlow',v)} unit="لتر/ساعة"/></>}
      {systemType==='sprinkler'&&<><F label="عدد الرشاشات" value={f.sprinklerCount} onChange={v=>set('sprinklerCount',v)}/><F label="تصريف الرشاش" value={f.sprinklerFlow} onChange={v=>set('sprinklerFlow',v)} unit="م³/ساعة"/></>}
      </div></div>}<button disabled={busy} onClick={run} className="w-full rounded-xl bg-cyan-400 px-4 py-3 text-sm font-bold text-slate-950 disabled:opacity-50">{busy?'جارٍ الحساب…':'احسب الشبكة'}</button>{error&&<p className="rounded-lg border border-rose-800 bg-rose-950/30 p-2 text-xs text-rose-300">{error}</p>}</div>
    </div>
    {result&&<div className="mt-5 border-t border-slate-800 pt-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5 text-sm"><div className="rounded-xl bg-slate-900 p-3">الحالة: <b>{result.status}</b></div><div className="rounded-xl bg-slate-900 p-3">النظام: <b>{result.machine_mode==='none'?'غير مضاف':String(result.selected_machines[0]?.system_type ?? 'مضاف')}</b></div><div className="rounded-xl bg-slate-900 p-3">صافي البركة: <b>{show(result.reservoir_balance.net_change_m3_h)} م³/ساعة</b></div><div className="rounded-xl bg-slate-900 p-3">الضغط المطلوب: <b>{show(result.booster.required_pressure_bar)} bar</b></div><div className="rounded-xl bg-slate-900 p-3">قدرة البوستر: <b>{show(result.booster.input_power_kw)} kW</b></div></div>{(result.blocking_constraints.length>0||result.warnings.length>0)&&<ul className="mt-3 list-disc rounded-xl border border-amber-800/50 bg-amber-950/20 p-4 pr-8 text-xs text-amber-200">{[...result.blocking_constraints,...result.warnings].map(x=><li key={x}>{x}</li>)}</ul>}</div>}
  </section>;
}
