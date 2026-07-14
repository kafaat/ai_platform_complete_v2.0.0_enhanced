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

/**
 * يُنهي مثيل DuckDB المُتشارَك ويُصفّر المفرد — يُستدعى عند تبديل المستأجِر/الخروج كي
 * لا يبقى جدول `fields` لمستأجِرٍ سابق قابلاً للاستعلام/التصدير في الجلسة (F-UI-35/F5-05).
 * أفضل-جهد: أيّ فشل إنهاء لا يمنع التصفير (getDuckDB يُعيد الإنشاء عند الحاجة).
 */
export async function resetDuckDB(): Promise<void> {
  const pending = dbPromise;
  dbPromise = null;
  if (!pending) return;
  try {
    const db = await pending;
    await db.terminate();
  } catch {
    /* أفضل-جهد: المثيل صُفِّر أصلاً */
  }
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

/** سقف صفوف نتيجة الاستعلام — يمنع استنزاف الذاكرة/العرض بنتيجة ضخمة. */
export const MAX_RESULT_ROWS = 10_000;

// كلمات مفتاحيّة على مستوى البيان تُشير إلى تعديل/إدارة/تسريب — ممنوعة في مساحة SQL
// القرائيّة (F-UI-33). مطابقة بحدود الكلمة كي لا تُطابَق كأجزاء من معرّفات.
const FORBIDDEN_SQL = /\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|install|load|pragma|truncate|vacuum|grant|revoke)\b/i;

/**
 * يتحقّق أنّ `sql` استعلام **قراءة فقط** واحد (SELECT/WITH) بلا DDL/DML/COPY/ATTACH/…
 * ويعيد الاستعلام مُنظَّفاً من التعليقات والفاصلة الختاميّة. يرمي خطأً عربيّاً واضحاً عند
 * المخالفة. مصدر تحقّق واحد لكلّ مسارات التنفيذ (اليدويّ وNL-to-SQL) — F-UI-33/F-UI-34.
 */
export function assertReadOnlySelect(sql: string): string {
  const stripped = sql
    .replace(/--[^\n]*/g, ' ') // تعليقات السطر
    .replace(/\/\*[\s\S]*?\*\//g, ' ') // تعليقات الكتلة
    .trim();
  if (!stripped) throw new Error('استعلام فارغ.');
  const single = stripped.replace(/;\s*$/, '');
  if (single.includes(';')) {
    throw new Error('يُسمح ببيان واحد فقط (لا فواصل منقوطة متعدّدة).');
  }
  if (!/^\s*(select|with)\b/i.test(single)) {
    throw new Error('يُسمح باستعلام قراءة فقط يبدأ بـSELECT أو WITH.');
  }
  const bad = single.match(FORBIDDEN_SQL);
  if (bad) {
    throw new Error(`كلمة غير مسموح بها في استعلام القراءة: ${bad[0].toUpperCase()}`);
  }
  return single;
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
  const safe = assertReadOnlySelect(sql); // قراءة فقط + بيان واحد (F-UI-33)
  try {
    await db.dropFile(FILE).catch(() => undefined); // تنظيف بقايا تصدير سابق إن وُجدت
    // COPY (تُديرها المساحة لا المستخدم) يلفّ الاستعلام المُتحقَّق مع سقف صفوف؛ أيّ خطأ
    // SQL يُرمى هنا بصدق (لا ابتلاع).
    await conn.query(
      `COPY (SELECT * FROM (${safe}) AS _sahool_ro LIMIT ${MAX_RESULT_ROWS}) TO '${FILE}' (FORMAT PARQUET)`,
    );
    return await db.copyFileToBuffer(FILE);
  } finally {
    await conn.close();
    await db.dropFile(FILE).catch(() => undefined); // لا نُبقي الملفّ في FS بعد القراءة
  }
}

/** ينفّذ استعلاماً ويعيد {columns, rows}. يرمي عند خطأ SQL (يُعرَض بصدق، لا ابتلاع). */
export async function runQuery(sql: string): Promise<QueryResult> {
  const safe = assertReadOnlySelect(sql); // قراءة فقط + بيان واحد (F-UI-33/F-UI-34)
  const db = await getDuckDB();
  const conn = await db.connect();
  try {
    // لفّ الاستعلام المُتحقَّق بسقف صفوف صارم كي لا تُرجِع نتيجةٌ ضخمة تُجمِّد الواجهة.
    const table = await conn.query(`SELECT * FROM (${safe}) AS _sahool_ro LIMIT ${MAX_RESULT_ROWS}`);
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
