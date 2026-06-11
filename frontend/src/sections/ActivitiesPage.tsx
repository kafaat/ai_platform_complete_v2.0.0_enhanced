// ═══════════════════════════════════════════════════════════════
// SAHOOL — ActivitiesPage (العمليّات الزراعيّة)
// تسجيل العمليّات الميدانيّة لكلّ حقل، بيانات حيّة عبر البوابة:
//   GET  /api/v1/fields/{id}/activities   (field:view)
//   POST /api/v1/fields/{id}/activities   (field:edit)
// مُقيَّد بالدور والمستأجِر (RLS). لا بيانات مُلفَّقة — عند الخطأ/الفراغ
// تُعرض حالة صادقة (StateViews). 503 = قاعدة البيانات معطّلة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Sprout, Plus, AlertTriangle, ClipboardList, Calendar, CheckCircle2 } from 'lucide-react';
import { useFields, useActivities, useCreateActivity } from '../hooks/useApi';
import type { Activity, ActivityType } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';

// ── أسماء عربيّة لأنواع العمليّات والحالات ───────────────────────
const TYPE_LABELS: Record<string, string> = {
  planting:      'بذر/زراعة',
  fertilization: 'تسميد',
  irrigation:    'ريّ',
  spraying:      'رشّ',
  pruning:       'تقليم',
  harvest:       'حصاد',
  scouting:      'كشف/مسح',
};
const TYPE_OPTIONS: ActivityType[] = [
  'planting', 'fertilization', 'irrigation', 'spraying', 'pruning', 'harvest', 'scouting',
];

const STATUS_STYLE: Record<string, { label: string; bg: string; fg: string }> = {
  planned: { label: 'مُجدوَلة', bg: '#f59e0b22', fg: '#fbbf24' },
  done:    { label: 'مُنفَّذة', bg: '#16a34a22', fg: '#4ade80' },
  skipped: { label: 'مُتجاوَزة', bg: '#64748b22', fg: '#94a3b8' },
};

const fmtDate = (d: string | null) => (d ? new Date(d).toLocaleDateString('en-CA') : '—');

// رسالة خطأ صادقة مُشتقّة من رمز الحالة.
function errorDetail(err: unknown): string {
  const status = (err as any)?.response?.status;
  if (status === 503) return 'خدمة العمليّات غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 404) return 'الحقل غير موجود ضمن هذا المستأجِر.';
  if (status === 403) return 'لا تملك صلاحية هذه العملية (field:view / field:edit).';
  if (status === 401) return 'انتهت الجلسة. يُرجى تسجيل الدخول من جديد.';
  return 'تعذّر الاتصال بخدمة العمليّات.';
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { label: status, bg: '#33415544', fg: '#cbd5e1' };
  return (
    <span className="px-2 py-0.5 rounded-full text-[11px] font-medium" style={{ background: s.bg, color: s.fg }}>
      {s.label}
    </span>
  );
}

const input = 'px-3 py-2 rounded-lg text-sm w-full';
const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

// ── نموذج تسجيل عمليّة لحقل محدّد ─────────────────────────────────
function AddActivityForm({ fieldId }: { fieldId: string }) {
  const create = useCreateActivity(fieldId);
  const [type, setType] = useState<ActivityType>('irrigation');
  const [title, setTitle] = useState('');
  const [scheduled, setScheduled] = useState('');
  const [performed, setPerformed] = useState('');
  const [notes, setNotes] = useState('');

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (create.isPending) return;
    create.mutate(
      {
        activity_type: type,
        ...(title.trim() ? { title_ar: title.trim() } : {}),
        ...(scheduled ? { scheduled_for: scheduled } : {}),
        ...(performed ? { performed_on: performed } : {}),
        ...(notes.trim() ? { details: { notes: notes.trim() } } : {}),
      },
      {
        onSuccess: () => {
          setType('irrigation'); setTitle(''); setScheduled(''); setPerformed(''); setNotes('');
        },
      },
    );
  };

  return (
    <form onSubmit={onSubmit} className="rounded-xl p-4 border space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }} dir="rtl">
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">تسجيل عمليّة</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">نوع العمليّة *</label>
          <select className={input} style={inputStyle} value={type} onChange={e => setType(e.target.value as ActivityType)}>
            {TYPE_OPTIONS.map(t => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">العنوان</label>
          <input className={input} style={inputStyle} value={title} onChange={e => setTitle(e.target.value)} placeholder="مثال: رشّ مبيد فطريّ" />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">التاريخ المُجدوَل</label>
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
      {performed && (
        <p className="text-[11px] text-emerald-400 flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> تحديد تاريخ تنفيذ يضبط الحالة على «مُنفَّذة».
        </p>
      )}
      {create.isError && (
        <p className="text-xs text-red-400 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" /> {errorDetail(create.error)}
        </p>
      )}
      <button
        type="submit"
        disabled={create.isPending}
        className="px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
        style={{ background: '#16a34a', color: '#fff' }}
      >
        {create.isPending ? 'جارٍ الحفظ…' : 'تسجيل العمليّة'}
      </button>
    </form>
  );
}

// ── قائمة عمليّات الحقل المحدّد ───────────────────────────────────
function ActivityList({ fieldId }: { fieldId: string }) {
  const { data, isLoading, isError, error, refetch } = useActivities(fieldId);

  if (isLoading) return <LoadingState message="جارٍ تحميل العمليّات…" />;
  if (isError) {
    return <ErrorState title="تعذّر تحميل العمليّات" detail={errorDetail(error)} onRetry={() => refetch()} />;
  }

  const activities: Activity[] = data ?? [];
  if (activities.length === 0) {
    return (
      <EmptyState
        icon={<ClipboardList className="w-8 h-8" />}
        title="لا توجد عمليّات مُسجَّلة بعد"
        hint="استخدم نموذج «تسجيل عمليّة» أعلاه لإضافة أوّل عمليّة لهذا الحقل."
      />
    );
  }

  return (
    <ul className="space-y-2" dir="rtl">
      {activities.map(a => {
        const note = typeof a.details?.notes === 'string' ? a.details.notes : null;
        return (
          <li key={a.activity_id} className="rounded-lg p-3 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-200">
                {TYPE_LABELS[a.activity_type] ?? a.activity_type}
                {a.title_ar && <span className="text-slate-400 font-normal"> — {a.title_ar}</span>}
              </span>
              <StatusBadge status={a.status} />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
              <span className="inline-flex items-center gap-1">
                <Calendar className="w-3 h-3 text-slate-500" /> مُجدوَلة: {fmtDate(a.scheduled_for)}
              </span>
              <span className="inline-flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-slate-500" /> التنفيذ: {fmtDate(a.performed_on)}
              </span>
            </div>
            {note && <p className="mt-1 text-xs text-slate-300">{note}</p>}
          </li>
        );
      })}
    </ul>
  );
}

// ── الصفحة ──────────────────────────────────────────────────────
export default function ActivitiesPage() {
  const role = useAuthStore(s => s.user?.role);
  const mutable = canMutate(role);
  const { data: fieldsData, isLoading, isError, error, refetch } = useFields();
  const [fieldId, setFieldId] = useState<string>('');

  const fields = ((fieldsData as { fields?: any[] } | undefined)?.fields ?? []).map((f) => ({
    id: String(f.field_id ?? f.id),
    name: String(f.name_ar ?? f.name ?? 'حقل'),
  }));

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div>
        <h2 className="text-xl font-bold text-slate-100">العمليّات الزراعيّة</h2>
        <p className="text-sm text-slate-400">تسجيل ومتابعة العمليّات الميدانيّة لكلّ حقل</p>
      </div>

      {/* اختيار الحقل */}
      <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
        <div className="flex items-center gap-2 mb-3">
          <Sprout className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">اختر الحقل</span>
        </div>
        {isLoading ? (
          <LoadingState message="جارٍ تحميل الحقول…" />
        ) : isError ? (
          <ErrorState title="تعذّر تحميل الحقول" detail={errorDetail(error)} onRetry={() => refetch()} />
        ) : fields.length === 0 ? (
          <EmptyState
            icon={<Sprout className="w-8 h-8" />}
            title="لا توجد حقول بعد"
            hint="أضِف حقلاً أوّلاً من شاشة «إدارة الحقول» لتسجيل عمليّاته."
          />
        ) : (
          <select
            className={input}
            style={inputStyle}
            value={fieldId}
            onChange={e => setFieldId(e.target.value)}
          >
            <option value="">— اختر حقلاً —</option>
            {fields.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        )}
      </div>

      {/* عند اختيار حقل: النموذج + القائمة */}
      {fieldId && (
        <>
          {mutable && <AddActivityForm fieldId={fieldId} />}
          <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 mb-3">
              <ClipboardList className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-slate-200">سجلّ العمليّات</span>
            </div>
            <ActivityList fieldId={fieldId} />
          </div>
        </>
      )}
    </div>
  );
}
