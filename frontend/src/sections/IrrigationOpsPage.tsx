// ═══════════════════════════════════════════════════════════════
// SAHOOL — IrrigationOpsPage (الريّ التشغيليّ: صمّامات + جداول مُخزَّنة)
// مستقلّة عن IrrigationWaterPage (تحليل كيمياء الماء). تربط حيّاً بـ:
//   GET/POST  /api/v1/irrigation/valves [+ /{id}/state]
//   GET/POST/DELETE /api/v1/irrigation/schedules
// صدق: لا بيانات مُلفَّقة — حالات StateViews للتحميل/الخطأ/الفراغ. RTL.
// التعديل (فتح/إغلاق/إنشاء/حذف) مُقيَّد بـcanMutate (irrigation:manage).
// ملاحظة: فتح/إغلاق الصمّام يسجّل النيّة فقط؛ التشغيل الفيزيائيّ عبر HIL.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Waypoints, CalendarClock, Plus, Trash2, Power, PowerOff,
  Gauge, Info, HardDrive,
} from 'lucide-react';
import {
  useValves, useCreateValve, useSetValveState,
  useSchedules, useCreateSchedule, useDeleteSchedule,
} from '../hooks/useApi';
import type {
  Valve, ValveType, ValveStatus, CreateScheduleInput,
} from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

// ── ترجمات/تسميات عربيّة ───────────────────────────────────────
const VALVE_TYPE_LABELS: Record<string, string> = {
  solenoid:    'كهرومغناطيسيّ',
  manual:      'يدويّ',
  drip_header: 'رأس تنقيط',
  gate:        'بوّابة',
};
const VALVE_TYPE_OPTIONS: ValveType[] = ['solenoid', 'manual', 'drip_header', 'gate'];

const STATUS_META: Record<ValveStatus, { label: string; color: string; bg: string }> = {
  open:    { label: 'مفتوح', color: '#4ade80', bg: '#04140a' },
  closed:  { label: 'مغلق',  color: '#94a3b8', bg: '#1e293b' },
  unknown: { label: 'غير معروف', color: '#f59e0b', bg: '#2a1a00' },
};

const DAYS_AR = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];

function errDetail(error: unknown): string {
  const status = (error as any)?.response?.status;
  if (status === 503) return 'خدمة الريّ غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض الريّ التشغيليّ (irrigation:view).';
  return 'تعذّر الاتصال بخدمة الريّ.';
}

// ════════════════════════════════════════════════════════════════
// لوحة الصمّامات
// ════════════════════════════════════════════════════════════════
function ValvesPanel({ mutable }: { mutable: boolean }) {
  const { data, isLoading, isError, error, refetch } = useValves();
  const setState = useSetValveState();
  const createValve = useCreateValve();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [fieldId, setFieldId] = useState('');
  const [deviceId, setDeviceId] = useState('');
  const [valveType, setValveType] = useState<ValveType>('solenoid');
  const [flow, setFlow] = useState('');

  const onCreate = () => {
    if (!name.trim()) return;
    createValve.mutate(
      {
        name: name.trim(),
        ...(fieldId.trim() ? { field_id: fieldId.trim() } : {}),
        ...(deviceId.trim() ? { device_id: deviceId.trim() } : {}),
        valve_type: valveType,
        ...(flow.trim() && !isNaN(Number(flow)) ? { flow_rate_lpm: Number(flow) } : {}),
      },
      {
        onSuccess: () => {
          setName(''); setFieldId(''); setDeviceId(''); setFlow(''); setValveType('solenoid');
          setShowForm(false);
        },
      },
    );
  };

  const toggle = (v: Valve) => {
    const next = v.status === 'open' ? 'closed' : 'open';
    setState.mutate({ valveId: v.valve_id, status: next });
  };

  return (
    <section className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Waypoints className="w-4 h-4 text-sky-400" />
          <span className="text-sm font-semibold text-slate-200">الصمّامات</span>
        </div>
        {mutable && !isLoading && !isError && (
          <button onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
            style={{ background: '#0ea5e9' }}>
            <Plus className="w-3.5 h-3.5" /> صمّام جديد
          </button>
        )}
      </div>

      {/* ملاحظة HIL */}
      <div className="flex items-start gap-2 mb-3 rounded-lg p-2.5 border text-[11px] text-amber-300"
        style={{ background: '#2a1a00', borderColor: '#f59e0b33' }}>
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        <span>
          فتح/إغلاق الصمّام هنا يسجّل النيّة فقط. التشغيل الفيزيائيّ الفعليّ يمرّ عبر
          موافقة بشريّة (HIL) قبل أن يُنفَّذ على الجهاز.
        </span>
      </div>

      {/* نموذج إنشاء */}
      {mutable && showForm && (
        <div className="rounded-xl border p-3 mb-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">الاسم *</span>
              <input value={name} onChange={e => setName(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">النوع</span>
              <select value={valveType} onChange={e => setValveType(e.target.value as ValveType)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
                {VALVE_TYPE_OPTIONS.map(t => <option key={t} value={t}>{VALVE_TYPE_LABELS[t]}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف الحقل (اختياريّ)</span>
              <input value={fieldId} onChange={e => setFieldId(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف الجهاز (اختياريّ)</span>
              <input value={deviceId} onChange={e => setDeviceId(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معدّل التدفّق (لتر/دقيقة، اختياريّ)</span>
              <input type="number" inputMode="decimal" step="any" value={flow} onChange={e => setFlow(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowForm(false)}
              className="px-3 py-1.5 rounded-lg text-xs text-slate-300 border" style={{ borderColor: '#334155' }}>
              إلغاء
            </button>
            <button onClick={onCreate} disabled={createValve.isPending || !name.trim()}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white disabled:opacity-60"
              style={{ background: '#0ea5e9' }}>
              {createValve.isPending ? 'جارٍ الحفظ…' : 'حفظ الصمّام'}
            </button>
          </div>
          {createValve.isError && (
            <p className="text-[11px] text-red-400 mt-2">تعذّر إنشاء الصمّام. حاول مجدّداً.</p>
          )}
        </div>
      )}

      {isLoading && <LoadingState message="جارٍ تحميل الصمّامات…" />}
      {isError && (
        <ErrorState title="تعذّر تحميل الصمّامات" detail={errDetail(error)} onRetry={() => refetch()} />
      )}
      {!isLoading && !isError && (data?.length ?? 0) === 0 && (
        <EmptyState
          icon={<Waypoints className="w-8 h-8" />}
          title="لا توجد صمّامات بعد"
          hint={mutable ? 'أضِف صمّاماً للبدء.' : 'لم تُسجَّل أيّ صمّامات حتى الآن.'}
        />
      )}

      {!isLoading && !isError && (data?.length ?? 0) > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {data!.map(v => {
            const st = STATUS_META[v.status] ?? STATUS_META.unknown;
            return (
              <div key={v.valve_id} className="rounded-xl border p-3"
                style={{ background: '#1e293b', borderColor: '#334155' }}>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-100 truncate">{v.name}</div>
                    <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                      {VALVE_TYPE_LABELS[v.valve_type ?? ''] ?? (v.valve_type || 'غير محدّد')}
                      {v.field_id && <span className="text-slate-600">· حقل {v.field_id}</span>}
                    </div>
                  </div>
                  <span className="text-[11px] px-2 py-0.5 rounded-full font-medium flex-shrink-0"
                    style={{ background: st.bg, color: st.color, border: `1px solid ${st.color}44` }}>
                    {st.label}
                  </span>
                </div>

                <div className="flex items-center gap-3 mt-2 text-[11px] text-slate-500">
                  {v.flow_rate_lpm != null && (
                    <span className="flex items-center gap-1"><Gauge className="w-3 h-3" /> {v.flow_rate_lpm} ل/د</span>
                  )}
                  {v.device_id && (
                    <span className="flex items-center gap-1"><HardDrive className="w-3 h-3" /> {v.device_id}</span>
                  )}
                </div>

                {mutable && (
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => toggle(v)}
                      disabled={setState.isPending}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-60"
                      style={v.status === 'open'
                        ? { background: '#1e293b', color: '#94a3b8', border: '1px solid #475569' }
                        : { background: '#04140a', color: '#4ade80', border: '1px solid #16a34a55' }}>
                      {v.status === 'open'
                        ? <><PowerOff className="w-3.5 h-3.5" /> طلب إغلاق</>
                        : <><Power className="w-3.5 h-3.5" /> طلب فتح</>}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ════════════════════════════════════════════════════════════════
// لوحة الجداول
// ════════════════════════════════════════════════════════════════
function SchedulesPanel({ mutable }: { mutable: boolean }) {
  const { data, isLoading, isError, error, refetch } = useSchedules();
  const createSchedule = useCreateSchedule();
  const deleteSchedule = useDeleteSchedule();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [fieldId, setFieldId] = useState('');
  const [valveId, setValveId] = useState('');
  const [startTime, setStartTime] = useState('06:00');
  const [duration, setDuration] = useState('30');
  const [waterTarget, setWaterTarget] = useState('');
  const [days, setDays] = useState<number[]>([]);

  const toggleDay = (d: number) =>
    setDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d].sort((a, b) => a - b));

  const onCreate = () => {
    if (!name.trim() || !startTime || isNaN(Number(duration))) return;
    const payload: CreateScheduleInput = {
      name: name.trim(),
      start_time: startTime,
      duration_min: Number(duration),
      ...(fieldId.trim() ? { field_id: fieldId.trim() } : {}),
      ...(valveId.trim() ? { valve_id: valveId.trim() } : {}),
      ...(days.length ? { days_of_week: days } : {}),
      ...(waterTarget.trim() && !isNaN(Number(waterTarget)) ? { water_target_mm: Number(waterTarget) } : {}),
      enabled: true,
    };
    createSchedule.mutate(payload, {
      onSuccess: () => {
        setName(''); setFieldId(''); setValveId(''); setStartTime('06:00');
        setDuration('30'); setWaterTarget(''); setDays([]); setShowForm(false);
      },
    });
  };

  return (
    <section className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <CalendarClock className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">جداول الريّ</span>
        </div>
        {mutable && !isLoading && !isError && (
          <button onClick={() => setShowForm(s => !s)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white"
            style={{ background: '#16a34a' }}>
            <Plus className="w-3.5 h-3.5" /> جدول جديد
          </button>
        )}
      </div>

      {/* نموذج إنشاء */}
      {mutable && showForm && (
        <div className="rounded-xl border p-3 mb-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">الاسم *</span>
              <input value={name} onChange={e => setName(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">وقت البدء *</span>
              <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">المدّة (دقيقة) *</span>
              <input type="number" inputMode="numeric" min="1" value={duration} onChange={e => setDuration(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">هدف الماء (مم، اختياريّ)</span>
              <input type="number" inputMode="decimal" step="any" value={waterTarget} onChange={e => setWaterTarget(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف الحقل (اختياريّ)</span>
              <input value={fieldId} onChange={e => setFieldId(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">معرّف الصمّام (اختياريّ)</span>
              <input value={valveId} onChange={e => setValveId(e.target.value)}
                className="px-3 py-2 rounded-lg text-sm"
                style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
            </label>
          </div>

          {/* أيام الأسبوع */}
          <div className="mt-3">
            <span className="text-xs text-slate-400">أيّام التشغيل (اختياريّ)</span>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {DAYS_AR.map((d, i) => {
                const on = days.includes(i);
                return (
                  <button key={i} type="button" onClick={() => toggleDay(i)}
                    className="px-2.5 py-1 rounded-lg text-[11px] border"
                    style={on
                      ? { background: '#04140a', color: '#4ade80', borderColor: '#16a34a55' }
                      : { background: '#0f1117', color: '#94a3b8', borderColor: '#334155' }}>
                    {d}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-3">
            <button onClick={() => setShowForm(false)}
              className="px-3 py-1.5 rounded-lg text-xs text-slate-300 border" style={{ borderColor: '#334155' }}>
              إلغاء
            </button>
            <button onClick={onCreate}
              disabled={createSchedule.isPending || !name.trim() || !startTime || isNaN(Number(duration))}
              className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white disabled:opacity-60"
              style={{ background: '#16a34a' }}>
              {createSchedule.isPending ? 'جارٍ الحفظ…' : 'حفظ الجدول'}
            </button>
          </div>
          {createSchedule.isError && (
            <p className="text-[11px] text-red-400 mt-2">تعذّر إنشاء الجدول. حاول مجدّداً.</p>
          )}
        </div>
      )}

      {isLoading && <LoadingState message="جارٍ تحميل الجداول…" />}
      {isError && (
        <ErrorState title="تعذّر تحميل الجداول" detail={errDetail(error)} onRetry={() => refetch()} />
      )}
      {!isLoading && !isError && (data?.length ?? 0) === 0 && (
        <EmptyState
          icon={<CalendarClock className="w-8 h-8" />}
          title="لا توجد جداول ريّ بعد"
          hint={mutable ? 'أنشِئ جدولاً للبدء.' : 'لم تُسجَّل أيّ جداول حتى الآن.'}
        />
      )}

      {!isLoading && !isError && (data?.length ?? 0) > 0 && (
        <ul className="space-y-2">
          {data!.map(s => (
            <li key={s.schedule_id}
              className="rounded-xl border p-3 flex items-center justify-between gap-3"
              style={{ background: '#1e293b', borderColor: '#334155' }}>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-100 truncate">{s.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                    style={s.enabled
                      ? { background: '#04140a', color: '#4ade80', border: '1px solid #16a34a55' }
                      : { background: '#1e293b', color: '#94a3b8', border: '1px solid #475569' }}>
                    {s.enabled ? 'مُفعّل' : 'مُعطّل'}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                  <span>البدء: {s.start_time}</span>
                  <span>المدّة: {s.duration_min} دقيقة</span>
                  {s.water_target_mm != null && <span>هدف: {s.water_target_mm} مم</span>}
                  {s.valve_id && <span>صمّام: {s.valve_id}</span>}
                  {s.field_id && <span>حقل: {s.field_id}</span>}
                </div>
                {s.days_of_week && s.days_of_week.length > 0 && (
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    الأيّام: {s.days_of_week.map(d => DAYS_AR[d] ?? d).join('، ')}
                  </div>
                )}
                {s.last_run_at && (
                  <div className="text-[10px] text-slate-600 mt-0.5">آخر تشغيل: {s.last_run_at}</div>
                )}
              </div>
              {mutable && (
                <button onClick={() => deleteSchedule.mutate(s.schedule_id)}
                  disabled={deleteSchedule.isPending}
                  title="حذف الجدول"
                  className="p-2 rounded-lg flex-shrink-0 text-slate-500 hover:text-red-400 disabled:opacity-60"
                  style={{ border: '1px solid #334155' }}>
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ════════════════════════════════════════════════════════════════
export default function IrrigationOpsPage() {
  const role = useAuthStore(s => s.user?.role);
  const mutable = canMutate(role);

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Waypoints className="w-5 h-5 text-sky-400" />
        <div>
          <h2 className="text-xl font-bold text-slate-100">الريّ التشغيليّ</h2>
          <p className="text-sm text-slate-400">
            إدارة صمّامات الريّ وجداوله المُخزَّنة. {mutable ? '' : 'وضع العرض فقط — لا تملك صلاحية التعديل.'}
          </p>
        </div>
      </div>

      <ValvesPanel mutable={mutable} />
      <SchedulesPanel mutable={mutable} />
    </div>
  );
}
