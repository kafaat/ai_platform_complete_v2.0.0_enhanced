import { useMemo, useState } from 'react';
import { Calculator, Droplets, Gauge, Zap } from 'lucide-react';
import { useTenantId } from '../hooks/useAuth';
import { calculateInteractiveIrrigation, type InteractiveCalculatorInput, type InteractiveCalculatorResult } from '../services/api/irrigationEngineeringCalculator';

function n(value: string): number | undefined {
  if (value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function fmt(value: unknown, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function NumberField({ label, value, onChange, unit, min = 0, step = 'any' }: { label: string; value: string; onChange: (v: string) => void; unit?: string; min?: number; step?: string }) {
  return <label className="space-y-1 text-xs text-slate-400"><span>{label}</span><div className="flex rounded-lg border border-slate-700 bg-slate-950"><input className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm text-slate-100 outline-none" type="number" min={min} step={step} value={value} onChange={e => onChange(e.target.value)} />{unit && <span className="border-r border-slate-700 px-2 py-2 text-slate-500">{unit}</span>}</div></label>;
}

export default function IrrigationEngineeringCalculator({ fieldId, seasonId }: { fieldId: string; seasonId?: string | null }) {
  const tenantId = useTenantId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InteractiveCalculatorResult | null>(null);
  const [form, setForm] = useState<Record<string, string>>({
    area: '50', efficiency: '0.82', flow: '230', pipeLength: '1000', diameter: '200', c: '140', elevation: '8', terminalPressure: '2.5', pumpEfficiency: '0.8', motorEfficiency: '0.9', motorPower: '45', mode: 'manual', depth: '18', crop: 'wheat', stage: 'flowering', kc: '1.15', soil: 'loam', taw: '120', raw: '60', depletion: '18', infiltration: '12', et0: '6.4', days: '1', rain: '0', elbows: '4', valves: '2', checks: '1', filters: '1', customLoss: '0', safety: '5', systemType: 'center_pivot',
  });
  // Editing any input invalidates the previous result (and its content_digest), so clear it
  // to avoid showing a stale computation that no longer matches the form.
  const set = (key: string, value: string) => {
    setForm(prev => ({ ...prev, [key]: value }));
    if (result) setResult(null);
    if (error) setError(null);
  };

  const input = useMemo<InteractiveCalculatorInput | null>(() => {
    if (!tenantId) return null;
    return {
      tenantId,
      fieldId,
      seasonId,
      systemId: `manual-calculator:${fieldId}`,
      systemType: form.systemType as InteractiveCalculatorInput['systemType'],
      irrigatedAreaHa: n(form.area) ?? 0,
      applicationEfficiency: n(form.efficiency) ?? 0,
      designFlowM3h: n(form.flow),
      pipeLengthM: n(form.pipeLength) ?? 0,
      pipeDiameterMm: n(form.diameter),
      hazenWilliamsC: n(form.c) ?? 140,
      elevationChangeM: n(form.elevation) ?? 0,
      terminalPressureBar: n(form.terminalPressure),
      pumpEfficiency: n(form.pumpEfficiency) ?? 0.8,
      motorEfficiency: n(form.motorEfficiency) ?? 0.9,
      installedMotorPowerKw: n(form.motorPower),
      waterDemandMode: form.mode as 'sahool' | 'manual',
      manualNetDepthMm: n(form.depth),
      cropType: form.crop || undefined,
      growthStage: form.stage || undefined,
      kc: n(form.kc),
      soilType: form.soil || undefined,
      tawMm: n(form.taw), rawMm: n(form.raw), depletionMm: n(form.depletion), infiltrationRateMmH: n(form.infiltration), et0MmDay: n(form.et0), forecastDays: n(form.days) ?? 1, effectiveRainMm: n(form.rain) ?? 0,
      elbows90: n(form.elbows) ?? 0, valves: n(form.valves) ?? 0, checkValves: n(form.checks) ?? 0, filters: n(form.filters) ?? 0, customMinorLossM: n(form.customLoss) ?? 0, safetyMarginM: n(form.safety) ?? 5,
    };
  }, [tenantId, fieldId, seasonId, form]);

  async function calculate() {
    if (!input) { setError('هوية المستأجر غير متاحة.'); return; }
    setBusy(true); setError(null);
    try { setResult(await calculateInteractiveIrrigation(input)); }
    catch (e) { setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'تعذر تنفيذ الحساب.'); }
    finally { setBusy(false); }
  }

  return <section className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5" aria-label="حاسبة هندسة الري التفاعلية">
    <div className="mb-4 flex items-center gap-2"><Calculator className="h-5 w-5 text-emerald-300" /><div><h2 className="font-bold text-slate-100">حاسبة الري والهيدروليك</h2><p className="text-xs text-slate-500">تقدير هندسي للتشغيل اليدوي؛ لا يمنح تفويض تشغيل آلي.</p></div></div>
    <div className="grid gap-5 xl:grid-cols-3">
      <div className="space-y-3"><h3 className="text-sm font-semibold text-emerald-300">المحصول والماء</h3>
        <label className="space-y-1 text-xs text-slate-400"><span>مصدر الاحتياج</span><select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" value={form.mode} onChange={e => set('mode', e.target.value)}><option value="manual">إدخال العمق يدوياً</option><option value="sahool">حساب من التربة والطقس</option></select></label>
        {form.mode === 'manual' && <NumberField label="الاحتياج الصافي" value={form.depth} onChange={v => set('depth', v)} unit="مم" />}
        <div className="grid grid-cols-2 gap-2"><NumberField label="المساحة" value={form.area} onChange={v => set('area', v)} unit="هكتار" /><NumberField label="كفاءة التطبيق" value={form.efficiency} onChange={v => set('efficiency', v)} step="0.01" /></div>
        <div className="grid grid-cols-2 gap-2"><NumberField label="ET0" value={form.et0} onChange={v => set('et0', v)} unit="مم/يوم" /><NumberField label="Kc" value={form.kc} onChange={v => set('kc', v)} step="0.01" /></div>
        <div className="grid grid-cols-2 gap-2"><NumberField label="عجز التربة" value={form.depletion} onChange={v => set('depletion', v)} unit="مم" /><NumberField label="المطر الفعال" value={form.rain} onChange={v => set('rain', v)} unit="مم" /></div>
        <div className="grid grid-cols-2 gap-2"><NumberField label="RAW" value={form.raw} onChange={v => set('raw', v)} unit="مم" /><NumberField label="TAW" value={form.taw} onChange={v => set('taw', v)} unit="مم" /></div>
      </div>
      <div className="space-y-3"><h3 className="text-sm font-semibold text-emerald-300">المواسير والهيدروليك</h3>
        <div className="grid grid-cols-2 gap-2"><NumberField label="التدفق" value={form.flow} onChange={v => set('flow', v)} unit="م³/ساعة" /><NumberField label="القطر الداخلي" value={form.diameter} onChange={v => set('diameter', v)} unit="مم" /></div>
        <div className="grid grid-cols-2 gap-2"><NumberField label="طول الخط" value={form.pipeLength} onChange={v => set('pipeLength', v)} unit="م" /><NumberField label="Hazen C" value={form.c} onChange={v => set('c', v)} /></div>
        <div className="grid grid-cols-2 gap-2"><NumberField label="فرق الارتفاع" value={form.elevation} onChange={v => set('elevation', v)} unit="م" /><NumberField label="ضغط الطرف" value={form.terminalPressure} onChange={v => set('terminalPressure', v)} unit="bar" /></div>
        <div className="grid grid-cols-4 gap-2"><NumberField label="أكواع" value={form.elbows} onChange={v => set('elbows', v)} /><NumberField label="صمامات" value={form.valves} onChange={v => set('valves', v)} /><NumberField label="عدم رجوع" value={form.checks} onChange={v => set('checks', v)} /><NumberField label="فلاتر" value={form.filters} onChange={v => set('filters', v)} /></div>
        <NumberField label="معدل تسرب التربة" value={form.infiltration} onChange={v => set('infiltration', v)} unit="مم/س" />
      </div>
      <div className="space-y-3"><h3 className="text-sm font-semibold text-emerald-300">المضخة والطاقة</h3>
        <div className="grid grid-cols-2 gap-2"><NumberField label="كفاءة المضخة" value={form.pumpEfficiency} onChange={v => set('pumpEfficiency', v)} step="0.01" /><NumberField label="كفاءة المحرك" value={form.motorEfficiency} onChange={v => set('motorEfficiency', v)} step="0.01" /></div>
        <NumberField label="قدرة المحرك المركبة" value={form.motorPower} onChange={v => set('motorPower', v)} unit="kW" />
        <NumberField label="هامش الأمان" value={form.safety} onChange={v => set('safety', v)} unit="م" />
        <button type="button" disabled={busy} onClick={calculate} className="w-full rounded-xl bg-emerald-500 px-4 py-3 text-sm font-bold text-slate-950 disabled:opacity-50">{busy ? 'جارٍ الحساب…' : 'احسب الكمية والضغط'}</button>
        {error && <p className="rounded-lg border border-rose-800 bg-rose-950/30 p-3 text-xs text-rose-300">{error}</p>}
      </div>
    </div>
    {result && <div className="mt-5 space-y-4 border-t border-slate-800 pt-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-800 p-3"><Droplets className="mb-2 h-4 w-4 text-cyan-300"/><p className="text-xs text-slate-500">الحجم الإجمالي</p><p className="text-xl font-bold text-slate-100">{fmt(result.calculations.gross_volume_m3)} م³</p></div>
        <div className="rounded-xl border border-slate-800 p-3"><Gauge className="mb-2 h-4 w-4 text-amber-300"/><p className="text-xs text-slate-500">الضغط المطلوب</p><p className="text-xl font-bold text-slate-100">{fmt(result.calculations.required_pressure_bar)} bar</p></div>
        <div className="rounded-xl border border-slate-800 p-3"><Zap className="mb-2 h-4 w-4 text-yellow-300"/><p className="text-xs text-slate-500">القدرة المطلوبة</p><p className="text-xl font-bold text-slate-100">{fmt(result.calculations.required_input_power_kw)} kW</p></div>
        <div className="rounded-xl border border-slate-800 p-3"><p className="text-xs text-slate-500">مدة التشغيل</p><p className="text-xl font-bold text-slate-100">{fmt(result.calculations.runtime_h)} ساعة</p></div>
      </div>
      <div className="grid gap-3 md:grid-cols-3 text-sm"><div className="rounded-xl bg-slate-900 p-3">سرعة الماء: <b>{fmt(result.calculations.mainline_velocity_m_s)} م/ث</b></div><div className="rounded-xl bg-slate-900 p-3">فاقد الاحتكاك: <b>{fmt(result.calculations.mainline_friction_loss_m)} م</b></div><div className="rounded-xl bg-slate-900 p-3">الحالة: <b>{result.status}</b></div></div>
      {(result.blocking_constraints.length > 0 || result.warnings.length > 0) && <div className="rounded-xl border border-amber-800/60 bg-amber-950/20 p-3 text-xs text-amber-200"><p className="font-bold">ملاحظات هندسية</p><ul className="mt-2 list-disc space-y-1 pr-5">{[...result.blocking_constraints, ...result.warnings].map(item => <li key={item}>{item}</li>)}</ul></div>}
      <p className="text-[11px] text-slate-600">النتيجة تقدير هندسي قابل للمراجعة، وليست شهادة Commissioning أو إذن تشغيل آلي. digest: {result.content_digest.slice(0, 12)}…</p>
    </div>}
  </section>;
}
