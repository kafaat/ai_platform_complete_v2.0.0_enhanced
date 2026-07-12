// ═══════════════════════════════════════════════════════════════
// SAHOOL — InventoryPage (ربط حيّ بـ /api/v1/inventory/*)
// مخزون المدخلات: أصناف (كميّة/وحدة/إعادة طلب) + شارة نقص + الأصناف القاربة
// على الانتهاء. الكتابة (إضافة صنف/دفعة) مُقيَّدة بالدور (canMutate). لا أرقام
// مُلفَّقة — عند الخطأ/الفراغ تُعرض حالة صادقة (StateViews). 503 عند تعطيل DB.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Boxes, PackagePlus, PlusCircle, AlertTriangle, CalendarClock } from 'lucide-react';
import {
  useInventoryItems, useExpiringBatches,
  useCreateInventoryItem, useAddInventoryBatch,
} from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import type { InventoryItem, ExpiringBatch, NewInventoryItem, NewInventoryBatch } from '../services/api';
import { asApiError } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { Card, Button, Pill } from '../components/ds/atoms';
import { Input } from '../components/ds/forms';
import { Modal } from '../components/ds/modal';
import { DataTable, type Column } from '../components/ds/table';
import { T } from '../components/ds/tokens';

// DataTable يتطلّب صفوفاً تطابق Record<string, unknown> (فهرس مفتوح). واجهات
// المخزون مغلقة الحقول، فنوسّعها بفهرس صريح لتوافق القيد دون فقدان حقولها.
type ItemRow = InventoryItem & Record<string, unknown>;
type ExpiringRow = ExpiringBatch & Record<string, unknown>;

// تفسير عربيّ صادق لأخطاء الخادم (يطابق سلوك ReportsPage/CostSummary).
function errDetail(error: unknown, fallback: string): string {
  const status = asApiError(error).response?.status;
  if (status === 503) return 'خدمة المخزون غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض المخزون (inventory:view).';
  return fallback;
}

// فئات المدخلات الزراعيّة القياسيّة — تُدمَج مع فئات المستأجِر القائمة (لا تحلّ محلّها).
const STANDARD_CATEGORIES = [
  'أسمدة', 'بذور', 'مبيدات حشريّة', 'مبيدات فطريّة', 'مبيدات أعشاب',
  'مستلزمات ريّ', 'وقود وزيوت', 'قطع غيار', 'أدوات ومعدّات', 'أعلاف',
];
const OTHER_CATEGORY = '__other__';

// ── نموذج إضافة صنف (داخل Modal) ─────────────────────────────────
function AddItemForm({ onClose, existingItems }: { onClose: () => void; existingItems: InventoryItem[] }) {
  const mut = useCreateInventoryItem();
  const [f, setF] = useState<{ category: string; name: string; unit: string; reorder_level: string; notes: string }>({
    category: '', name: '', unit: '', reorder_level: '', notes: '',
  });
  // «أخرى» تفتح إدخالاً حرّاً — القائمة تُرشد ولا تُقيّد (علّة مُبلَّغة 2026-07-11).
  const [customCategory, setCustomCategory] = useState(false);
  const categories = Array.from(new Set([
    ...STANDARD_CATEGORIES,
    ...existingItems.map((it) => it.category).filter(Boolean),
  ]));
  // اقتراحات الاسم من أصناف الفئة المختارة (datalist: اقتراح لا قيد).
  const nameSuggestions = Array.from(new Set(
    existingItems
      .filter((it) => !f.category || it.category === f.category)
      .map((it) => it.name),
  )).slice(0, 30);

  const onSubmit = () => {
    if (!f.category.trim() || !f.name.trim()) return;
    const payload: NewInventoryItem = {
      category: f.category.trim(),
      name: f.name.trim(),
      ...(f.unit.trim() ? { unit: f.unit.trim() } : {}),
      ...(f.reorder_level.trim() !== '' && !isNaN(Number(f.reorder_level)) ? { reorder_level: Number(f.reorder_level) } : {}),
      ...(f.notes.trim() ? { notes: f.notes.trim() } : {}),
    };
    mut.mutate(payload, { onSuccess: () => onClose() });
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="إضافة صنف جديد"
      footer={
        <>
          <Button tone="gold" full={false} onClick={onClose} style={{ background: 'transparent', color: T.muted, border: `1px solid ${T.line}` }}>
            إلغاء
          </Button>
          <Button full={false} onClick={onSubmit} disabled={mut.isPending || !f.category.trim() || !f.name.trim()}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <PlusCircle className="w-4 h-4" />
            {mut.isPending ? 'جارٍ الحفظ…' : 'حفظ الصنف'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span style={{ color: T.muted }}>الفئة <span style={{ color: T.warn }}>*</span></span>
          <select
            value={customCategory ? OTHER_CATEGORY : f.category}
            onChange={(e) => {
              if (e.target.value === OTHER_CATEGORY) {
                setCustomCategory(true);
                setF(v => ({ ...v, category: '' }));
              } else {
                setCustomCategory(false);
                setF(v => ({ ...v, category: e.target.value }));
              }
            }}
            className="px-3 py-2 rounded-lg"
            style={{ background: T.card2, border: `1px solid ${T.line}`, color: T.ink }}
          >
            <option value="">— اختر فئة —</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            <option value={OTHER_CATEGORY}>فئة أخرى…</option>
          </select>
        </label>
        {customCategory ? (
          <Input label="اسم الفئة الجديدة" required value={f.category}
            onChange={val => setF(v => ({ ...v, category: val }))} placeholder="مثال: مواد تعبئة" />
        ) : <span className="hidden sm:block" />}
        <Input label="الاسم" required value={f.name} list="inventory-item-name-suggestions"
          onChange={val => setF(v => ({ ...v, name: val }))} placeholder="مثال: يوريا 46%" />
        <datalist id="inventory-item-name-suggestions">
          {nameSuggestions.map((n) => <option key={n} value={n} />)}
        </datalist>
        <Input label="الوحدة" value={f.unit} onChange={val => setF(v => ({ ...v, unit: val }))} placeholder="مثال: كيس" />
        <Input label="حدّ إعادة الطلب" type="number" inputMode="decimal"
          value={f.reorder_level} onChange={val => setF(v => ({ ...v, reorder_level: val }))} />
        <div className="sm:col-span-2">
          <Input label="ملاحظات" value={f.notes} onChange={val => setF(v => ({ ...v, notes: val }))} />
        </div>
      </div>
      {mut.isError && (
        <p className="text-xs mt-3" style={{ color: T.warn }}>{errDetail(mut.error, 'تعذّر إضافة الصنف. حاول مرّة أخرى.')}</p>
      )}
    </Modal>
  );
}

// ── نموذج إضافة دفعة لصنف ─────────────────────────────────────────
function AddBatchForm({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const mut = useAddInventoryBatch();
  const [f, setF] = useState<{ quantity: string; batch_code: string; expiry_date: string; supplier: string; notes: string }>({
    quantity: '', batch_code: '', expiry_date: '', supplier: '', notes: '',
  });

  const onSubmit = () => {
    const qty = Number(f.quantity);
    if (f.quantity.trim() === '' || isNaN(qty)) return;
    const batch: NewInventoryBatch = {
      quantity: qty,
      ...(item.unit ? { unit: item.unit } : {}),
      ...(f.batch_code.trim() ? { batch_code: f.batch_code.trim() } : {}),
      ...(f.expiry_date ? { expiry_date: f.expiry_date } : {}),
      ...(f.supplier.trim() ? { supplier: f.supplier.trim() } : {}),
      ...(f.notes.trim() ? { notes: f.notes.trim() } : {}),
    };
    mut.mutate({ itemId: item.item_id, batch }, { onSuccess: () => onClose() });
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={`إضافة دفعة إلى: ${item.name}`}
      footer={
        <>
          <Button tone="gold" full={false} onClick={onClose} style={{ background: 'transparent', color: T.muted, border: `1px solid ${T.line}` }}>
            إلغاء
          </Button>
          <Button tone="gold" full={false} onClick={onSubmit} disabled={mut.isPending || f.quantity.trim() === '' || isNaN(Number(f.quantity))}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <PackagePlus className="w-4 h-4" />
            {mut.isPending ? 'جارٍ الحفظ…' : 'حفظ الدفعة'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Input label={`الكميّة${item.unit ? ` (${item.unit})` : ''}`} required type="number" inputMode="decimal"
          value={f.quantity} onChange={val => setF(v => ({ ...v, quantity: val }))} />
        <Input label="رمز الدفعة" value={f.batch_code} onChange={val => setF(v => ({ ...v, batch_code: val }))} />
        <Input label="تاريخ الانتهاء" type="date" value={f.expiry_date} onChange={val => setF(v => ({ ...v, expiry_date: val }))} />
        <Input label="المورّد" value={f.supplier} onChange={val => setF(v => ({ ...v, supplier: val }))} />
        <div className="sm:col-span-2">
          <Input label="ملاحظات" value={f.notes} onChange={val => setF(v => ({ ...v, notes: val }))} />
        </div>
      </div>
      {mut.isError && (
        <p className="text-xs mt-3" style={{ color: T.warn }}>{errDetail(mut.error, 'تعذّر إضافة الدفعة. حاول مرّة أخرى.')}</p>
      )}
    </Modal>
  );
}

// ── الأصناف القاربة على الانتهاء ──────────────────────────────────
function ExpiringSection() {
  const { data, isLoading, isError, error, refetch } = useExpiringBatches(30);

  if (isLoading) return <LoadingState message="جارٍ تحميل الأصناف القاربة على الانتهاء…" />;
  if (isError) {
    return <ErrorState title="تعذّر تحميل الأصناف القاربة على الانتهاء"
      detail={errDetail(error, 'تعذّر الاتصال بخدمة المخزون.')} onRetry={() => refetch()} />;
  }
  const batches = data ?? [];
  if (batches.length === 0) {
    return <EmptyState icon={<CalendarClock className="w-8 h-8" />}
      title="لا توجد أصناف قاربة على الانتهاء" hint="خلال الـ30 يوماً القادمة." />;
  }

  const columns: Column<ExpiringRow>[] = [
    { key: 'name', label: 'الصنف' },
    { key: 'quantity', label: 'الكميّة', render: b => b.quantity.toLocaleString('en-US') },
    { key: 'unit', label: 'الوحدة', render: b => b.unit ?? '—' },
    {
      key: 'expiry_date', label: 'تاريخ الانتهاء',
      render: b => <Pill tone="warn" icon={<CalendarClock className="w-3 h-3" />}>{b.expiry_date}</Pill>,
    },
  ];

  return <DataTable<ExpiringRow> columns={columns} rows={batches as ExpiringRow[]} rowKey={b => b.batch_id} />;
}

// ── الصفحة ────────────────────────────────────────────────────────
export default function InventoryPage() {
  const role = useAuthStore(s => s.user?.role);
  const mayMutate = canMutate(role);

  const { data, isLoading, isError, error, refetch } = useInventoryItems();
  const [showAddItem, setShowAddItem] = useState(false);
  const [batchFor, setBatchFor] = useState<string | null>(null);

  const items = data ?? [];
  // الصنف المُختار لإضافة دفعة (يقود فتح المودال).
  const batchItem = batchFor ? items.find(it => it.item_id === batchFor) ?? null : null;

  // أعمدة جدول الأصناف (DataTable). عمود «إجراء» يظهر للمخوّلين فقط.
  const itemColumns: Column<ItemRow>[] = [
    { key: 'category', label: 'الفئة', render: it => <span style={{ color: T.muted }}>{it.category}</span> },
    {
      key: 'name', label: 'الاسم',
      render: it => (
        <span className="inline-flex items-center gap-2 flex-wrap">
          <span style={{ color: T.ink }}>{it.name}</span>
          {it.low_stock && (
            <Pill tone="danger" icon={<AlertTriangle className="w-2.5 h-2.5" />}>مخزون منخفض</Pill>
          )}
        </span>
      ),
    },
    { key: 'total_quantity', label: 'الكميّة', render: it => it.total_quantity.toLocaleString('en-US') },
    { key: 'unit', label: 'الوحدة', render: it => it.unit ?? '—' },
    ...(mayMutate
      ? [{
          key: 'item_id' as const, label: 'إجراء',
          render: (it: ItemRow) => (
            <Button tone="gold" full={false} onClick={() => setBatchFor(it.item_id)}
              style={{ padding: '6px 12px', fontSize: 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <PackagePlus className="w-3.5 h-3.5" /> إضافة دفعة
            </Button>
          ),
        }]
      : []),
  ];

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      {/* رأس الصفحة */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div className="flex items-center gap-2">
          <Boxes className="w-5 h-5" style={{ color: T.green }} />
          <div>
            <h2 className="text-xl font-bold" style={{ color: T.ink }}>المخزون</h2>
            <p className="text-sm" style={{ color: T.muted }}>مخزون المدخلات الزراعيّة: الكميّات، حدّ إعادة الطلب، والصلاحيّة.</p>
          </div>
        </div>
        {mayMutate && (
          <Button full={false} onClick={() => setShowAddItem(true)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <PlusCircle className="w-4 h-4" /> إضافة صنف
          </Button>
        )}
      </div>

      {/* نموذج إضافة صنف (للمخوّلين فقط) — داخل Modal */}
      {mayMutate && showAddItem && (
        <AddItemForm onClose={() => setShowAddItem(false)} existingItems={items} />
      )}

      {/* نموذج إضافة دفعة — داخل Modal مدفوع بـbatchFor */}
      {mayMutate && batchItem && (
        <AddBatchForm item={batchItem} onClose={() => setBatchFor(null)} />
      )}

      {/* قائمة الأصناف */}
      <Card style={{ background: T.card2 }}>
        <div className="flex items-center gap-2 mb-3">
          <Boxes className="w-4 h-4" style={{ color: T.green }} />
          <span className="text-sm font-semibold" style={{ color: T.ink }}>الأصناف</span>
        </div>

        {isLoading && <LoadingState message="جارٍ تحميل المخزون…" />}

        {isError && (
          <ErrorState title="تعذّر تحميل المخزون"
            detail={errDetail(error, 'تعذّر الاتصال بخدمة المخزون.')} onRetry={() => refetch()} />
        )}

        {!isLoading && !isError && items.length === 0 && (
          <EmptyState icon={<Boxes className="w-8 h-8" />}
            title="لا توجد أصناف في المخزون بعد"
            hint={mayMutate ? 'ابدأ بإضافة صنف جديد.' : 'لم تُسجَّل أي أصناف حتى الآن.'} />
        )}

        {!isLoading && !isError && items.length > 0 && (
          <DataTable<ItemRow> columns={itemColumns} rows={items as ItemRow[]} rowKey={it => it.item_id} />
        )}
      </Card>

      {/* الأصناف القاربة على الانتهاء */}
      <Card style={{ background: T.card2 }}>
        <div className="flex items-center gap-2 mb-3">
          <CalendarClock className="w-4 h-4" style={{ color: T.warn }} />
          <span className="text-sm font-semibold" style={{ color: T.ink }}>قاربت على الانتهاء (خلال 30 يوماً)</span>
        </div>
        <ExpiringSection />
      </Card>
    </div>
  );
}
