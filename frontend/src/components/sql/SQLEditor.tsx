// SQLEditor — محرّر SQL في المتصفّح فوق DuckDB-WASM (lazy). يحمّل حقول المستأجر إلى جدول `fields`
// وينفّذ استعلامات المستخدم محليّاً. عميل-فقط، آمن (نسخة في الذاكرة لا تمسّ الخلفيّة).
// الأخطاء تُعرَض بصدق؛ النطاق معلَن (سمات الحقول فقط — لا مؤشّرات/ST_* في v1).
import { useMemo, useState } from 'react';
import { useSelectedField } from '../../hooks/useSelectedField';
import { useDuckDBFields } from '../../hooks/useDuckDB';
import type { FieldRow, QueryResult } from '../../services/duckdb';
import { csvRow } from '../../lib/csv';
import { exportQueryToParquet } from '../../services/duckdb';
import { DataTable, type Column } from '../ds/table';
import { LoadingState, ErrorState, EmptyState } from '../StateViews';
import { T } from '../ds/tokens';
import { loadHistory, pushHistory } from '../../lib/sqlHistory';
import { toastStore } from '../../services/websocket';
import { generateSqlFromNl } from '../../services/api';

const DEFAULT_SQL = `SELECT crop, count(*) AS n, round(sum(area_ha), 1) AS ha
FROM fields
GROUP BY crop
ORDER BY ha DESC`;

// استعلامات أمثلة جاهزة (عميل-فقط، تُحمَّل في المحرّر عند النقر).
const EXAMPLE_QUERIES: { label: string; sql: string }[] = [
  {
    label: 'عدد الحقول حسب المحصول',
    sql: 'SELECT crop, count(*) AS n FROM fields GROUP BY crop ORDER BY n DESC',
  },
  {
    label: 'أكبر ٥ حقول مساحةً',
    sql: 'SELECT id, name, area_ha FROM fields ORDER BY area_ha DESC LIMIT 5',
  },
  {
    label: 'متوسّط المساحة',
    sql: 'SELECT round(avg(area_ha), 2) AS avg_ha FROM fields',
  },
];

/** وسم قابل للنقر (شريحة) — أمثلة/سجلّ. يحمّل نصّاً في المحرّر. */
function Chip({ label, title, onClick }: { label: string; title?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      dir="auto"
      className="px-2.5 py-1 rounded-lg text-xs font-mono max-w-[18rem] truncate"
      style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
    >
      {label}
    </button>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  return String(v);
}

/** يحوّل النتيجة إلى CSV عبر المُرمّز الآمن المُشترَك (تهريب RFC-4180 + تحييد حقن الصيغ، F-UI-38). */
function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const head = csvRow(columns);
  const body = rows.map((r) => csvRow(columns.map((c) => r[c]))).join('\r\n');
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

/** ينزّل مخزّن Parquet (Uint8Array من DuckDB) كملفّ .parquet — نفس نمط تنزيل CSV (Blob/URL). */
function downloadParquet(bytes: Uint8Array): void {
  // ننسخ إلى ArrayBuffer صريح (لا ArrayBufferLike/SharedArrayBuffer) — مخزّن DuckDB
  // (Uint8Array<ArrayBufferLike> تحت TS الصارم) ليس BlobPart صالحاً مباشرةً. النسخ يضمن
  // الطول الفعليّ بالضبط (لا أصفار ذيليّة) ونوعاً صالحاً للـBlob.
  const ab = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(ab).set(bytes);
  const blob = new Blob([ab], { type: 'application/vnd.apache.parquet' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sahool-query-${new Date().toISOString().slice(0, 10)}.parquet`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function SQLEditor() {
  const { options, fieldId: activeFieldId, setFieldId, isLoading, isError, refetch } = useSelectedField();

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
  const [history, setHistory] = useState<string[]>(() => loadHistory());
  const [exportingParquet, setExportingParquet] = useState(false);

  // مساعد الذكاء (NL→SQL): سؤال عربيّ → الخادم يستدعي Claude → يملأ المحرّر للمراجعة.
  const [nlQuestion, setNlQuestion] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlError, setNlError] = useState<string | null>(null);
  const [nlGenerated, setNlGenerated] = useState(false);

  /** يولّد SQL من سؤال عربيّ عبر الخادم — يملأ المحرّر فقط (لا تشغيل تلقائيّ). أخطاء صادقة. */
  async function generateFromNl() {
    const q = nlQuestion.trim();
    if (!q) return;
    setNlLoading(true);
    setNlError(null);
    setNlGenerated(false);
    try {
      const r = await generateSqlFromNl(q);
      setSql(r.sql);
      setNlGenerated(true);
    } catch (e) {
      const ax = e as { response?: { status?: number; data?: { detail?: string } } };
      const status = ax.response?.status;
      const detail = ax.response?.data?.detail;
      setNlError(
        status === 404 ? 'المساعد الذكيّ غير مُفعَّل'
          : status === 503 ? (detail || 'المساعد غير مُهيّأ (مفتاح مفقود)')
          : status === 429 ? 'طلبات كثيرة — حاول بعد قليل'
          : detail || 'تعذّر توليد الاستعلام',
      );
    } finally {
      setNlLoading(false);
    }
  }

  async function run() {
    setRunning(true);
    setQueryError(null);
    try {
      const r = await runQuery(sql);
      setResult(r);
      setHistory(pushHistory(sql)); // سجلّ الاستعلامات الناجحة فقط (عميل-فقط)
    } catch (e) {
      setQueryError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  /** ينسخ صفوف النتيجة كـJSON إلى الحافظة (best-effort؛ توست عند النجاح/التعذّر). */
  async function copyJson() {
    if (!result) return;
    const text = JSON.stringify(result.rows);
    try {
      if (!navigator.clipboard?.writeText) {
        toastStore.add('warning', 'النسخ غير متاح', 'الحافظة غير مدعومة في هذا المتصفّح');
        return;
      }
      await navigator.clipboard.writeText(text);
      toastStore.add('success', 'تمّ النسخ', `نُسخت ${result.rows.length} صفّ كـJSON`);
    } catch {
      toastStore.add('error', 'تعذّر النسخ', 'لم يُسمح بالوصول إلى الحافظة');
    }
  }

  /**
   * يصدّر نتيجة الاستعلام الحاليّ كـ**Parquet** (تنسيق أعمدة) عبر DuckDB ثمّ ينزّله.
   * يُعيد تشغيل نفس الاستعلام داخل COPY (DuckDB يكتب من الاستعلام مباشرةً، لا من صفوف JS).
   * أخطاء صادقة عبر توست (لا ابتلاع). الاسم «Parquet» لا «GeoParquet» (لا هندسة في v1).
   */
  async function exportParquet() {
    if (!result) return;
    setExportingParquet(true);
    try {
      const bytes = await exportQueryToParquet(sql);
      downloadParquet(bytes);
      toastStore.add('success', 'تمّ التصدير', 'نُزّلت النتيجة كملفّ Parquet');
    } catch (e) {
      toastStore.add('error', 'تعذّر التصدير', e instanceof Error ? e.message : String(e));
    } finally {
      setExportingParquet(false);
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

      {/* مساعد الذكاء: سؤال عربيّ → SQL (خادميّ؛ يملأ المحرّر للمراجعة قبل التشغيل) */}
      <div className="flex flex-col gap-1.5">
        <span className="text-xs" style={{ color: T.muted }}>
          اسأل بالعربيّة (تجريبيّ) — يولّد SQL تراجعه قبل التشغيل:
        </span>
        <div className="flex items-center gap-1.5 flex-wrap">
          <input
            type="text"
            value={nlQuestion}
            onChange={(e) => setNlQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') generateFromNl(); }}
            placeholder="مثال: حقول القمح التي مساحتها أكبر من 50 هكتاراً"
            aria-label="سؤال باللغة الطبيعيّة"
            className="flex-1 min-w-[14rem] rounded-lg px-3 py-2 text-sm"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          />
          <button
            type="button"
            onClick={generateFromNl}
            disabled={nlLoading || !nlQuestion.trim()}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
            style={{ background: T.green }}
          >
            {nlLoading ? 'جارٍ التوليد…' : '✨ ولّد SQL'}
          </button>
        </div>
        {nlGenerated && (
          <span className="text-xs" style={{ color: T.muted }}>مُولَّد بالذكاء — راجِعه ثمّ اضغط «تشغيل».</span>
        )}
        {nlError && <span className="text-xs" style={{ color: '#f87171' }}>{nlError}</span>}
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-xs" style={{ color: T.muted }}>أمثلة جاهزة:</span>
        <div className="flex flex-wrap items-center gap-1.5">
          {EXAMPLE_QUERIES.map((ex) => (
            <Chip key={ex.label} label={ex.label} title={ex.sql} onClick={() => setSql(ex.sql)} />
          ))}
        </div>
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

      {history.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs" style={{ color: T.muted }}>سجلّ الاستعلامات (محليّ):</span>
          <div className="flex flex-wrap items-center gap-1.5">
            {history.map((q, i) => (
              <Chip key={`${i}-${q}`} label={q} title={q} onClick={() => setSql(q)} />
            ))}
          </div>
        </div>
      )}

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
            className="px-3 py-2 rounded-lg text-xs font-semibold"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            ⬇ تصدير CSV
          </button>
        )}
        {result && result.rows.length > 0 && (
          <button
            type="button"
            onClick={exportParquet}
            disabled={exportingParquet}
            title="تصدير النتيجة كملفّ Parquet (تنسيق أعمدة) عبر DuckDB"
            className="px-3 py-2 rounded-lg text-xs font-semibold disabled:opacity-50"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            {exportingParquet ? 'جارٍ التصدير…' : '⬇ تصدير Parquet'}
          </button>
        )}
        {result && result.rows.length > 0 && (
          <button
            type="button"
            onClick={copyJson}
            className="px-3 py-2 rounded-lg text-xs font-semibold"
            style={{ background: T.card2, color: T.ink, border: `1px solid ${T.line}` }}
          >
            نسخ JSON
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
