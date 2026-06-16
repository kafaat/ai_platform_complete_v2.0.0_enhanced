// ═══════════════════════════════════════════════════════════════
// SAHOOL — InventoryPage (ربط حيّ بـ /api/v1/inventory/*)
// مخزون المدخلات: أصناف (كميّة/وحدة/إعادة طلب) + شارة نقص + الأصناف القاربة
// على الانتهاء. الكتابة (إضافة صنف/دفعة) مُقيَّدة بالدور (canMutate). لا أرقام
// مُلفَّقة — عند الخطأ/الفراغ تُعرض حالة صادقة (StateViews). 503 عند تعطيل DB.
// ═══════════════════════════════════════════════════════════════
import { useState, Fragment } from 'react';
import { Boxes, PackagePlus, PlusCircle, AlertTriangle, CalendarClock, X } from 'lucide-react';
import {
  useInventoryItems, useExpiringBatches,
  useCreateInventoryItem, useAddInventoryBatch,
} from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import type { InventoryItem, NewInventoryItem, NewInventoryBatch } from '../services/api';
import { asApiError } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

// تفسير عربيّ صادق لأخطاء الخادم (يطابق سلوك ReportsPage/CostSummary).
function errDetail(error: unknown, fallback: string): string {
  const status = asApiError(error).response?.status;
  if (status === 503) return 'خدمة المخزون غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض المخزون (inventory:view).';
  return fallback;
}

const CARD = { background: '#1e293b', borderColor: '#334155' } as const;
const PANEL = { background: '#0f1117', borderColor: '#334155' } as const;
const INPUT = { background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' } as const;

// ── نموذج إضافة صنف ──────────────────────────────────────────────
function AddItemForm({ onClose }: { onClose: () => void }) {
  const mut = useCreateInventoryItem();
  const [f, setF] = useState<{ category: string; name: string; unit: string; reorder_level: string; notes: string }>({
    category: '', name: '', unit: '', reorder_level: '', notes: '',
  });

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
    <div className="rounded-xl border p-4 space-y-3" style={CARD}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <PlusCircle className="w-4 h-4 text-emerald-400" /> إضافة صنف جديد
        </span>
        <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300" title="إغلاق">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الفئة *</span>
          <input value={f.category} onChange={e => setF(v => ({ ...v, category: e.target.value }))}
            placeholder="مثال: أسمدة"
            className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الاسم *</span>
          <input value={f.name} onChange={e => setF(v => ({ ...v, name: e.target.value }))}
            placeholder="مثال: يوريا 46%"
            className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">الوحدة</span>
          <input value={f.unit} onChange={e => setF(v => ({ ...v, unit: e.target.value }))}
            placeholder="مثال: كيس"
            className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">حدّ إعادة الطلب</span>
          <input type="number" inputMode="decimal" step="any"
            value={f.reorder_level} onChange={e => setF(v => ({ ...v, reorder_level: e.target.value }))}
            className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">ملاحظات</span>
          <input value={f.notes} onChange={e => setF(v => ({ ...v, notes: e.target.value }))}
            className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
        </label>
      </div>
      {mut.isError && (
        <p className="text-xs text-orange-300">{errDetail(mut.error, 'تعذّر إضافة الصنف. حاول مرّة أخرى.')}</p>
      )}
      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-slate-300 border" style={{ borderColor: '#334155' }}>
          إلغاء
        </button>
        <button onClick={onSubmit} disabled={mut.isPending || !f.category.trim() || !f.name.trim()}
          className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
          style={{ background: '#16a34a' }}>
          <PlusCircle className="w-4 h-4" />
          {mut.isPending ? 'جارٍ الحفظ…' : 'حفظ الصنف'}
        </button>
      </div>
    </div>
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
    <tr>
      <td colSpan={5} className="p-3" style={{ background: '#0f1117' }}>
        <div className="rounded-lg border p-3 space-y-3" style={CARD}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <PackagePlus className="w-4 h-4 text-sky-400" /> إضافة دفعة إلى: {item.name}
            </span>
            <button onClick={onClose} className="p-1 text-slate-500 hover:text-slate-300" title="إغلاق">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">الكميّة *{item.unit ? ` (${item.unit})` : ''}</span>
              <input type="number" inputMode="decimal" step="any"
                value={f.quantity} onChange={e => setF(v => ({ ...v, quantity: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">رمز الدفعة</span>
              <input value={f.batch_code} onChange={e => setF(v => ({ ...v, batch_code: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">تاريخ الانتهاء</span>
              <input type="date" value={f.expiry_date} onChange={e => setF(v => ({ ...v, expiry_date: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">المورّد</span>
              <input value={f.supplier} onChange={e => setF(v => ({ ...v, supplier: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-xs text-slate-400">ملاحظات</span>
              <input value={f.notes} onChange={e => setF(v => ({ ...v, notes: e.target.value }))}
                className="px-3 py-2 rounded-lg text-sm" style={INPUT} />
            </label>
          </div>
          {mut.isError && (
            <p className="text-xs text-orange-300">{errDetail(mut.error, 'تعذّر إضافة الدفعة. حاول مرّة أخرى.')}</p>
          )}
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-slate-300 border" style={{ borderColor: '#334155' }}>
              إلغاء
            </button>
            <button onClick={onSubmit} disabled={mut.isPending || f.quantity.trim() === '' || isNaN(Number(f.quantity))}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
              style={{ background: '#0ea5e9' }}>
              <PackagePlus className="w-4 h-4" />
              {mut.isPending ? 'جارٍ الحفظ…' : 'حفظ الدفعة'}
            </button>
          </div>
        </div>
      </td>
    </tr>
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

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-right">
        <thead>
          <tr className="text-[11px] text-slate-400 border-b" style={{ borderColor: '#334155' }}>
            <th className="py-2 px-2 font-medium">الصنف</th>
            <th className="py-2 px-2 font-medium">الكميّة</th>
            <th className="py-2 px-2 font-medium">الوحدة</th>
            <th className="py-2 px-2 font-medium">تاريخ الانتهاء</th>
          </tr>
        </thead>
        <tbody>
          {batches.map(b => (
            <tr key={b.batch_id} className="border-b last:border-0" style={{ borderColor: '#1e293b' }}>
              <td className="py-2 px-2 text-slate-200">{b.name}</td>
              <td className="py-2 px-2 text-slate-300">{b.quantity.toLocaleString('en-US')}</td>
              <td className="py-2 px-2 text-slate-400">{b.unit ?? '—'}</td>
              <td className="py-2 px-2">
                <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                  style={{ background: '#2a1a00', color: '#fbbf24', border: '1px solid #f59e0b44' }}>
                  <CalendarClock className="w-3 h-3" /> {b.expiry_date}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── الصفحة ────────────────────────────────────────────────────────
export default function InventoryPage() {
  const role = useAuthStore(s => s.user?.role);
  const mayMutate = canMutate(role);

  const { data, isLoading, isError, error, refetch } = useInventoryItems();
  const [showAddItem, setShowAddItem] = useState(false);
  const [batchFor, setBatchFor] = useState<string | null>(null);

  const items = data ?? [];

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      {/* رأس الصفحة */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div className="flex items-center gap-2">
          <Boxes className="w-5 h-5 text-emerald-400" />
          <div>
            <h2 className="text-xl font-bold text-slate-100">المخزون</h2>
            <p className="text-sm text-slate-400">مخزون المدخلات الزراعيّة: الكميّات، حدّ إعادة الطلب، والصلاحيّة.</p>
          </div>
        </div>
        {mayMutate && !showAddItem && (
          <button onClick={() => setShowAddItem(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white"
            style={{ background: '#16a34a' }}>
            <PlusCircle className="w-4 h-4" /> إضافة صنف
          </button>
        )}
      </div>

      {/* نموذج إضافة صنف (للمخوّلين فقط) */}
      {mayMutate && showAddItem && <AddItemForm onClose={() => setShowAddItem(false)} />}

      {/* قائمة الأصناف */}
      <div className="rounded-xl p-4 border" style={PANEL}>
        <div className="flex items-center gap-2 mb-3">
          <Boxes className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">الأصناف</span>
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-[11px] text-slate-400 border-b" style={{ borderColor: '#334155' }}>
                  <th className="py-2 px-2 font-medium">الفئة</th>
                  <th className="py-2 px-2 font-medium">الاسم</th>
                  <th className="py-2 px-2 font-medium">الكميّة</th>
                  <th className="py-2 px-2 font-medium">الوحدة</th>
                  {mayMutate && <th className="py-2 px-2 font-medium">إجراء</th>}
                </tr>
              </thead>
              <tbody>
                {items.map(it => (
                  <Fragment key={it.item_id}>
                    <tr className="border-b last:border-0" style={{ borderColor: '#1e293b' }}>
                      <td className="py-2 px-2 text-slate-400">{it.category}</td>
                      <td className="py-2 px-2">
                        <span className="text-slate-200">{it.name}</span>
                        {it.low_stock && (
                          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full mr-2"
                            style={{ background: '#2a0a0a', color: '#f87171', border: '1px solid #dc262644' }}>
                            <AlertTriangle className="w-2.5 h-2.5" /> مخزون منخفض
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-slate-300">{it.total_quantity.toLocaleString('en-US')}</td>
                      <td className="py-2 px-2 text-slate-400">{it.unit ?? '—'}</td>
                      {mayMutate && (
                        <td className="py-2 px-2">
                          <button onClick={() => setBatchFor(batchFor === it.item_id ? null : it.item_id)}
                            className="inline-flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300">
                            <PackagePlus className="w-3.5 h-3.5" /> إضافة دفعة
                          </button>
                        </td>
                      )}
                    </tr>
                    {mayMutate && batchFor === it.item_id && (
                      <AddBatchForm item={it} onClose={() => setBatchFor(null)} />
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* الأصناف القاربة على الانتهاء */}
      <div className="rounded-xl p-4 border" style={PANEL}>
        <div className="flex items-center gap-2 mb-3">
          <CalendarClock className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-slate-200">قاربت على الانتهاء (خلال 30 يوماً)</span>
        </div>
        <ExpiringSection />
      </div>
    </div>
  );
}
