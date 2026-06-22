// ═══════════════════════════════════════════════════════════════
// SAHOOL — DocumentsPage (سجلّ الوثائق — بيانات وصفيّة)
// سجلّ حيّ من /api/v1/documents: عقود/تقارير/صور/خرائط/نتائج مخبريّة.
// مهمّ (صدق): هذا سجلّ بيانات وصفيّة فقط — الملفّ الفعليّ في تخزين الكائنات،
// وstorage_ref مسار/رابط له. النموذج يُسجِّل مرجعاً (metadata) ولا يرفع ملفّاً.
// حالات موحّدة (StateViews)، أزرار محكومة بالدور (RBAC: document:manage)، بلا تلفيق.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  FileText, FileBarChart2, Image as ImageIcon, Map as MapIcon,
  FlaskConical, File, ExternalLink, Plus, RefreshCw, Info, Loader2,
} from 'lucide-react';
import { useDocuments, useCreateDocument } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canManage } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import type { DocumentCategory, DocumentCreateInput, DocumentRecord } from '../services/api';
import { asApiError } from '../services/api';
import { toastStore } from '../services/websocket';
import { Button } from '../components/ds/atoms';
import { Input, Select } from '../components/ds/forms';
import { DataTable, type Column } from '../components/ds/table';
import { Modal } from '../components/ds/modal';
import { T, RADIUS } from '../components/ds/tokens';

// تصنيفات الوثائق المعتمدة خادميّاً + تسمية عربيّة + أيقونة/لون لكلّ تصنيف.
const CATEGORIES: { id: DocumentCategory; label: string; icon: typeof FileText; color: string }[] = [
  { id: 'contract',   label: 'عقد',           icon: FileText,      color: '#38bdf8' },
  { id: 'report',     label: 'تقرير',         icon: FileBarChart2, color: '#a855f7' },
  { id: 'image',      label: 'صورة',          icon: ImageIcon,     color: '#16a34a' },
  { id: 'map',        label: 'خريطة',         icon: MapIcon,       color: '#f59e0b' },
  { id: 'lab_result', label: 'نتيجة مخبريّة', icon: FlaskConical,  color: '#ef4444' },
  { id: 'other',      label: 'أخرى',          icon: File,          color: '#94a3b8' },
];

const CAT_BY_ID: Record<string, { label: string; icon: typeof FileText; color: string }> =
  Object.fromEntries(CATEGORIES.map(c => [c.id, c]));

function formatBytes(bytes: number | null): string {
  if (bytes == null) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const v = bytes / Math.pow(1024, i);
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat('ar', { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

// عرض storage_ref كرابط فقط إن بدا URL (http/https). غير ذلك يُعرَض كنصّ مسار.
function isUrl(ref: string | null): boolean {
  return !!ref && /^https?:\/\//i.test(ref);
}

// وسم التصنيف — يُحافظ على لون/أيقونة كلّ تصنيف (لون مخصّص على خلفيّة باهتة).
function CategoryBadge({ category }: { category: string }) {
  const cfg = CAT_BY_ID[category] ?? CAT_BY_ID.other;
  const Icon = cfg.icon;
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{
        background: `${cfg.color}1a`, color: cfg.color, border: `1px solid ${cfg.color}33`,
        borderRadius: RADIUS.pill, padding: '3px 10px', fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
      }}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {cfg.label}
    </span>
  );
}

// نموذج تسجيل وثيقة (بيانات وصفيّة + storage_ref). صدق: لا يرفع ملفّاً.
function RegisterForm({ onClose }: { onClose: () => void }) {
  const createMut = useCreateDocument();
  const [category, setCategory] = useState<DocumentCategory>('report');
  const [title, setTitle] = useState('');
  const [storageRef, setStorageRef] = useState('');
  const [contentType, setContentType] = useState('');
  const [sizeBytes, setSizeBytes] = useState('');
  const [fieldId, setFieldId] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    if (fieldId.length > 50) return;
    const payload: DocumentCreateInput = {
      category,
      title: title.trim(),
      ...(storageRef.trim()  ? { storage_ref:  storageRef.trim() } : {}),
      ...(contentType.trim() ? { content_type: contentType.trim() } : {}),
      ...(sizeBytes.trim() && !Number.isNaN(Number(sizeBytes)) ? { size_bytes: Number(sizeBytes) } : {}),
      ...(fieldId.trim()     ? { field_id: fieldId.trim() } : {}),
    };
    try {
      await createMut.mutateAsync(payload);
      toastStore.add('success', 'تمّ التسجيل', 'تمّ تسجيل الوثيقة (بيانات وصفيّة).');
      onClose();
    } catch (err) {
      const status = asApiError(err).response?.status;
      const detail = status === 503
        ? 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
        : status === 403
          ? 'لا تملك صلاحية إدارة الوثائق (document:manage).'
          : 'تعذّر تسجيل الوثيقة.';
      toastStore.add('error', 'تعذّر التسجيل', detail);
    }
  };

  return (
    <form onSubmit={submit} dir="rtl" className="space-y-3">
      {/* بيان صدق: تسجيل مرجع لا رفع ملفّ */}
      <div
        className="flex items-start gap-2"
        style={{
          background: T.warnBg, border: `1px solid ${T.warn}55`, color: T.warn,
          borderRadius: RADIUS.sm, padding: 8, fontSize: 11,
        }}
      >
        <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>
          هذا النموذج <strong>يُسجِّل بيانات وصفيّة + مرجع تخزين (storage_ref)</strong> — وليس رفعاً للملفّ.
          الملفّ الفعليّ يبقى في تخزين الكائنات، ويُدخَل هنا مساره أو رابطه.
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select<DocumentCategory>
          label="التصنيف"
          value={category}
          onChange={setCategory}
          options={CATEGORIES.map(c => ({ value: c.id, label: c.label }))}
        />
        <Input
          label="العنوان"
          required
          value={title}
          onChange={setTitle}
          placeholder="عنوان الوثيقة"
        />
        <div className="sm:col-span-2">
          <Input
            label="مرجع التخزين (storage_ref) — مسار أو رابط"
            value={storageRef}
            onChange={setStorageRef}
            placeholder="https://… أو s3://bucket/path"
          />
        </div>
        <Input
          label="نوع المحتوى (content_type)"
          value={contentType}
          onChange={setContentType}
          placeholder="application/pdf"
        />
        <Input
          label="الحجم (bytes)"
          value={sizeBytes}
          onChange={setSizeBytes}
          inputMode="numeric"
          placeholder="مثال: 102400"
        />
        <Input
          label="معرّف الحقل (field_id) — اختياريّ"
          value={fieldId}
          onChange={setFieldId}
          placeholder="field_01"
          error={fieldId.length > 50 ? 'الحدّ الأقصى 50 محرفاً.' : undefined}
        />
      </div>

      <div className="flex items-center gap-2 justify-end pt-1">
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '11px 14px', borderRadius: RADIUS.md,
            border: `1px solid ${T.line}`, background: 'transparent',
            color: T.muted, fontSize: 14, fontWeight: 700, cursor: 'pointer',
          }}
        >
          إلغاء
        </button>
        <button
          type="submit"
          disabled={createMut.isPending || !title.trim() || fieldId.length > 50}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '11px 18px', borderRadius: RADIUS.md, border: 'none',
            background: (createMut.isPending || !title.trim() || fieldId.length > 50) ? T.line : T.green,
            color: (createMut.isPending || !title.trim() || fieldId.length > 50) ? T.muted : '#fff',
            fontSize: 14, fontWeight: 800,
            cursor: (createMut.isPending || !title.trim() || fieldId.length > 50) ? 'not-allowed' : 'pointer',
          }}
        >
          {createMut.isPending
            ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            : <Plus className="w-4 h-4" aria-hidden="true" />}
          تسجيل الوثيقة
        </button>
      </div>
    </form>
  );
}

export default function DocumentsPage() {
  const { user } = useAuthStore();
  // إدارة فقط (owner/manager): تسجيل الوثائق إجراء إداريّ لا يظهر لغير الإدارة.
  const mutateAllowed = canManage(user?.role);

  const [category, setCategory] = useState<DocumentCategory | 'all'>('all');
  const [showForm, setShowForm] = useState(false);

  const { data, isLoading, isError, error, refetch, isFetching } =
    useDocuments(category === 'all' ? undefined : category);

  const docs = data ?? [];

  const errorDetail = (() => {
    const status = asApiError(error).response?.status;
    if (status === 503) return 'خدمة الوثائق غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
    if (status === 403) return 'لا تملك صلاحية عرض الوثائق (document:view).';
    return 'تعذّر الاتصال بخدمة الوثائق.';
  })();

  // DataTable يقيّد الصفّ بـRecord<string,unknown>؛ نوسّع النوع محليّاً دون تغيير الـAPI.
  type Row = DocumentRecord & Record<string, unknown>;
  const columns: Column<Row>[] = [
    {
      key: 'title',
      label: 'العنوان',
      render: (d) => (
        <span style={{ color: T.ink, fontWeight: 600 }}>
          {d.title}
          {d.version > 1 && (
            <span style={{ marginInlineStart: 6, fontSize: 10, color: T.faint }}>v{d.version}</span>
          )}
        </span>
      ),
    },
    {
      key: 'category',
      label: 'التصنيف',
      render: (d) => <CategoryBadge category={d.category} />,
    },
    {
      key: 'content_type',
      label: 'نوع المحتوى',
      render: (d) => <span style={{ color: T.muted, fontSize: 12 }} dir="ltr">{d.content_type ?? '—'}</span>,
    },
    {
      key: 'size_bytes',
      label: 'الحجم',
      render: (d) => <span style={{ color: T.muted, fontSize: 12 }} dir="ltr">{formatBytes(d.size_bytes)}</span>,
    },
    {
      key: 'field_id',
      label: 'الحقل',
      render: (d) => <span style={{ color: T.muted, fontSize: 12 }} dir="ltr">{d.field_id ?? '—'}</span>,
    },
    {
      key: 'created_at',
      label: 'أُنشئت في',
      render: (d) => <span style={{ color: T.muted, fontSize: 12 }}>{formatDate(d.created_at)}</span>,
    },
    {
      key: 'storage_ref',
      label: 'المرجع',
      render: (d) => (
        !d.storage_ref ? (
          <span style={{ color: T.faint }}>—</span>
        ) : isUrl(d.storage_ref) ? (
          <a
            href={d.storage_ref} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 max-w-[180px] truncate"
            style={{ color: T.info, fontSize: 12 }}
            dir="ltr" title={d.storage_ref}
          >
            <ExternalLink className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
            <span className="truncate">فتح</span>
          </a>
        ) : (
          <span
            className="font-mono max-w-[180px] truncate inline-block align-bottom"
            style={{ color: T.muted, fontSize: 12 }}
            dir="ltr" title={d.storage_ref}
          >
            {d.storage_ref}
          </span>
        )
      ),
    },
  ];

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      {/* رأس الصفحة */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold" style={{ color: T.ink }}>الوثائق</h2>
          <p className="text-sm" style={{ color: T.muted }}>
            سجلّ بيانات وصفيّة للوثائق (عقود/تقارير/صور/خرائط/نتائج مخبريّة) — الملفّات في تخزين الكائنات.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()} title="تحديث"
            style={{
              padding: 8, borderRadius: RADIUS.sm, border: `1px solid ${T.line}`,
              background: T.card, color: T.muted, cursor: 'pointer',
            }}
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
          {mutateAllowed && (
            <Button tone="green" full={false} onClick={() => setShowForm(true)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <Plus className="w-4 h-4" aria-hidden="true" />
              تسجيل وثيقة (بيانات وصفيّة)
            </Button>
          )}
        </div>
      </div>

      {/* النموذج داخل مودال (حسب الصلاحيّة) */}
      {mutateAllowed && (
        <Modal
          open={showForm}
          onClose={() => setShowForm(false)}
          title="تسجيل وثيقة (بيانات وصفيّة)"
          maxWidth={640}
        >
          <RegisterForm onClose={() => setShowForm(false)} />
        </Modal>
      )}

      {/* مرشِّح التصنيف */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setCategory('all')}
          style={category === 'all'
            ? { padding: '6px 12px', borderRadius: RADIUS.pill, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: T.greenSoft, border: `1px solid ${T.green}`, color: T.greenDark }
            : { padding: '6px 12px', borderRadius: RADIUS.pill, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: T.card, border: `1px solid ${T.line}`, color: T.muted }}
        >
          الكلّ
        </button>
        {CATEGORIES.map(c => {
          const active = category === c.id;
          const Icon = c.icon;
          return (
            <button
              key={c.id} onClick={() => setCategory(c.id)}
              className="inline-flex items-center gap-1.5"
              style={active
                ? { padding: '6px 12px', borderRadius: RADIUS.pill, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: `${c.color}1a`, border: `1px solid ${c.color}`, color: c.color }
                : { padding: '6px 12px', borderRadius: RADIUS.pill, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: T.card, border: `1px solid ${T.line}`, color: T.muted }}
            >
              <Icon className="w-3 h-3" aria-hidden="true" />
              {c.label}
            </button>
          );
        })}
      </div>

      {/* الجدول / الحالات */}
      {isLoading ? (
        <LoadingState message="جارٍ تحميل الوثائق…" />
      ) : isError ? (
        <ErrorState title="تعذّر تحميل الوثائق" detail={errorDetail} onRetry={() => refetch()} />
      ) : docs.length === 0 ? (
        <EmptyState
          icon={<FileText className="w-8 h-8" />}
          title="لا توجد وثائق بعد"
          hint={category === 'all'
            ? 'لم تُسجَّل أيّ وثيقة حتى الآن.'
            : 'لا توجد وثائق ضمن هذا التصنيف.'}
        />
      ) : (
        <DataTable<Row>
          columns={columns}
          rows={docs as Row[]}
          rowKey={(d) => d.doc_id}
        />
      )}

      {!isLoading && !isError && docs.length > 0 && (
        <p className="text-center" style={{ fontSize: 11, color: T.faint }}>
          {docs.length.toLocaleString('en-US')} وثيقة — بيانات وصفيّة فقط؛ المرجع يشير إلى الملفّ في تخزين الكائنات.
        </p>
      )}
    </div>
  );
}
