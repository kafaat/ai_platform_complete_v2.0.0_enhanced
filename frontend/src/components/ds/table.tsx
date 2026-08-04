// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · جدول البيانات (DataTable)
// ───────────────────────────────────────────────────────────────
// جدول عامّ مكتوب الأنواع DataTable<T>: أعمدة قابلة للضبط (render/sortable)،
// فرز عميل، رأس لاصق، وانهيار للموبايل (تكدّس الصفوف كبطاقات تحت نقطة الكسر).
// حالة فراغ مدمجة. واعٍ RTL (الخصائص المنطقيّة + textAlign:start). الألوان من
// tokens.ts. لا بيانات وهميّة: يعرض ما يُمرَّر فقط؛ القيمة الغائبة «—».
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronUp, ChevronDown, Inbox } from 'lucide-react';
import { T, RADIUS } from './tokens';

export interface Column<T> {
  key: keyof T & string;
  label: ReactNode;
  // عرض مخصّص للخليّة (مثل وسم/زرّ)؛ افتراضيّاً يُعرَض النصّ الخام أو «—».
  render?: (row: T, index: number) => ReactNode;
  sortable?: boolean;
  // محاذاة الخليّة منطقيّاً (start/end/center) — RTL واعٍ.
  align?: 'start' | 'end' | 'center';
  width?: number | string;
}

type SortState<T> = { key: keyof T & string; dir: 'asc' | 'desc' } | null;

function defaultCompare(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'ar');
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  rowKey,
  onRowClick,
  emptyTitle = 'لا توجد بيانات',
  emptyHint,
  emptyIcon,
  // نقطة كسر الموبايل (px): تحتها تتكدّس الصفوف كبطاقات.
  mobileBreakpoint = 640,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  emptyTitle?: string;
  emptyHint?: string;
  emptyIcon?: ReactNode;
  mobileBreakpoint?: number;
}) {
  const [sort, setSort] = useState<SortState<T>>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    // فرز مستقرّ على نسخة (لا يُحوّر مدخل المستدعي).
    const copy = [...rows];
    copy.sort((ra, rb) => {
      const cmp = defaultCompare(ra[sort.key], rb[sort.key]);
      return sort.dir === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort, columns]);

  function toggleSort(key: keyof T & string) {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: 'asc' };
      if (prev.dir === 'asc') return { key, dir: 'desc' };
      return null; // الدورة: asc → desc → بلا فرز
    });
  }

  // معرّف فريد لحقن CSS الاستجابة (انهيار الموبايل) لهذا الجدول فقط.
  //
  // موضعه **قبل** الخروج المبكر للحالة الفارغة عن قصد: كان تحته، فيُستدعى عند وجود
  // صفوف ولا يُستدعى عند غيابها. اختلاف عدد الـhooks بين تصييرَين يرمي
  // «Rendered more hooks than during the previous render» لحظة امتلاء جدول كان
  // فارغاً — وهو المسار الشائع (جدول يُحمَّل ثمّ تصل بياناته).
  const tid = useMemo(() => `dt-${Math.random().toString(36).slice(2, 9)}`, []);

  if (rows.length === 0) {
    return (
      <div
        role="status"
        style={{
          textAlign: 'center',
          padding: '40px 16px',
          color: T.muted,
          background: T.card,
          border: `1px solid ${T.line}`,
          borderRadius: RADIUS.md,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }} aria-hidden="true">
          {emptyIcon ?? <Inbox style={{ width: 32, height: 32 }} />}
        </div>
        <p style={{ fontSize: 14, fontWeight: 600, color: T.ink }}>{emptyTitle}</p>
        {emptyHint && <p style={{ fontSize: 12, marginTop: 4 }}>{emptyHint}</p>}
      </div>
    );
  }

  function cellContent(col: Column<T>, row: T, i: number): ReactNode {
    if (col.render) return col.render(row, i);
    const v = row[col.key];
    if (v == null || v === '') return '—';
    return v as ReactNode;
  }

  return (
    <div
      style={{
        overflowX: 'auto',
        border: `1px solid ${T.line}`,
        borderRadius: RADIUS.md,
        background: T.card,
      }}
    >
      {/* انهيار الموبايل: تحت نقطة الكسر يُخفى الرأس وتُكدَّس الخلايا عموديّاً مع
          إظهار تسمية العمود (data-label) أمام كلّ قيمة. */}
      <style>{`
        @media (max-width: ${mobileBreakpoint}px) {
          .${tid} thead { display: none; }
          .${tid} tr { display: block; border-bottom: 1px solid ${T.line}; padding: 8px 0; }
          .${tid} td { display: flex; justify-content: space-between; gap: 12px; border: none !important; padding: 6px 12px; }
          .${tid} td::before { content: attr(data-label); font-weight: 700; color: ${T.muted}; font-size: 12px; }
        }
      `}</style>
      <table className={tid} style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((col) => {
              const active = sort?.key === col.key;
              const align = col.align ?? 'start';
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={active ? (sort?.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                  style={{
                    position: 'sticky',
                    top: 0,
                    zIndex: 1,
                    background: T.card2,
                    color: T.brownSoft,
                    fontWeight: 700,
                    textAlign: align,
                    padding: '10px 12px',
                    borderBottom: `1px solid ${T.line}`,
                    whiteSpace: 'nowrap',
                    width: col.width,
                  }}
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        color: 'inherit',
                        font: 'inherit',
                        fontWeight: 700,
                        padding: 0,
                      }}
                    >
                      {col.label}
                      {active ? (
                        sort?.dir === 'asc' ? (
                          <ChevronUp style={{ width: 14, height: 14 }} aria-hidden="true" />
                        ) : (
                          <ChevronDown style={{ width: 14, height: 14 }} aria-hidden="true" />
                        )
                      ) : (
                        <ChevronUp style={{ width: 14, height: 14, opacity: 0.3 }} aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={rowKey(row, i)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              style={{ cursor: onRowClick ? 'pointer' : undefined }}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  data-label={typeof col.label === 'string' ? col.label : undefined}
                  style={{
                    padding: '10px 12px',
                    borderBottom: `1px solid ${T.line}`,
                    color: T.ink,
                    textAlign: col.align ?? 'start',
                  }}
                >
                  {cellContent(col, row, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
