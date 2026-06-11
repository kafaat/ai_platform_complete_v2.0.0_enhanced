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
import { canMutate } from '../lib/permissions';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import type { DocumentCategory, DocumentCreateInput } from '../services/api';
import { toastStore } from '../services/websocket';

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

function CategoryBadge({ category }: { category: string }) {
  const cfg = CAT_BY_ID[category] ?? CAT_BY_ID.other;
  const Icon = cfg.icon;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium"
      style={{ background: `${cfg.color}1a`, color: cfg.color, border: `1px solid ${cfg.color}33` }}
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
      const status = (err as any)?.response?.status;
      const detail = status === 503
        ? 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
        : status === 403
          ? 'لا تملك صلاحية إدارة الوثائق (document:manage).'
          : 'تعذّر تسجيل الوثيقة.';
      toastStore.add('error', 'تعذّر التسجيل', detail);
    }
  };

  const labelCls = 'text-xs text-slate-400 mb-1 block';
  const inputCls = 'w-full px-3 py-2 rounded-lg text-sm';
  const inputStyle = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

  return (
    <form onSubmit={submit} className="rounded-xl p-4 border space-y-3" dir="rtl"
      style={{ background: '#1e293b', borderColor: '#334155' }}>
      {/* بيان صدق: تسجيل مرجع لا رفع ملفّ */}
      <div className="flex items-start gap-2 text-[11px] text-amber-300/90 rounded-lg p-2"
        style={{ background: '#2a1a00', border: '1px solid #f59e0b33' }}>
        <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
        <span>
          هذا النموذج <strong>يُسجِّل بيانات وصفيّة + مرجع تخزين (storage_ref)</strong> — وليس رفعاً للملفّ.
          الملفّ الفعليّ يبقى في تخزين الكائنات، ويُدخَل هنا مساره أو رابطه.
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className={labelCls} htmlFor="doc-category">التصنيف</label>
          <select id="doc-category" value={category}
            onChange={e => setCategory(e.target.value as DocumentCategory)}
            className={inputCls} style={inputStyle}>
            {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls} htmlFor="doc-title">العنوان *</label>
          <input id="doc-title" value={title} onChange={e => setTitle(e.target.value)}
            required maxLength={255} placeholder="عنوان الوثيقة"
            className={inputCls} style={inputStyle} />
        </div>
        <div className="sm:col-span-2">
          <label className={labelCls} htmlFor="doc-ref">مرجع التخزين (storage_ref) — مسار أو رابط</label>
          <input id="doc-ref" value={storageRef} onChange={e => setStorageRef(e.target.value)}
            placeholder="https://… أو s3://bucket/path"
            className={inputCls} style={inputStyle} dir="ltr" />
        </div>
        <div>
          <label className={labelCls} htmlFor="doc-ct">نوع المحتوى (content_type)</label>
          <input id="doc-ct" value={contentType} onChange={e => setContentType(e.target.value)}
            placeholder="application/pdf"
            className={inputCls} style={inputStyle} dir="ltr" />
        </div>
        <div>
          <label className={labelCls} htmlFor="doc-size">الحجم (bytes)</label>
          <input id="doc-size" value={sizeBytes} onChange={e => setSizeBytes(e.target.value)}
            inputMode="numeric" placeholder="مثال: 102400"
            className={inputCls} style={inputStyle} dir="ltr" />
        </div>
        <div>
          <label className={labelCls} htmlFor="doc-field">معرّف الحقل (field_id) — اختياريّ</label>
          <input id="doc-field" value={fieldId} onChange={e => setFieldId(e.target.value)}
            maxLength={50} placeholder="field_01"
            className={inputCls} style={inputStyle} dir="ltr" />
          {fieldId.length > 50 && (
            <p className="text-[10px] text-red-400 mt-1">الحدّ الأقصى 50 محرفاً.</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 justify-end pt-1">
        <button type="button" onClick={onClose}
          className="px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 border border-slate-700">
          إلغاء
        </button>
        <button type="submit" disabled={createMut.isPending || !title.trim() || fieldId.length > 50}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50"
          style={{ background: '#16a34a' }}>
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
  const mutateAllowed = canMutate(user?.role);

  const [category, setCategory] = useState<DocumentCategory | 'all'>('all');
  const [showForm, setShowForm] = useState(false);

  const { data, isLoading, isError, error, refetch, isFetching } =
    useDocuments(category === 'all' ? undefined : category);

  const docs = data ?? [];

  const errorDetail = (() => {
    const status = (error as any)?.response?.status;
    if (status === 503) return 'خدمة الوثائق غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
    if (status === 403) return 'لا تملك صلاحية عرض الوثائق (document:view).';
    return 'تعذّر الاتصال بخدمة الوثائق.';
  })();

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      {/* رأس الصفحة */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">الوثائق</h2>
          <p className="text-sm text-slate-400">
            سجلّ بيانات وصفيّة للوثائق (عقود/تقارير/صور/خرائط/نتائج مخبريّة) — الملفّات في تخزين الكائنات.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()} title="تحديث"
            className="p-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200">
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
          {mutateAllowed && (
            <button onClick={() => setShowForm(v => !v)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-white"
              style={{ background: '#16a34a' }}>
              <Plus className="w-4 h-4" aria-hidden="true" />
              تسجيل وثيقة (بيانات وصفيّة)
            </button>
          )}
        </div>
      </div>

      {/* النموذج (حسب الصلاحيّة) */}
      {mutateAllowed && showForm && <RegisterForm onClose={() => setShowForm(false)} />}

      {/* مرشِّح التصنيف */}
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setCategory('all')}
          className="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors"
          style={category === 'all'
            ? { background: '#1e3a1e', borderColor: '#16a34a', color: '#4ade80' }
            : { background: '#1e293b', borderColor: '#334155', color: '#94a3b8' }}>
          الكلّ
        </button>
        {CATEGORIES.map(c => {
          const active = category === c.id;
          const Icon = c.icon;
          return (
            <button key={c.id} onClick={() => setCategory(c.id)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors"
              style={active
                ? { background: `${c.color}1a`, borderColor: c.color, color: c.color }
                : { background: '#1e293b', borderColor: '#334155', color: '#94a3b8' }}>
              <Icon className="w-3 h-3" aria-hidden="true" />
              {c.label}
            </button>
          );
        })}
      </div>

      {/* الجدول / الحالات */}
      <div className="rounded-xl border overflow-hidden" style={{ background: '#0f1117', borderColor: '#334155' }}>
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-[11px] text-slate-500 border-b" style={{ borderColor: '#334155' }}>
                  <th className="px-3 py-2 font-medium">العنوان</th>
                  <th className="px-3 py-2 font-medium">التصنيف</th>
                  <th className="px-3 py-2 font-medium">نوع المحتوى</th>
                  <th className="px-3 py-2 font-medium">الحجم</th>
                  <th className="px-3 py-2 font-medium">الحقل</th>
                  <th className="px-3 py-2 font-medium">أُنشئت في</th>
                  <th className="px-3 py-2 font-medium">المرجع</th>
                </tr>
              </thead>
              <tbody>
                {docs.map(d => (
                  <tr key={d.doc_id} className="border-b last:border-0 hover:bg-slate-800/40"
                    style={{ borderColor: '#1e293b' }}>
                    <td className="px-3 py-2.5 text-slate-100 font-medium">
                      {d.title}
                      {d.version > 1 && (
                        <span className="mr-1.5 text-[10px] text-slate-500">v{d.version}</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5"><CategoryBadge category={d.category} /></td>
                    <td className="px-3 py-2.5 text-slate-400 text-xs" dir="ltr">{d.content_type ?? '—'}</td>
                    <td className="px-3 py-2.5 text-slate-400 text-xs" dir="ltr">{formatBytes(d.size_bytes)}</td>
                    <td className="px-3 py-2.5 text-slate-400 text-xs" dir="ltr">{d.field_id ?? '—'}</td>
                    <td className="px-3 py-2.5 text-slate-400 text-xs">{formatDate(d.created_at)}</td>
                    <td className="px-3 py-2.5 text-xs">
                      {!d.storage_ref ? (
                        <span className="text-slate-600">—</span>
                      ) : isUrl(d.storage_ref) ? (
                        <a href={d.storage_ref} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sky-400 hover:text-sky-300 max-w-[180px] truncate"
                          dir="ltr" title={d.storage_ref}>
                          <ExternalLink className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                          <span className="truncate">فتح</span>
                        </a>
                      ) : (
                        <span className="text-slate-400 font-mono max-w-[180px] truncate inline-block align-bottom"
                          dir="ltr" title={d.storage_ref}>
                          {d.storage_ref}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {!isLoading && !isError && docs.length > 0 && (
        <p className="text-[11px] text-slate-500 text-center">
          {docs.length.toLocaleString('en-US')} وثيقة — بيانات وصفيّة فقط؛ المرجع يشير إلى الملفّ في تخزين الكائنات.
        </p>
      )}
    </div>
  );
}
