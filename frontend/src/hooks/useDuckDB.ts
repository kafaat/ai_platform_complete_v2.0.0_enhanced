// useDuckDB — يحمّل صفوف الحقول إلى جدول `fields` في DuckDB-WASM (كسولاً) ويكشف حالة الجاهزيّة.
// يعيد runQuery للتنفيذ. مغلَّف لعزل دورة حياة المحرّك عن مكوّن العرض.
import { useEffect, useState } from 'react';
import { loadFields, runQuery, type FieldRow } from '../services/duckdb';

export function useDuckDBFields(rows: FieldRow[] | null) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!rows) return;
    let cancelled = false;
    setReady(false);
    setError(null);
    loadFields(rows)
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [rows]);

  return { ready, error, runQuery };
}
