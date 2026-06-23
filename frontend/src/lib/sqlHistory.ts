// SAHOOL — lib/sqlHistory.ts
// سجلّ استعلامات SQL محليّ (ورشة SQL في المتصفّح فوق DuckDB-WASM). يحفظ آخر ~10
// استعلامات نُفّذت بنجاح وتختلف عن بعضها، في localStorage — عميل-فقط بلا خادم.
// best-effort: أيّ تعذّر/فساد تخزين ⇒ سجلّ فارغ (لا يكسر الورشة). يبني على نمط
// workspaceStorage.ts (try/catch صامت).

const KEY = 'sahool-sql-history-v1';
const CAP = 10;

/** يقرأ السجلّ المحفوظ (الأحدث أوّلاً). تعذّر/فساد/ليس مصفوفة نصوص ⇒ []. */
export function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const data = JSON.parse(raw) as unknown;
    if (!Array.isArray(data)) return [];
    return data.filter((x): x is string => typeof x === 'string').slice(0, CAP);
  } catch {
    return [];
  }
}

/**
 * يضيف استعلاماً إلى مقدّمة السجلّ (الأحدث أوّلاً)، مزيلاً التكرار (المطابق يُنقل
 * للمقدّمة) ومحدّداً السقف بـ10. يتجاهل الاستعلام الفارغ. يُعيد السجلّ الجديد
 * ويحفظه best-effort (تجاهُل أيّ تعذّر تخزين).
 */
export function pushHistory(sql: string): string[] {
  const trimmed = sql.trim();
  const current = loadHistory();
  if (!trimmed) return current;
  const next = [trimmed, ...current.filter((q) => q !== trimmed)].slice(0, CAP);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* تجاهُل — التخزين غير متاح (وضع خاصّ/ممتلئ) لا يؤثّر على الجلسة */
  }
  return next;
}
