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
import type { MasterDataCategory, MasterDataEntry } from '../services/api';
import { asApiError } from '../services/api';
import { Card, Button } from '../components/ds/atoms';
import { Input } from '../components/ds/forms';
import { DataTable, type Column } from '../components/ds/table';
import { T, RADIUS } from '../components/ds/tokens';

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
  const status = asApiError(error).response?.status;
  if (status === 503) return 'خدمة البيانات المرجعيّة غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض البيانات المرجعيّة (master_data:view).';
  return 'تعذّر الاتصال بخدمة البيانات المرجعيّة.';
}

function AddEntryForm({ category }: { category: MasterDataCategory }) {
  const create = useCreateMasterData();
  const [code, setCode]     = useState('');
  const [nameAr, setNameAr] = useState('');
  const [nameEn, setNameEn] = useState('');

  const status   = asApiError(create.error).response?.status;
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
    <Card pad={16}>
      <form onSubmit={onSubmit} dir="rtl">
        <div className="flex items-center gap-2 mb-3">
          <Plus className="w-4 h-4" style={{ color: T.green }} />
          <span style={{ fontSize: 14, fontWeight: 700, color: T.ink }}>إضافة مُدخَل مرجعيّ</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Input
            label="الرمز"
            required
            value={code}
            onChange={setCode}
            placeholder="مثال: WHEAT_01"
          />
          <Input
            label="الاسم العربيّ"
            required
            value={nameAr}
            onChange={setNameAr}
            placeholder="مثال: قمح صلب"
          />
          <Input
            label="الاسم الإنجليزيّ"
            value={nameEn}
            onChange={setNameEn}
            placeholder="Durum wheat"
          />
        </div>

        {errMsg && (
          <p
            className="mt-3"
            style={{ fontSize: 12, color: isDup ? T.warn : T.danger, fontWeight: 600 }}
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
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '11px 18px', borderRadius: RADIUS.md, border: 'none',
              background: !canSubmit ? T.line : T.green,
              color: !canSubmit ? T.muted : '#fff',
              fontSize: 14, fontWeight: 800,
              cursor: !canSubmit ? 'not-allowed' : 'pointer',
            }}
          >
            {create.isPending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Plus className="w-4 h-4" />}
            إضافة
          </button>
        </div>
      </form>
    </Card>
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

  // DataTable يقيّد الصفّ بـRecord<string,unknown>؛ نوسّع النوع محليّاً دون تغيير الـAPI.
  type Row = MasterDataEntry & Record<string, unknown>;
  const entries = (data ?? []) as Row[];

  const columns: Column<Row>[] = [
    {
      key: 'code',
      label: 'الرمز',
      render: (e) => (
        <span className="font-mono" style={{ color: T.gold, fontSize: 12 }} dir="ltr">{e.code}</span>
      ),
    },
    { key: 'name_ar', label: 'الاسم العربيّ' },
    {
      key: 'name_en',
      label: 'الاسم الإنجليزيّ',
      render: (e) => (
        <span style={{ color: T.muted }} dir="ltr">{e.name_en ?? '—'}</span>
      ),
    },
  ];

  return (
    <DataTable<Row>
      columns={columns}
      rows={entries}
      rowKey={(e) => e.md_id}
      emptyIcon={<Database className="w-8 h-8" />}
      emptyTitle="لا توجد مُدخَلات في هذه الفئة بعد"
      emptyHint="أضِف مُدخَلاً مرجعيّاً جديداً للبدء."
    />
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
        <h2 className="text-xl font-bold flex items-center gap-2" style={{ color: T.ink }}>
          <Database className="w-5 h-5" style={{ color: T.green }} />
          البيانات المرجعيّة
        </h2>
        <p className="text-sm" style={{ color: T.muted }}>
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
              className="text-sm transition-all"
              style={{
                padding: '6px 12px',
                borderRadius: RADIUS.sm,
                background: active ? T.greenSoft : T.card,
                border: `1px solid ${active ? T.green : T.line}`,
                color: active ? T.greenDark : T.muted,
                fontWeight: active ? 700 : 600,
                cursor: 'pointer',
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
