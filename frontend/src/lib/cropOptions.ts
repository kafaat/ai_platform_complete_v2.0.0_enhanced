// ═══════════════════════════════════════════════════════════════
// SAHOOL — lib/cropOptions.ts — مفردات المحاصيل الوحيدة لمنتقيات الويب
// ───────────────────────────────────────────────────────────────
// كلّ منتقي محصول في الواجهة (إضافة حقل · تعديل حقل · خطوة الموسم · إضافة موسم ·
// التوصية المتكاملة) يقرأ من هنا، ومرآته في الموبايل kEngineCrops
// (mobile/sahool_app/lib/features/advisor/presentation/recommendations_screen.dart).
//
// لكلّ خيار معرّف بطاقة محصول قانونيّ (`id` = crop_id في core/crop_cards) وتسمية
// عربيّة تُعرَض وتُرسَل كما كانت (field.crop يُعرَض خاماً في الواجهة). الخادم يحلّ
// التسمية عبر core.season_phenology.resolve_crop_id، واختبار الحارس
// tests_v9/unit/test_crop_picker_options_resolve.py يُثبت أنّ resolve_crop_id(label)
// يساوي `id` لكلّ خيار — فلا خيار يُعرَض بلا بطاقة محصول تُحلّ إليه.
//
// «خضروات» العامّة حُذفت: لا بطاقة لها، فكان اختيارها يحجب نصيحة العناصر دائماً
// (NUTRIENT_LEDGER_CROP_UNRESOLVED) بلا طريق للإصلاح من الواجهة. حلّت محلّها
// خضروات محدّدة لها بطاقات فعلاً.
// ═══════════════════════════════════════════════════════════════

export interface CropOption {
  /** crop_id لبطاقة محصول موجودة (core/crop_cards/<id>.yaml). */
  readonly id: string;
  /** التسمية العربيّة: تُعرَض وتُرسَل، وتُحلّ خادميّاً إلى `id`. */
  readonly label: string;
  readonly emoji: string;
}

export const CROP_OPTIONS: readonly CropOption[] = [
  { id: 'wheat', label: 'قمح صلب', emoji: '🌾' },
  { id: 'barley', label: 'شعير', emoji: '🌾' },
  { id: 'maize', label: 'ذرة صفراء', emoji: '🌽' },
  { id: 'sorghum', label: 'سورغم', emoji: '🌾' },
  { id: 'millet', label: 'دخن', emoji: '🌿' },
  { id: 'tomato', label: 'طماطم', emoji: '🍅' },
  { id: 'potato', label: 'بطاطس', emoji: '🥔' },
  { id: 'onion', label: 'بصل', emoji: '🧅' },
  { id: 'cucumber', label: 'خيار', emoji: '🥒' },
  { id: 'eggplant', label: 'باذنجان', emoji: '🍆' },
  { id: 'pepper', label: 'فلفل', emoji: '🌶' },
  { id: 'okra', label: 'بامية', emoji: '🥬' },
  { id: 'alfalfa', label: 'برسيم', emoji: '🌿' },
];

/** التسميات بالترتيب — للمنتقيات التي تحمل القيمة نصّاً. */
export const CROP_LABELS: readonly string[] = CROP_OPTIONS.map((o) => o.label);

/** ما يُعرَض مكان قيمة محصول مخزّنة لا تُحلّ إلى بطاقة (تحتاج محصولاً محدّداً). */
export const UNSPECIFIED_CROP_LABEL = 'غير محدَّد — اختر المحصول';

/** قيم عامّة عرضتها منتقيات سابقة (الويب والموبايل) وقد تبقى مخزّنة في حقول قائمة.
 *  لا تُحلّ إلى أيّ بطاقة — والحارس يُثبت ذلك — فلا تُمرَّر صامتةً ولا تُربَط بمحصول
 *  اعتباطيّ: تُعرَض «غير محدَّد» حتّى يختار المزارع محصولاً محدّداً. */
export const LEGACY_GENERIC_CROP_VALUES: readonly string[] = [
  'خضروات', 'vegetables', 'فواكه', 'fruits', 'أخرى', 'other',
];

/** هل القيمة المخزّنة «بلا محصول محدّد»؟ (فارغة · «—» · قيمة عامّة قديمة). */
export function isUnspecifiedCrop(raw: string | null | undefined): boolean {
  const v = (raw ?? '').trim();
  return v === '' || v === '—' || LEGACY_GENERIC_CROP_VALUES.includes(v);
}
