// ═══════════════════════════════════════════════════════════════
// SAHOOL — MasterDataPage (البيانات المرجعيّة)
// كتالوج مرجعيّ حيّ (محصول/تربة/سماد/مبيد/صنف بذور/نوع معدّة/أخرى) عبر
// /api/v1/master-data، مُقيَّد بالدور (master_data:view للعرض،
// master_data:manage للإضافة) وبالمستأجِر. لا بيانات مُلفَّقة — عند الخطأ/الفراغ
// تُعرض حالة صادقة (StateViews). 503 عند تعطيل قاعدة البيانات، 409 عند تكرار
// (المستأجِر، الفئة، الرمز) ⇒ «الرمز موجود مسبقاً». RTL متّسق.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Database, Plus, Loader2 } from 'lucide-react';
import { useMasterData, useCreateMasterData } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { canManage } from '../lib/permissions';
import { useAuthStore } from '../hooks/useAuth';
import type { MasterDataCategory } from '../services/api';

const CATEGORIES: { id: MasterDataCategory; label: string }[] = [
  { id: 'crop',           label: 'المحاصيل' },
  { id: 'soil_type',      label: 'أنواع التربة' },
  { id: 'fertilizer',     label: 'الأسمدة' },
  { id: 'pesticide',      label: 'المبيدات' },
  { id: 'seed_variety',   label: 'أصناف البذور' },
  { id: 'equipment_type', label: 'أنواع المعدّات' },
  { id: 'other',          label: 'أخرى' },
];

// رسالة خطأ صادقة حسب رمز الحالة من الخادم (لا قيمة مُلفَّقة).
function errorDetail(error: unknown): string {
  const status = (error as any)?.response?.status;
  if (status === 503) return 'خدمة البيانات المرجعيّة غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض البيانات المرجعيّة (master_data:view).';
  return 'تعذّر الاتصال بخدمة البيانات المرجعيّة.';
}

function AddEntryForm({ category }: { category: MasterDataCategory }) {
  const create = useCreateMasterData();
  const [code, setCode]     = useState('');
  const [nameAr, setNameAr] = useState('');
  const [nameEn, setNameEn] = useState('');

  const status   = (create.error as any)?.response?.status;
  const isDup     = status === 409;
  const errMsg    = create.isError
    ? isDup
      ? 'الرمز موجود مسبقاً'
      : status === 403
        ? 'لا تملك صلاحية الإضافة (master_data:manage).'
        : status === 503
          ? 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
          : 'تعذّرت إضافة المُدخَل. حاول مجدّداً.'
    : null;

  const canSubmit = code.trim() !== '' && nameAr.trim() !== '' && !create.isPending;

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    create.mutate(
      {
        category,
        code:    code.trim(),
        name_ar: nameAr.trim(),
        ...(nameEn.trim() ? { name_en: nameEn.trim() } : {}),
      },
      {
        onSuccess: () => { setCode(''); setNameAr(''); setNameEn(''); },
      },
    );
  };

  return (
    <form
      onSubmit={onSubmit}
      className="rounded-xl p-4 border"
      style={{ background: '#1e293b', borderColor: '#334155' }}
      dir="rtl"
    >
      <div className="flex items-center gap-2 mb-3">
        <Plus className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">إضافة مُدخَل مرجعيّ</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">الرمز *</label>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="مثال: WHEAT_01"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">الاسم العربيّ *</label>
          <input
            value={nameAr}
            onChange={(e) => setNameAr(e.target.value)}
            placeholder="مثال: قمح صلب"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
          />
        </div>
        <div>
          <label className="block text-[11px] text-slate-400 mb-1">الاسم الإنجليزيّ</label>
          <input
            value={nameEn}
            onChange={(e) => setNameEn(e.target.value)}
            placeholder="Durum wheat"
            dir="ltr"
            className="w-full px-3 py-2 rounded-lg text-sm text-left"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
          />
        </div>
      </div>

      {errMsg && (
        <p
          className="mt-3 text-xs"
          style={{ color: isDup ? '#fbbf24' : '#f87171' }}
          role="alert"
          aria-live="assertive"
        >
          {errMsg}
        </p>
      )}

      <div className="mt-3 flex justify-end">
        <button
          type="submit"
          disabled={!canSubmit}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: '#16a34a', color: '#fff' }}
        >
          {create.isPending
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <Plus className="w-4 h-4" />}
          إضافة
        </button>
      </div>
    </form>
  );
}

function EntriesTable({ category }: { category: MasterDataCategory }) {
  const { data, isLoading, isError, error, refetch } = useMasterData(category);

  if (isLoading) return <LoadingState message="جارٍ تحميل البيانات المرجعيّة…" />;
  if (isError) {
    return (
      <ErrorState
        title="تعذّر تحميل البيانات المرجعيّة"
        detail={errorDetail(error)}
        onRetry={() => refetch()}
      />
    );
  }

  const entries = data ?? [];
  if (entries.length === 0) {
    return (
      <EmptyState
        icon={<Database className="w-8 h-8" />}
        title="لا توجد مُدخَلات في هذه الفئة بعد"
        hint="أضِف مُدخَلاً مرجعيّاً جديداً للبدء."
      />
    );
  }

  return (
    <div className="rounded-xl border overflow-x-auto" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <table className="w-full text-sm text-right" dir="rtl">
        <thead>
          <tr className="text-[11px] text-slate-400" style={{ borderBottom: '1px solid #334155' }}>
            <th className="px-4 py-3 font-medium">الرمز</th>
            <th className="px-4 py-3 font-medium">الاسم العربيّ</th>
            <th className="px-4 py-3 font-medium">الاسم الإنجليزيّ</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.md_id} className="hover:bg-slate-800/40" style={{ borderBottom: '1px solid #1e293b' }}>
              <td className="px-4 py-3 font-mono text-xs text-amber-400" dir="ltr">{e.code}</td>
              <td className="px-4 py-3 text-slate-200">{e.name_ar}</td>
              <td className="px-4 py-3 text-slate-400" dir="ltr">{e.name_en ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MasterDataPage() {
  const role = useAuthStore((s) => s.user?.role);
  // إدارة فقط (owner/manager): البيانات المرجعيّة كتالوج إداريّ، لا يُحرّره غير الإدارة.
  const mutable = canManage(role);
  const [category, setCategory] = useState<MasterDataCategory>('crop');

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div>
        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <Database className="w-5 h-5 text-emerald-500" />
          البيانات المرجعيّة
        </h2>
        <p className="text-sm text-slate-400">
          كتالوج موحّد للمحاصيل وأنواع التربة والأسمدة والمبيدات وأصناف البذور وأنواع المعدّات.
        </p>
      </div>

      {/* تبويبات الفئات السبع */}
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="فئات البيانات المرجعيّة">
        {CATEGORIES.map((c) => {
          const active = c.id === category;
          return (
            <button
              key={c.id}
              role="tab"
              aria-selected={active}
              onClick={() => setCategory(c.id)}
              className="px-3 py-1.5 rounded-lg text-sm transition-all"
              style={{
                background: active ? '#1e3a1e' : '#1e293b',
                border: active ? '1px solid #16a34a' : '1px solid #334155',
                color: active ? '#4ade80' : '#94a3b8',
              }}
            >
              {c.label}
            </button>
          );
        })}
      </div>

      {mutable && <AddEntryForm key={category} category={category} />}

      <EntriesTable category={category} />
    </div>
  );
}

export default MasterDataPage;
