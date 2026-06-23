// SAHOOL — services/duckdb.ts
// محرّك DuckDB-WASM في المتصفّح (عميل-فقط، مستضاف ذاتيّاً — لا CDN، يعمل أوفلاين). يُهيَّأ كسولاً
// مرّةً واحدة، وتُحمَّل صفوف الحقول إلى جدول `fields` للاستعلام بـSQL. (اقتباس GeoLibre — الفكرة 2.)
// آمن بحكم البنية: نسخة في الذاكرة (ephemeral) فوق قائمة الحقول؛ أيّ تعديل لا يمسّ الخلفيّة.
import * as duckdb from '@duckdb/duckdb-wasm';
// حُزَم WASM/worker مستضافة ذاتيّاً عبر Vite (?url ⇒ أصل مُجمَّع محليّاً، لا شبكة وقت التشغيل).
import mvpWasm from '@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url';
import mvpWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url';
import ehWasm from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import ehWorker from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';

const BUNDLES: duckdb.DuckDBBundles = {
  mvp: { mainModule: mvpWasm, mainWorker: mvpWorker },
  eh: { mainModule: ehWasm, mainWorker: ehWorker },
};

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null;

/** يُهيّئ مثيل DuckDB مرّةً واحدة (كسول، مُتشارَك عبر الجلسة). فشل التهيئة يُعيد المحاولة لاحقاً. */
export async function getDuckDB(): Promise<duckdb.AsyncDuckDB> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const bundle = await duckdb.selectBundle(BUNDLES);
      const worker = new Worker(bundle.mainWorker!);
      const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker);
      await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
      return db;
    })().catch((e) => {
      dbPromise = null; // اسمح بإعادة المحاولة عند الفشل
      throw e;
    });
  }
  return dbPromise;
}

/** صفّ جدول `fields` (أعمدة v1 — سمات متاحة عميل-فقط؛ المؤشّرات async ⇒ خارج النطاق). */
export interface FieldRow {
  id: string;
  name: string;
  crop: string;
  area_ha: number;
  lat: number | null;
  lon: number | null;
}

/** (يستبدل) يُنشئ جدول `fields` بمخطّط صريح ويحمّل الصفوف. مخطّط ثابت ⇒ sum/avg تعمل ولو 0 صفّ. */
export async function loadFields(rows: FieldRow[]): Promise<void> {
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    await conn.query(
      'CREATE OR REPLACE TABLE fields (id VARCHAR, name VARCHAR, crop VARCHAR, area_ha DOUBLE, lat DOUBLE, lon DOUBLE)',
    );
    if (rows.length > 0) {
      await db.dropFile('fields.json').catch(() => undefined); // تجاهُل إن لم يكن مُسجّلاً
      await db.registerFileText('fields.json', JSON.stringify(rows));
      await conn.insertJSONFromPath('fields.json', { name: 'fields', create: false });
    }
  } finally {
    await conn.close();
  }
}

/** نتيجة استعلام جاهزة للعرض في DataTable. */
export interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
}

/**
 * يصدّر نتيجة استعلام كـ**Parquet** (تنسيق أعمدة) عبر قدرة DuckDB-WASM على الكتابة:
 * `COPY (<sql>) TO 'result.parquet' (FORMAT PARQUET)` يكتب الملفّ في نظام ملفّات DuckDB
 * الافتراضيّ (في الذاكرة)، ثمّ نقرأه إلى `Uint8Array` عبر `db.copyFileToBuffer` ونحذفه.
 * يرمي عند خطأ SQL (يُعرَض بصدق). عميل-فقط — لا خادم.
 *
 * صدق التسمية: هذا **Parquet عاديّ** (سمات id/name/crop/area_ha/lat/lon فقط، لا هندسة).
 * TODO(GeoParquet): لإصدار GeoParquet حقيقيّ يلزم ترميز الهندسة WKB + بيانات وصفيّة
 *   geo؛ جدول `fields` لا يحمل هندسة في v1، فلا نُسمّيه GeoParquet زوراً.
 */
export async function exportQueryToParquet(sql: string): Promise<Uint8Array> {
  const db = await getDuckDB();
  const conn = await db.connect();
  const FILE = 'result.parquet';
  try {
    await db.dropFile(FILE).catch(() => undefined); // تنظيف بقايا تصدير سابق إن وُجدت
    // COPY يلفّ الاستعلام كاستعلام فرعيّ؛ أيّ خطأ SQL يُرمى هنا بصدق (لا ابتلاع).
    await conn.query(`COPY (${sql}) TO '${FILE}' (FORMAT PARQUET)`);
    return await db.copyFileToBuffer(FILE);
  } finally {
    await conn.close();
    await db.dropFile(FILE).catch(() => undefined); // لا نُبقي الملفّ في FS بعد القراءة
  }
}

/** ينفّذ استعلاماً ويعيد {columns, rows}. يرمي عند خطأ SQL (يُعرَض بصدق، لا ابتلاع). */
export async function runQuery(sql: string): Promise<QueryResult> {
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    const table = await conn.query(sql);
    const columns = table.schema.fields.map((f) => f.name);
    const arr = table.toArray() as Array<Record<string, unknown>>;
    const rows = arr.map((row) => {
      const o: Record<string, unknown> = {};
      for (const c of columns) {
        const v = row[c];
        // BigInt (نواتج count/sum) → Number للعرض والفرز في DataTable.
        o[c] = typeof v === 'bigint' ? Number(v) : v;
      }
      return o;
    });
    return { columns, rows };
  } finally {
    await conn.close();
  }
}
