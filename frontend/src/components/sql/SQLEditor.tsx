// SQLEditor — محرّر SQL في المتصفّح فوق DuckDB-WASM (lazy). يحمّل حقول المستأجر إلى جدول `fields`
// وينفّذ استعلامات المستخدم محليّاً. عميل-فقط، آمن (نسخة في الذاكرة لا تمسّ الخلفيّة).
// الأخطاء تُعرَض بصدق؛ النطاق معلَن (سمات الحقول فقط — لا مؤشّرات/ST_* في v1).
import { useMemo, useState } from 'react';
import { useFieldOptions } from '../../hooks/useFieldOptions';
import { useDuckDBFields } from '../../hooks/useDuckDB';
import type { FieldRow, QueryResult } from '../../services/duckdb';
import { DataTable, type Column } from '../ds/table';
import { LoadingState, ErrorState, EmptyState } from '../StateViews';
import { T } from '../ds/tokens';

const DEFAULT_SQL = `SELECT crop, count(*) AS n, round(sum(area_ha), 1) AS ha
FROM fields
GROUP BY crop
ORDER BY ha DESC`;

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  return String(v);
}

/** يحوّل النتيجة إلى CSV مع تهريب صحيح (اقتباس عند فاصلة/سطر/علامة). */
function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const esc = (v: unknown): string => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const head = columns.map(esc).join(',');
  const body = rows.map((r) => columns.map((c) => esc(r[c])).join(',')).join('\r\n');
  return `${head}\r\n${body}`;
}

/** ينزّل النتيجة كملفّ CSV (BOM لدعم العربيّة في Excel). تنزيل المتصفّح — لا خادم. */
function downloadCsv(columns: string[], rows: Record<string, unknown>[]): void {
  const blob = new Blob(['﻿' + toCsv(columns, rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sahool-query-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function SQLEditor() {
  const { options, isLoading, isError, refetch } = useFieldOptions();

  const rows = useMemo<FieldRow[] | null>(
    () =>
      isLoading || isError
        ? null
        : options.map((o) => ({
            id: o.id,
            name: o.name,
            crop: o.crop,
            area_ha: o.area,
            lat: o.lat,
            lon: o.lon,
          })),
    [options, isLoading, isError],
  );

  const { ready, error: dbError, runQuery } = useDuckDBFields(rows);

  const [sql, setSql] = useState(DEFAULT_SQL);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    setQueryError(null);
    try {
      setResult(await runQuery(sql));
    } catch (e) {
      setQueryError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  if (isLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (isError) return <ErrorState title="تعذّر تحميل الحقول" onRetry={refetch} />;
  if (dbError) return <ErrorState title="تعذّر تهيئة محرّك SQL" detail={dbError} />;

  const columns: Column<Record<string, unknown>>[] = result
    ? result.columns.map((c) => ({
        key: c,
        label: c,
        sortable: true,
        render: (row) => formatCell(row[c]),
      }))
    : [];

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs leading-relaxed" style={{ color: T.muted }}>
        الجدول المتاح: <code style={{ color: T.ink }}>fields</code> (الأعمدة:
        {' '}<code>id, name, crop, area_ha, lat, lon</code>) — {options.length} حقل.
        <br />
        بيانات الحقول الحاليّة فقط؛ المؤشّرات (NDVI) والاستعلام المكانيّ (<code>ST_*</code>) قادمة لاحقاً.
      </div>

      <textarea
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        dir="ltr"
        spellCheck={false}
        rows={5}
        aria-label="محرّر SQL"
        className="w-full rounded-lg p-3 font-mono text-sm"
        style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}`, resize: 'vertical' }}
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={run}
          disabled={!ready || running}
          className="px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
          style={{ background: T.green }}
        >
          {running ? 'جارٍ التشغيل…' : !ready ? 'جارٍ التهيئة…' : '▶ تشغيل'}
        </button>
        {result && (
          <span className="text-xs" style={{ color: T.muted }}>{result.rows.length} صفّ</span>
        )}
        {result && result.rows.length > 0 && (
          <button
            type="button"
            onClick={() => downloadCsv(result.columns, result.rows)}
            className="px-3 py-2 rounded-lg text-sm font-semibold"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            ⬇ تصدير CSV
          </button>
        )}
      </div>

      {queryError && <ErrorState title="خطأ في الاستعلام" detail={queryError} />}

      {result &&
        (result.rows.length > 0 ? (
          <DataTable
            columns={columns}
            rows={result.rows}
            rowKey={(_row, i) => String(i)}
          />
        ) : (
          <EmptyState title="لا نتائج" hint="نفّذ استعلاماً يُعيد صفوفاً." />
        ))}
    </div>
  );
}
