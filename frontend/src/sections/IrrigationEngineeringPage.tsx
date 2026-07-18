// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationEngineeringPage (هندسة نظام الريّ، محايدة عن المُصنِّع)
// أوّل مستهلك واجهة لـ IrrigationEngineeringWorkspace (كان يتيماً). يربط حيّاً بـ:
//   POST /api/v1/irrigation/engineering/calculate  → EngineeringResult
//        (== IrrigationEngineeringSummary: status + capability_graph + manual_operation)
// صدق: لا بيانات مُلفَّقة — المدخلات مُعلَنة من المستخدم (user_declared)، والحساب
// خادميّ حقيقيّ. حالات تحميل/خطأ صريحة. توصية-فقط: لا أمر تنفيذ من هذه الشاشة
// (التنفيذ اليدويّ المحكوم يمرّ عبر «الريّ التشغيليّ» + مركز القرار). RTL.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { IrrigationEngineeringWorkspace } from './IrrigationEngineeringWorkspace';
import type { IrrigationEngineeringSummary, IrrigationSystemType } from '../lib/irrigationEngineering';
import {
  calculateIrrigationEngineering,
  type EngineeringCalcInput,
} from '../services/api/irrigationEngineeringCalculator';
import { asApiError } from '../services/api';
import { useAuthStore } from '../hooks/useAuth';

const SYSTEM_TYPES: IrrigationSystemType[] = [
  'center_pivot', 'linear_move', 'reel', 'sprinkler', 'drip', 'pump_only', 'valve_network',
];

type FormState = {
  fieldId: string;
  systemId: string;
  name: string;
  systemType: IrrigationSystemType;
  irrigatedAreaHa: string;
  netDepthMm: string;
  effectiveRainMm: string;
  lengthM: string; // center_pivot only
};

const INITIAL: FormState = {
  fieldId: '', systemId: '', name: '',
  systemType: 'drip',
  irrigatedAreaHa: '', netDepthMm: '', effectiveRainMm: '0', lengthM: '',
};

export default function IrrigationEngineeringPage() {
  const { user } = useAuthStore();
  const [form, setForm] = useState<FormState>(INITIAL);
  const [summary, setSummary] = useState<IrrigationEngineeringSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const area = Number(form.irrigatedAreaHa);
  const depth = Number(form.netDepthMm);
  const pivotNeedsLength = form.systemType === 'center_pivot' && !form.lengthM;
  const valid =
    !!user?.tenant_id &&
    form.fieldId.trim() && form.systemId.trim() && form.name.trim() &&
    area > 0 && depth > 0 && !pivotNeedsLength;

  async function runCalculate() {
    if (!valid || !user?.tenant_id) return;
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const input: EngineeringCalcInput = {
        tenantId: String(user.tenant_id),
        fieldId: form.fieldId.trim(),
        systemId: form.systemId.trim(),
        name: form.name.trim(),
        systemType: form.systemType,
        irrigatedAreaHa: area,
        netDepthMm: depth,
        effectiveRainMm: Number(form.effectiveRainMm) || 0,
        lengthM: form.lengthM ? Number(form.lengthM) : null,
      };
      setSummary(await calculateIrrigationEngineering(input));
    } catch (e) {
      setError(asApiError(e).message ?? 'تعذّر حساب هندسة الريّ');
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 p-4" dir="rtl">
      <header>
        <h1 className="text-2xl font-bold">هندسة نظام الريّ</h1>
        <p className="text-sm text-muted-foreground">
          حاسبة هيدروليّة/طاقة محايدة عن المُصنِّع. المدخلات مُعلَنة والحساب خادميّ — توصية فقط.
        </p>
      </header>

      <section className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2 lg:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">معرّف الحقل
          <input className="rounded border px-2 py-1" value={form.fieldId}
            onChange={(e) => set('fieldId', e.target.value)} placeholder="field_id" />
        </label>
        <label className="flex flex-col gap-1 text-sm">معرّف النظام
          <input className="rounded border px-2 py-1" value={form.systemId}
            onChange={(e) => set('systemId', e.target.value)} placeholder="system_id" />
        </label>
        <label className="flex flex-col gap-1 text-sm">اسم النظام
          <input className="rounded border px-2 py-1" value={form.name}
            onChange={(e) => set('name', e.target.value)} placeholder="مثال: محوري ١" />
        </label>
        <label className="flex flex-col gap-1 text-sm">نوع النظام
          <select className="rounded border px-2 py-1" value={form.systemType}
            onChange={(e) => set('systemType', e.target.value as IrrigationSystemType)}>
            {SYSTEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">المساحة المرويّة (هكتار)
          <input className="rounded border px-2 py-1" inputMode="decimal" value={form.irrigatedAreaHa}
            onChange={(e) => set('irrigatedAreaHa', e.target.value)} placeholder="> 0" />
        </label>
        <label className="flex flex-col gap-1 text-sm">العمق الصافي (مم)
          <input className="rounded border px-2 py-1" inputMode="decimal" value={form.netDepthMm}
            onChange={(e) => set('netDepthMm', e.target.value)} placeholder="> 0" />
        </label>
        <label className="flex flex-col gap-1 text-sm">المطر الفعّال (مم)
          <input className="rounded border px-2 py-1" inputMode="decimal" value={form.effectiveRainMm}
            onChange={(e) => set('effectiveRainMm', e.target.value)} placeholder="0" />
        </label>
        {form.systemType === 'center_pivot' && (
          <label className="flex flex-col gap-1 text-sm">طول الذراع (م) — مطلوب للمحوري
            <input className="rounded border px-2 py-1" inputMode="decimal" value={form.lengthM}
              onChange={(e) => set('lengthM', e.target.value)} placeholder="> 0" />
          </label>
        )}
      </section>

      {error && <div role="alert" className="rounded border border-red-500 bg-red-950/20 px-3 py-2 text-sm">{error}</div>}
      {notice && <div role="status" className="rounded border px-3 py-2 text-sm">{notice}</div>}

      <IrrigationEngineeringWorkspace
        summary={summary}
        onCalculate={loading ? undefined : runCalculate}
        onConfirmManualExecution={() =>
          setNotice('التنفيذ اليدويّ المحكوم يتمّ عبر «الريّ التشغيليّ» ومركز القرار (بمعرّف تنفيذ)، لا من الحاسبة.')
        }
      />
      {loading && <div role="status" className="text-sm text-muted-foreground">جارٍ الحساب…</div>}
    </div>
  );
}
