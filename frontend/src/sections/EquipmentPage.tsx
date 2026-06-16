// ═══════════════════════════════════════════════════════════════
// SAHOOL — EquipmentPage (المعدّات)
// إدارة المعدّات + سجلّ الصيانة، بيانات حيّة عبر البوابة:
//   GET  /api/v1/equipment
//   POST /api/v1/equipment
//   GET  /api/v1/equipment/{id}/maintenance
//   POST /api/v1/equipment/{id}/maintenance   (kind=breakdown ⇒ broken خادميّاً)
// مُقيَّد بالدور (equipment:view / equipment:manage) والمستأجِر. لا بيانات
// مُلفَّقة — عند الخطأ/الفراغ تُعرض حالة صادقة (StateViews). 503 = DB مُعطَّلة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Tractor, Wrench, Plus, Clock, AlertTriangle, History } from 'lucide-react';
import {
  useEquipment, useMaintenance, useCreateEquipment, useLogMaintenance,
} from '../hooks/useApi';
import type {
  Equipment, EquipmentType, MaintenanceKind,
} from '../services/api';
import { asApiError } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';

// ── أسماء عربيّة للأنواع/حالات/أنواع الصيانة ─────────────────────
const TYPE_LABELS: Record<string, string> = {
  tractor:   'جرّار',
  pump:      'مضخّة',
  harvester: 'حصّادة',
  sprayer:   'رشّاشة',
  other:     'أخرى',
};
const TYPE_OPTIONS: EquipmentType[] = ['tractor', 'pump', 'harvester', 'sprayer', 'other'];

const KIND_LABELS: Record<string, string> = {
  scheduled:  'صيانة مجدولة',
  repair:     'إصلاح',
  breakdown:  'عطل',
  inspection: 'فحص',
};
const KIND_OPTIONS: MaintenanceKind[] = ['scheduled', 'repair', 'breakdown', 'inspection'];

// حالة المعدّة → تسمية ولون (من الخادم؛ fallback للقيمة الخام).
const STATUS_STYLE: Record<string, { label: string; bg: string; fg: string }> = {
  active:      { label: 'نشطة',     bg: '#16a34a22', fg: '#4ade80' },
  broken:      { label: 'معطّلة',   bg: '#dc262622', fg: '#f87171' },
  maintenance: { label: 'في الصيانة', bg: '#f59e0b22', fg: '#fbbf24' },
  retired:     { label: 'مُتقاعدة',  bg: '#64748b22', fg: '#94a3b8' },
};

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n ?? 0);

const fmtDate = (d: string | null) => (d ? new Date(d).toLocaleDateString('en-CA') : '—');

// رسالة خطأ صادقة مُشتقّة من رمز الحالة (يُستخدم في كلّ الاستعلامات/الطفرات).
function errorDetail(err: unknown): string {
  const status = asApiError(err).response?.status;
  if (status === 503) return 'خدمة المعدّات غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية هذه العملية (equipment:view / equipment:manage).';
  if (status === 401) return 'انتهت الجلسة. يُرجى تسجيل الدخول من جديد.';
  return 'تعذّر الاتصال بخدمة المعدّات.';
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { label: status, bg: '#33415544', fg: '#cbd5e1' };
  return (
    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium" style={{ background: s.bg, color: s.fg }}>
      {s.label}
    </span>
  );
}

// ── نموذج تسجيل معدّة جديدة ──────────────────────────────────────
function RegisterForm() {
  const create = useCreateEquipment();
  const [name, setName] = useState('');
  const [type, setType] = useState<EquipmentType>('tractor');
  const [hours, setHours] = useState('');
  const [purchase, setPurchase] = useState('');
  const [notes, setNotes] = useState('');

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || create.isPending) return;
    create.mutate(
      {
        name: name.trim(),
        type,
        ...(hours.trim() !== '' ? { operating_hours: Number(hours) } : {}),
        ...(purchase ? { purchase_date: purchase } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      },
      {
        onSuccess: () => { setName(''); setHours(''); setPurchase(''); setNotes(''); setType('tractor'); },
      },
    );
  };

  const input = 'px-3 py-2 rounded-lg text-sm w-full';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  return (
    <form onSubmit={onSubmit} className="rounded-xl p-4 border space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">تسجيل معدّة</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">الاسم *</label>
          <input className={input} style={inputStyle} value={name} onChange={e => setName(e.target.value)} placeholder="مثال: جرّار جون دير 5075" />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">النوع *</label>
          <select className={input} style={inputStyle} value={type} onChange={e => setType(e.target.value as EquipmentType)}>
            {TYPE_OPTIONS.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">ساعات التشغيل</label>
          <input className={input} style={inputStyle} type="number" min={0} step="any" value={hours} onChange={e => setHours(e.target.value)} placeholder="0" />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">تاريخ الشراء</label>
          <input className={input} style={inputStyle} type="date" value={purchase} onChange={e => setPurchase(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-[11px] text-slate-400 mb-1">ملاحظات</label>
          <input className={input} style={inputStyle} value={notes} onChange={e => setNotes(e.target.value)} placeholder="اختياري" />
        </div>
      </div>
      {create.isError && (
        <p className="text-xs text-red-400 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {errorDetail(create.error)}
        </p>
      )}
      <button
        type="submit"
        disabled={!name.trim() || create.isPending}
        className="px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
        style={{ background: '#16a34a', color: '#fff' }}
      >
        {create.isPending ? 'جارٍ الحفظ…' : 'تسجيل المعدّة'}
      </button>
    </form>
  );
}

// ── نموذج تسجيل صيانة لمعدّة محدّدة ──────────────────────────────
function LogMaintenanceForm({ equipment }: { equipment: Equipment }) {
  const log = useLogMaintenance(equipment.equipment_id);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<MaintenanceKind>('scheduled');
  const [scheduled, setScheduled] = useState('');
  const [performed, setPerformed] = useState('');
  const [cost, setCost] = useState('');
  const [notes, setNotes] = useState('');

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (log.isPending) return;
    log.mutate(
      {
        kind,
        ...(scheduled ? { scheduled_date: scheduled } : {}),
        ...(performed ? { performed_date: performed } : {}),
        ...(cost.trim() !== '' ? { cost_usd: Number(cost) } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      },
      {
        onSuccess: () => { setScheduled(''); setPerformed(''); setCost(''); setNotes(''); setKind('scheduled'); setOpen(false); },
      },
    );
  };

  const input = 'px-3 py-2 rounded-lg text-sm w-full';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
        style={{ background: '#f59e0b22', color: '#fbbf24', border: '1px solid #f59e0b44' }}
      >
        <Wrench className="w-3.5 h-3.5" /> تسجيل صيانة
      </button>
    );
  }

  return (
    <form onSubmit={onSubmit} className="rounded-xl p-3 border space-y-3 mt-2" style={{ background: '#0f1117', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2">
        <Wrench className="w-4 h-4 text-amber-400" />
        <span className="text-sm font-semibold text-slate-200">صيانة: {equipment.name}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">النوع *</label>
          <select className={input} style={inputStyle} value={kind} onChange={e => setKind(e.target.value as MaintenanceKind)}>
            {KIND_OPTIONS.map(k => <option key={k} value={k}>{KIND_LABELS[k]}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">التكلفة (USD)</label>
          <input className={input} style={inputStyle} type="number" min={0} step="any" value={cost} onChange={e => setCost(e.target.value)} placeholder="0" />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">تاريخ الجدولة</label>
          <input className={input} style={inputStyle} type="date" value={scheduled} onChange={e => setScheduled(e.target.value)} />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">تاريخ التنفيذ</label>
          <input className={input} style={inputStyle} type="date" value={performed} onChange={e => setPerformed(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-[11px] text-slate-400 mb-1">ملاحظات</label>
          <input className={input} style={inputStyle} value={notes} onChange={e => setNotes(e.target.value)} placeholder="اختياري" />
        </div>
      </div>
      {kind === 'breakdown' && (
        <p className="text-[11px] text-amber-400 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> تسجيل عطل سيقلب حالة المعدّة إلى «معطّلة».
        </p>
      )}
      {log.isError && (
        <p className="text-xs text-red-400 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {errorDetail(log.error)}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={log.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
          style={{ background: '#f59e0b', color: '#1c1917' }}
        >
          {log.isPending ? 'جارٍ الحفظ…' : 'حفظ الصيانة'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200">
          إلغاء
        </button>
      </div>
    </form>
  );
}

// ── سجلّ صيانة المعدّة المحدّدة ──────────────────────────────────
function MaintenanceHistory({ equipment }: { equipment: Equipment }) {
  const { data, isLoading, isError, error, refetch } = useMaintenance(equipment.equipment_id);

  if (isLoading) return <LoadingState message="جارٍ تحميل سجلّ الصيانة…" />;
  if (isError) {
    return <ErrorState title="تعذّر تحميل سجلّ الصيانة" detail={errorDetail(error)} onRetry={() => refetch()} />;
  }

  const records = data ?? [];
  if (records.length === 0) {
    return (
      <EmptyState
        icon={<History className="w-8 h-8" />}
        title="لا يوجد سجلّ صيانة بعد"
        hint="لم تُسجَّل أي عمليات صيانة لهذه المعدّة."
      />
    );
  }

  return (
    <ul className="space-y-2" dir="rtl">
      {records.map(r => (
        <li key={r.maintenance_id} className="rounded-lg p-3 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-200">{KIND_LABELS[r.kind] ?? r.kind}</span>
            {r.cost_usd != null && <span className="text-sm font-semibold text-amber-400">{usd(r.cost_usd)}</span>}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
            {r.status && <span>الحالة: {r.status}</span>}
            <span>الجدولة: {fmtDate(r.scheduled_date)}</span>
            <span>التنفيذ: {fmtDate(r.performed_date)}</span>
          </div>
          {r.notes && <p className="mt-1 text-xs text-slate-300">{r.notes}</p>}
        </li>
      ))}
    </ul>
  );
}

// ── الصفحة ──────────────────────────────────────────────────────
export default function EquipmentPage() {
  const role = useAuthStore(s => s.user?.role);
  const mutable = canMutate(role);
  const { data, isLoading, isError, error, refetch } = useEquipment();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const equipment = data ?? [];
  const selected = equipment.find(e => e.equipment_id === selectedId) ?? null;

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">المعدّات</h2>
          <p className="text-sm text-slate-400">إدارة المعدّات وسجلّ الصيانة</p>
        </div>
      </div>

      {mutable && <RegisterForm />}

      {/* قائمة المعدّات */}
      <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
        <div className="flex items-center gap-2 mb-3">
          <Tractor className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">قائمة المعدّات</span>
        </div>

        {isLoading ? (
          <LoadingState message="جارٍ تحميل المعدّات…" />
        ) : isError ? (
          <ErrorState title="تعذّر تحميل المعدّات" detail={errorDetail(error)} onRetry={() => refetch()} />
        ) : equipment.length === 0 ? (
          <EmptyState
            icon={<Tractor className="w-8 h-8" />}
            title="لا توجد معدّات مُسجَّلة بعد"
            hint={mutable ? 'استخدم نموذج «تسجيل معدّة» أعلاه لإضافة أوّل معدّة.' : 'لم تُسجَّل أي معدّات حتى الآن.'}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] text-slate-500 border-b" style={{ borderColor: '#334155' }}>
                  <th className="text-right font-medium py-2 px-2">الاسم</th>
                  <th className="text-right font-medium py-2 px-2">النوع</th>
                  <th className="text-right font-medium py-2 px-2">الحالة</th>
                  <th className="text-right font-medium py-2 px-2">ساعات التشغيل</th>
                </tr>
              </thead>
              <tbody>
                {equipment.map(eq => {
                  const active = eq.equipment_id === selectedId;
                  return (
                    <tr
                      key={eq.equipment_id}
                      onClick={() => setSelectedId(active ? null : eq.equipment_id)}
                      className="cursor-pointer transition-colors border-b"
                      style={{
                        borderColor: '#1e293b',
                        background: active ? '#1e3a1e' : 'transparent',
                      }}
                    >
                      <td className="py-2.5 px-2 text-slate-200 font-medium">{eq.name}</td>
                      <td className="py-2.5 px-2 text-slate-400">{TYPE_LABELS[eq.type] ?? eq.type}</td>
                      <td className="py-2.5 px-2"><StatusBadge status={eq.status} /></td>
                      <td className="py-2.5 px-2 text-slate-300">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-500" />
                          {Number(eq.operating_hours ?? 0).toLocaleString('en-US')}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* تفاصيل المعدّة المحدّدة: صيانة + سجلّ */}
      {selected && (
        <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-semibold text-slate-200">سجلّ صيانة: {selected.name}</span>
              <StatusBadge status={selected.status} />
            </div>
            {mutable && <LogMaintenanceForm equipment={selected} />}
          </div>
          <div className="text-[11px] text-slate-500 mb-3">
            تاريخ الشراء: {fmtDate(selected.purchase_date)} · ساعات التشغيل: {Number(selected.operating_hours ?? 0).toLocaleString('en-US')}
          </div>
          <MaintenanceHistory equipment={selected} />
        </div>
      )}
    </div>
  );
}
