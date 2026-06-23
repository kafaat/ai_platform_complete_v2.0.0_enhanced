// SQLWorkspacePage — ورشة SQL / استوديو البيانات (اقتباس GeoLibre — الفكرة 2).
// يغلّف محرّر SQL الكسول (DuckDB-WASM ~2.5MB يُحمَّل عند فتح القسم فقط — صفر أثر على الحزمة الرئيسة).
import { Suspense, lazy } from 'react';
import { Database } from 'lucide-react';
import { LoadingState } from '../components/StateViews';
import { T } from '../components/ds/tokens';

const SQLEditor = lazy(() => import('../components/sql/SQLEditor'));

export default function SQLWorkspacePage() {
  return (
    <div className="p-4 flex flex-col gap-3" dir="rtl">
      <header className="flex items-center gap-2 flex-wrap">
        <Database className="w-5 h-5 text-emerald-400" aria-hidden="true" />
        <h1 className="text-lg font-bold" style={{ color: T.ink }}>ورشة SQL — استوديو البيانات</h1>
        <span
          className="text-[11px] px-2 py-0.5 rounded"
          style={{ background: T.card2, color: T.muted, border: `1px solid ${T.line}` }}
        >
          DuckDB-WASM · ألفا
        </span>
      </header>
      <p className="text-xs leading-relaxed" style={{ color: T.muted }}>
        استعلِم بيانات حقولك بـSQL داخل المتصفّح — عميل-فقط، لا تُرسَل بياناتك إلى أيّ خادم (خصوصيّة أعلى،
        حمل أقلّ على الـAPI).
      </p>
      <Suspense fallback={<LoadingState message="جارٍ تحميل محرّك SQL (DuckDB-WASM)…" />}>
        <SQLEditor />
      </Suspense>
    </div>
  );
}
