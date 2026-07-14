// ترميز CSV آمن مُشترَك — يجمع تهريب RFC-4180 مع **تحييد حقن الصيغ** (CSV/spreadsheet
// formula injection). خليّة تبدأ بـ`= + - @` (أو tab/CR) قد تُنفَّذ كصيغة عند فتح الملفّ
// في Excel/LibreOffice؛ نُسبِّقها بفاصلة عليا فتُعامَل كنصّ. مصدر واحد لكلّ مسارات التصدير
// (التقارير + مساحة SQL) — F-UI-38 / continuation-3.

// محارف تُطلِق تقييم الصيغة في الجداول الحسابيّة إن بدأت بها الخليّة.
const FORMULA_TRIGGERS = new Set(['=', '+', '-', '@', '\t', '\r']);

/**
 * يُرمّز قيمة كخليّة CSV آمنة:
 *  1) تحييد الصيغ: تُسبَّق الخليّة المبدوءة بمُطلِق صيغة بفاصلة عليا (`'`).
 *  2) تهريب RFC-4180: تُقتبَس عند احتوائها فاصلة/سطر/اقتباس، وتُضاعَف الاقتباسات الداخليّة.
 */
export function csvCell(v: unknown): string {
  let s = v === null || v === undefined ? '' : String(v);
  if (s.length > 0 && FORMULA_TRIGGERS.has(s[0])) {
    s = `'${s}`;
  }
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** يبني سطر CSV من قيَم عبر {@link csvCell}. */
export function csvRow(values: unknown[]): string {
  return values.map(csvCell).join(',');
}
