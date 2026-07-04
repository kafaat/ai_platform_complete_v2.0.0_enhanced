// FieldView Scouting Evidence — مستوحى من Taranis: يجلب سياق الاستكشاف داخل FieldView
// بدل صفحة منفصلة — «ماذا تفحص لهذا المحصول؟» من تصنيف الاستكشاف الحيّ (آفات/أمراض/
// أعشاب/نقص عناصر…)، مجمَّعاً حسب الفئة، ليبدأ المزارع جولة موجَّهة ثمّ يسجّل الدليل.
//
// صدق المصدر: القائمة من /api/v1/scouting/taxonomy الحيّة لمحصول الحقل. لا اختلاق —
// غياب المحصول أو القائمة يظهر كحالة صريحة.
export interface ScoutingIssueLite {
  code: string;
  category: string;
  name_ar: string;
}

export interface ScoutingCategoryGroup {
  category: string;
  label: string;
  items: ScoutingIssueLite[];
}

export interface ScoutingSummary {
  crop: string | null;
  hasCrop: boolean;
  total: number;
  groups: ScoutingCategoryGroup[];
}

const CATEGORY_LABEL: Record<string, string> = {
  disease: 'أمراض',
  pest: 'آفات',
  weed: 'أعشاب',
  nutrient: 'نقص عناصر',
  water_stress: 'إجهاد مائيّ',
  abiotic: 'عوامل لا حيويّة',
  other: 'أخرى',
};

// ترتيب الخطورة للعرض: الأمراض والآفات أوّلاً.
const CATEGORY_ORDER = ['disease', 'pest', 'weed', 'nutrient', 'water_stress', 'abiotic', 'other'];

export function summarizeScouting(crop: string | null | undefined, issues: ScoutingIssueLite[] = []): ScoutingSummary {
  const hasCrop = !!crop;
  const byCat = new Map<string, ScoutingIssueLite[]>();
  for (const issue of issues) {
    const key = issue.category || 'other';
    if (!byCat.has(key)) byCat.set(key, []);
    byCat.get(key)!.push(issue);
  }

  const groups: ScoutingCategoryGroup[] = [...byCat.entries()]
    .map(([category, items]) => ({ category, label: CATEGORY_LABEL[category] ?? category, items }))
    .sort((a, b) => {
      const ia = CATEGORY_ORDER.indexOf(a.category);
      const ib = CATEGORY_ORDER.indexOf(b.category);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });

  return { crop: crop ?? null, hasCrop, total: issues.length, groups };
}
