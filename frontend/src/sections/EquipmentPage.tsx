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
import { Card, Button, Pill, SectionLabel } from '../components/ds/atoms';
import { Input, Select } from '../components/ds/forms';
import { DataTable, type Column } from '../components/ds/table';
import { equipStatusAr, equipStatusTone } from '../components/ds/status';
import { T } from '../components/ds/tokens';

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

// تسمية الحالة من مصدر DS الموحّد (equipStatusAr)، مع استثناء «retired» الذي لا
// يضمّه المصدر العامّ — نُبقي تسميته العربيّة الأصليّة هنا (حفظاً للسلوك).
function statusLabel(status: string): string {
  if ((status ?? '').toLowerCase() === 'retired') return 'مُتقاعدة';
  return equipStatusAr(status);
}

function StatusBadge({ status }: { status: string }) {
  return <Pill tone={equipStatusTone(status)}>{statusLabel(status)}</Pill>;
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

  return (
    <Card>
      <form onSubmit={onSubmit} className="space-y-3" dir="rtl">
        <SectionLabel>
          <span className="inline-flex items-center gap-2">
            <Plus className="w-4 h-4" style={{ color: T.green }} />
            تسجيل معدّة
          </span>
        </SectionLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input
            label="الاسم" required
            value={name} onChange={v => setName(v)}
            placeholder="مثال: جرّار جون دير 5075"
          />
          <Select<EquipmentType>
            label="النوع" required
            value={type} onChange={v => setType(v)}
            options={TYPE_OPTIONS.map(t => ({ value: t, label: TYPE_LABELS[t] }))}
          />
          <Input
            label="ساعات التشغيل" type="number" inputMode="decimal"
            value={hours} onChange={v => setHours(v)} placeholder="0"
          />
          <Input
            label="تاريخ الشراء" type="date"
            value={purchase} onChange={v => setPurchase(v)}
          />
          <Input
            label="ملاحظات" style={{ gridColumn: '1 / -1' }}
            value={notes} onChange={v => setNotes(v)} placeholder="اختياري"
          />
        </div>
        {create.isError && (
          <p className="text-xs flex items-center gap-1" style={{ color: T.danger }}>
            <AlertTriangle className="w-3 h-3" /> {errorDetail(create.error)}
          </p>
        )}
        <Button
          full={false}
          disabled={!name.trim() || create.isPending}
          onClick={() => onSubmit({ preventDefault: () => {} } as React.FormEvent)}
        >
          {create.isPending ? 'جارٍ الحفظ…' : 'تسجيل المعدّة'}
        </Button>
      </form>
    </Card>
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

  if (!open) {
    return (
      <Button tone="gold" full={false} onClick={() => setOpen(true)} style={{ padding: '7px 12px', fontSize: 13 }}>
        <span className="inline-flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5" /> تسجيل صيانة
        </span>
      </Button>
    );
  }

  return (
    <Card style={{ background: T.card2, marginTop: 8 }}>
      <form onSubmit={onSubmit} className="space-y-3" dir="rtl">
        <SectionLabel>
          <span className="inline-flex items-center gap-2">
            <Wrench className="w-4 h-4" style={{ color: T.warn }} />
            صيانة: {equipment.name}
          </span>
        </SectionLabel>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Select<MaintenanceKind>
            label="النوع" required
            value={kind} onChange={v => setKind(v)}
            options={KIND_OPTIONS.map(k => ({ value: k, label: KIND_LABELS[k] }))}
          />
          <Input
            label="التكلفة (USD)" type="number" inputMode="decimal"
            value={cost} onChange={v => setCost(v)} placeholder="0"
          />
          <Input
            label="تاريخ الجدولة" type="date"
            value={scheduled} onChange={v => setScheduled(v)}
          />
          <Input
            label="تاريخ التنفيذ" type="date"
            value={performed} onChange={v => setPerformed(v)}
          />
          <Input
            label="ملاحظات" style={{ gridColumn: '1 / -1' }}
            value={notes} onChange={v => setNotes(v)} placeholder="اختياري"
          />
        </div>
        {kind === 'breakdown' && (
          <p className="text-[11px] flex items-center gap-1" style={{ color: T.warn }}>
            <AlertTriangle className="w-3 h-3" /> تسجيل عطل سيقلب حالة المعدّة إلى «معطّلة».
          </p>
        )}
        {log.isError && (
          <p className="text-xs flex items-center gap-1" style={{ color: T.danger }}>
            <AlertTriangle className="w-3 h-3" /> {errorDetail(log.error)}
          </p>
        )}
        <div className="flex gap-2">
          <Button
            tone="gold" full={false}
            disabled={log.isPending}
            onClick={() => onSubmit({ preventDefault: () => {} } as React.FormEvent)}
          >
            {log.isPending ? 'جارٍ الحفظ…' : 'حفظ الصيانة'}
          </Button>
          <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg text-sm" style={{ color: T.muted }}>
            إلغاء
          </button>
        </div>
      </form>
    </Card>
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
        <li key={r.maintenance_id}>
          <Card pad={12} style={{ background: T.card2 }}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold" style={{ color: T.ink }}>{KIND_LABELS[r.kind] ?? r.kind}</span>
              {r.cost_usd != null && <span className="text-sm font-semibold" style={{ color: T.warn }}>{usd(r.cost_usd)}</span>}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px]" style={{ color: T.muted }}>
              {r.status && <span>الحالة: {r.status}</span>}
              <span>الجدولة: {fmtDate(r.scheduled_date)}</span>
              <span>التنفيذ: {fmtDate(r.performed_date)}</span>
            </div>
            {r.notes && <p className="mt-1 text-xs" style={{ color: T.brownSoft }}>{r.notes}</p>}
          </Card>
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

  type EquipmentRow = Equipment & Record<string, unknown>;
  const columns: Column<EquipmentRow>[] = [
    { key: 'name', label: 'الاسم', render: (eq) => <span style={{ fontWeight: 600 }}>{eq.name}</span> },
    { key: 'type', label: 'النوع', render: (eq) => <span style={{ color: T.muted }}>{TYPE_LABELS[eq.type] ?? eq.type}</span> },
    { key: 'status', label: 'الحالة', render: (eq) => <StatusBadge status={eq.status} /> },
    {
      key: 'operating_hours', label: 'ساعات التشغيل',
      render: (eq) => (
        <span className="inline-flex items-center gap-1" style={{ color: T.brownSoft }}>
          <Clock className="w-3 h-3" style={{ color: T.faint }} />
          {Number(eq.operating_hours ?? 0).toLocaleString('en-US')}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold" style={{ color: T.ink }}>المعدّات</h2>
          <p className="text-sm" style={{ color: T.muted }}>إدارة المعدّات وسجلّ الصيانة</p>
        </div>
      </div>

      {mutable && <RegisterForm />}

      {/* قائمة المعدّات */}
      <Card>
        <SectionLabel>
          <span className="inline-flex items-center gap-2">
            <Tractor className="w-4 h-4" style={{ color: T.green }} />
            قائمة المعدّات
          </span>
        </SectionLabel>

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
          <DataTable<EquipmentRow>
            columns={columns}
            rows={equipment as EquipmentRow[]}
            rowKey={(eq) => eq.equipment_id}
            onRowClick={(eq) => setSelectedId(eq.equipment_id === selectedId ? null : eq.equipment_id)}
          />
        )}
      </Card>

      {/* تفاصيل المعدّة المحدّدة: صيانة + سجلّ */}
      {selected && (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <History className="w-4 h-4" style={{ color: T.warn }} />
              <span className="text-sm font-semibold" style={{ color: T.ink }}>سجلّ صيانة: {selected.name}</span>
              <StatusBadge status={selected.status} />
            </div>
            {mutable && <LogMaintenanceForm equipment={selected} />}
          </div>
          <div className="text-[11px] mb-3" style={{ color: T.muted }}>
            تاريخ الشراء: {fmtDate(selected.purchase_date)} · ساعات التشغيل: {Number(selected.operating_hours ?? 0).toLocaleString('en-US')}
          </div>
          <MaintenanceHistory equipment={selected} />
        </Card>
      )}
    </div>
  );
}
