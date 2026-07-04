// FieldView Layer Compare presets — يجعل وضع المقارنة القائم (يسار/يمين) أكثر فائدة
// بتقديم مقارنات ذات معنى زراعيّ بنقرة واحدة بدل اختيار طبقتين يدويّاً. لا يبني محرّك
// مقارنة جديداً — يوجّه المحرّك القائم (setLeftLayer/setRightLayer). صدق: تُعرَض فقط
// المقارنات التي تتوفّر طبقاتها في كتالوج المؤشّرات الفعليّ.
export interface LayerComparePreset {
  id: string;
  label: string;
  left: string;
  right: string;
  /** لماذا هذه المقارنة مفيدة زراعيّاً. */
  why: string;
}

const CANDIDATES: LayerComparePreset[] = [
  { id: 'cover-moisture', label: 'الغطاء ↔ الرطوبة', left: 'ndvi', right: 'ndmi', why: 'صحّة الغطاء مقابل رطوبة المجموع — يكشف الإجهاد المائيّ تحت غطاء أخضر.' },
  { id: 'cover-salinity', label: 'الغطاء ↔ الملوحة', left: 'ndvi', right: 'salinity', why: 'مناطق ضعف الغطاء التي تتوافق مع ارتفاع الملوحة.' },
  { id: 'moisture-water', label: 'الرطوبة ↔ الماء', left: 'ndmi', right: 'ndwi', why: 'رطوبة المجموع النباتيّ مقابل الماء السطحيّ/التجمّعات.' },
  { id: 'cover-stress', label: 'الغطاء ↔ الإجهاد', left: 'ndvi', right: 'msi', why: 'الغطاء مقابل مؤشّر الإجهاد المائيّ (MSI).' },
  { id: 'image-cover', label: 'الصورة ↔ الغطاء', left: 'truecolor', right: 'ndvi', why: 'الصورة الخام مقابل مؤشّر الغطاء لتفسير بصريّ.' },
];

/** يُرجِع المقارنات التي تتوفّر كلتا طبقتيها في الكتالوج الفعليّ. */
export function buildComparePresets(availableLayerIds: ReadonlyArray<string>): LayerComparePreset[] {
  const set = new Set(availableLayerIds);
  return CANDIDATES.filter((p) => set.has(p.left) && set.has(p.right));
}
