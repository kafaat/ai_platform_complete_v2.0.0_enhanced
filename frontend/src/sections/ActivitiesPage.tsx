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
import { useActivities, useCreateActivity } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import type { Activity, ActivityType } from '../services/api';
import { asApiError } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { Card, Pill, Button } from '../components/ds/atoms';
import { Input, Select } from '../components/ds/forms';
import { T } from '../components/ds/tokens';
import type { Tone } from '../components/ds/tokens';

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

// تسمية الحالة + نغمة DS (planned→warn، done→ok، skipped→neutral) بدل
// خريطة الألوان الداكنة السابقة.
const STATUS_STYLE: Record<string, { label: string; tone: Tone }> = {
  planned: { label: 'مُجدوَلة', tone: 'warn' },
  done:    { label: 'مُنفَّذة', tone: 'ok' },
  skipped: { label: 'مُتجاوَزة', tone: 'neutral' },
};

// الخادم يُرجع ISO (YYYY-MM-DD)؛ نعرضه كما هو لتفادي انزياح اليوم بحسب المنطقة
// الزمنيّة (new Date('YYYY-MM-DD') يُفسَّر UTC ثمّ يُعرَض محليّاً).
const fmtDate = (d: string | null) => d || '—';

// رسالة خطأ صادقة مُشتقّة من رمز الحالة.
function errorDetail(err: unknown): string {
  const status = asApiError(err).response?.status;
  if (status === 503) return 'خدمة العمليّات غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 404) return 'الحقل غير موجود ضمن هذا المستأجِر.';
  if (status === 403) return 'لا تملك صلاحية هذه العملية (field:view / field:edit).';
  if (status === 401) return 'انتهت الجلسة. يُرجى تسجيل الدخول من جديد.';
  return 'تعذّر الاتصال بخدمة العمليّات.';
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLE[status] ?? { label: status, tone: 'neutral' as Tone };
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

// ── نموذج تسجيل عمليّة لحقل محدّد ─────────────────────────────────
function AddActivityForm({ fieldId }: { fieldId: string }) {
  const create = useCreateActivity(fieldId);
  const [type, setType] = useState<ActivityType>('irrigation');
  const [title, setTitle] = useState('');
  const [scheduled, setScheduled] = useState('');
  const [performed, setPerformed] = useState('');
  const [notes, setNotes] = useState('');

  const onSubmit = () => {
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
    <Card style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="flex items-center gap-2">
        <Plus className="w-4 h-4" style={{ color: T.green }} />
        <span className="text-sm font-semibold" style={{ color: T.ink }}>تسجيل عمليّة</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select
          label="نوع العمليّة"
          required
          value={type}
          onChange={v => setType(v as ActivityType)}
          options={TYPE_OPTIONS.map(t => ({ value: t, label: TYPE_LABELS[t] }))}
        />
        <Input label="العنوان" value={title} onChange={v => setTitle(v)} placeholder="مثال: رشّ مبيد فطريّ" />
        <Input label="التاريخ المُجدوَل" type="date" value={scheduled} onChange={v => setScheduled(v)} />
        <Input label="تاريخ التنفيذ" type="date" value={performed} onChange={v => setPerformed(v)} />
        <div className="sm:col-span-2">
          <Input label="ملاحظات" value={notes} onChange={v => setNotes(v)} placeholder="اختياري" />
        </div>
      </div>
      {performed && (
        <p className="text-[11px] flex items-center gap-1" style={{ color: T.green }}>
          <CheckCircle2 className="w-3 h-3" /> تحديد تاريخ تنفيذ يضبط الحالة على «مُنفَّذة».
        </p>
      )}
      {create.isError && (
        <p className="text-xs flex items-center gap-1" style={{ color: T.danger }}>
          <AlertTriangle className="w-3 h-3" /> {errorDetail(create.error)}
        </p>
      )}
      <Button onClick={onSubmit} disabled={create.isPending} full={false} style={{ alignSelf: 'flex-start' }}>
        {create.isPending ? 'جارٍ الحفظ…' : 'تسجيل العمليّة'}
      </Button>
    </Card>
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
          <li key={a.activity_id}>
            <Card style={{ background: T.card2 }} pad={12}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold" style={{ color: T.ink }}>
                  {TYPE_LABELS[a.activity_type] ?? a.activity_type}
                  {a.title_ar && <span className="font-normal" style={{ color: T.muted }}> — {a.title_ar}</span>}
                </span>
                <StatusBadge status={a.status} />
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px]" style={{ color: T.muted }}>
                <span className="inline-flex items-center gap-1">
                  <Calendar className="w-3 h-3" style={{ color: T.faint }} /> مُجدوَلة: {fmtDate(a.scheduled_for)}
                </span>
                <span className="inline-flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" style={{ color: T.faint }} /> التنفيذ: {fmtDate(a.performed_on)}
                </span>
              </div>
              {note && <p className="mt-1 text-xs" style={{ color: T.brownSoft }}>{note}</p>}
            </Card>
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
  // «الحقل النشط» المشترك (useSelectedField) — يتبع المستخدم عبر الشاشات.
  const { options: fields, isLoading, isError, error, refetch, fieldId, setFieldId } = useSelectedField();

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div>
        <h2 className="text-xl font-bold" style={{ color: T.ink }}>العمليّات الزراعيّة</h2>
        <p className="text-sm" style={{ color: T.muted }}>تسجيل ومتابعة العمليّات الميدانيّة لكلّ حقل</p>
      </div>

      {/* اختيار الحقل */}
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Sprout className="w-4 h-4" style={{ color: T.green }} />
          <span className="text-sm font-semibold" style={{ color: T.ink }}>اختر الحقل</span>
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
          <Select
            value={fieldId}
            onChange={v => setFieldId(v)}
            placeholder="— اختر حقلاً —"
            options={fields.map(f => ({ value: f.id, label: f.name }))}
          />
        )}
      </Card>

      {/* عند اختيار حقل: النموذج + القائمة */}
      {fieldId && (
        <>
          {mutable && <AddActivityForm fieldId={fieldId} />}
          <Card>
            <div className="flex items-center gap-2 mb-3">
              <ClipboardList className="w-4 h-4" style={{ color: T.green }} />
              <span className="text-sm font-semibold" style={{ color: T.ink }}>سجلّ العمليّات</span>
            </div>
            <ActivityList fieldId={fieldId} />
          </Card>
        </>
      )}
    </div>
  );
}
