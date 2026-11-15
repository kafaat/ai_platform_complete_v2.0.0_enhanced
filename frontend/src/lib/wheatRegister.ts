import type { Sheet } from 'read-excel-file/browser';

export const wheatCultivars = ['علس', 'حبيب', 'بوني', 'حميري', 'سمراء'];
export type WheatReference = {
  sheet: string; variety: string; hectares: number; seedKg: number; rainfed: boolean; day: string;
};

// تطبيع الكتابة العربيّة: التشكيل والتطويل، والألف المقصورة في آخر الكلمة («حميرى» = «حميري»).
function normalizeArabic(value: unknown) {
  return String(value ?? '').replace(/[ً-ْـ]/g, '').replace(/ى(?=\s|$)/g, 'ي').trim();
}

function cultivar(value: unknown) {
  const name = normalizeArabic(value).replace(/\s+/g, ' ').replace(/^قمح\s+/, '').replace(/^ال/, '');
  return wheatCultivars.find(v => v === name);
}

// خليّة رقميّة: رقم Excel، أو نصّ بأرقام عربيّة/هنديّة شرقيّة أو فارسيّة وفاصلة عشريّة «٫».
// فاصل الآلاف «٬» يُحذف، و«,» فقط في تجميع آلاف صريح (1,250) لا فاصلةً عشريّة (12,5 ⇒ null).
// أيّ نصّ آخر (وحدة ملتصقة، «-»، فارغ) ⇒ null: لا تخمين.
export function cellNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  let text = value.trim()
    .replace(/[٠-٩]/g, d => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, d => String(d.charCodeAt(0) - 0x06F0))
    .replace(/٬/g, '').replace(/٫/g, '.');
  if (/^\d{1,3}(,\d{3})+(\.\d+)?$/.test(text)) text = text.replace(/,/g, '');
  return /^\d+(\.\d+)?$/.test(text) ? Number(text) : null;
}

// وحدة المساحة من عنوان العمود: م² ⇒ ÷10000، هكتار ⇒ ×1، غيرها (دونم/لبنة/بلا وحدة) ⇒ 0 فلا مرجع.
function areaDivisor(header: string) {
  if (/متر\s*مربع|م\s*[²2]/.test(header)) return 10000;
  if (/هكتار/.test(header)) return 1;
  return 0;
}

// وحدة كمية البذار من عنوان العمود: كغ افتراضاً، طن ×1000، غرام ÷1000، وكيس/شوال مجهول الوزن ⇒ 0.
function seedFactor(header: string) {
  if (/كغ|كجم|كيلو|kg/i.test(header)) return 1;
  if (/طن/.test(header)) return 1000;
  if (/غرام|جرام/.test(header)) return 0.001;
  if (/كيس|شوال|أكياس/.test(header)) return 0;
  return 1;
}

// معدل البذار كغ/هكتار مقرَّباً إلى منزلتين (نصّ لحقل الإدخال).
export function seedRatePerHa(ref: Pick<WheatReference, 'seedKg' | 'hectares'>) {
  return (Math.round((ref.seedKg / ref.hectares) * 100) / 100).toFixed(2);
}

export function readWheatReferences(sheets: Sheet[]) {
  const refs: WheatReference[] = [];
  for (const { sheet, data } of sheets) {
    const header = data.findIndex(r => normalizeArabic(r[1]).includes('مساحة القطاع')
      && normalizeArabic(r[4]) === 'نوع البذور' && normalizeArabic(r[6]).includes('كمية البذور'));
    if (header < 0) continue;
    const divisor = areaDivisor(normalizeArabic(data[header][1]));
    const factor = seedFactor(normalizeArabic(data[header][6]));
    const rows = data.slice(header + 1);
    const areas = rows.map(r => r[1]).filter(v => v != null && String(v).trim() !== '');
    const lots = rows.filter(r => r[4] != null || r[6] != null || r[2] != null);
    const variety = cultivar(lots[0]?.[4]);
    const area = areas.length === 1 ? cellNumber(areas[0]) : null;
    const amounts = lots.map(r => cellNumber(r[6]));
    // ورقة مختلطة الأصناف، أو مساحتها مجهولة/متعدّدة، أو كمية ناقصة ⇒ لا معدل آليّ.
    if (!divisor || !factor || area == null || area <= 0 || !variety
      || !lots.every((r, i) => cultivar(r[4]) === variety && (amounts[i] ?? 0) > 0)) continue;
    const dates = lots.flatMap(r => r[2] instanceof Date ? [r[2].toISOString().slice(0, 10)] : []).sort();
    refs.push({ sheet: sheet.trim(), variety, hectares: area / divisor,
      seedKg: amounts.reduce<number>((sum, kg) => sum + (kg ?? 0), 0) * factor,
      rainfed: sheet.includes('الري المطري'), day: dates[0] ?? '' });
  }
  return refs;
}
