// useIndicatorRegistry — قارئ مانيفست سجلّ المؤشّرات (WS-B.2، build-time only).
//
// المصدر مانيفست مُولَّد وقت البناء (lib/indicatorsRegistry.generated.ts) من المصدر
// الأوحد config/indicators_registry.json — لا نقطة runtime (سقف مسارات المنصّة p2_6=575
// يمنعها)، ولا اعتماد على config داخل الحاوية. حتميّ ودائم التوفّر.
//
// السجلّ هو المصدر الأحاديّ لِـ *مجموعة* المؤشّرات + availability + source_class +
// renderable. تحتفظ الواجهة بخصائص العرض الثابتة (أيقونة/لون/وصف) مفتاحها id فقط
// للتلميع، بينما تأتي الحقائق من المانيفست. النسخة (REGISTRY_VERSION) علامة نضارة
// مبنيّة وقت البناء يعرضها المستهلك.

import {
  INDICATORS_MANIFEST,
  REGISTRY_DIGEST,
  REGISTRY_VERSION,
} from '../lib/indicatorsRegistry.generated';

// حالة توفّر المؤشّر كما يعلنها السجلّ — تُعرض بصدق لا تُخفى.
export type IndicatorAvailability = 'active' | 'estimated' | 'unavailable';

// تصنيف مصدر القيمة (حين يتوفّر) — حقيقيّ/تقديريّ/مُشتقّ.
export type IndicatorSourceClass = 'real' | 'estimated' | 'derived' | null;

export interface RegistryIndicator {
  id: string;
  name_ar: string;
  name_en: string;
  category: string;
  unit: string;
  range: [number, number] | null;
  renderable: boolean;
  source_class: IndicatorSourceClass;
  availability: IndicatorAvailability;
}

export interface IndicatorRegistryResponse {
  registry_version: string; // بادئة digest بطول 12 — علامة نضارة الـmanifest المبنيّ
  content_digest: string; // sha256:...
  count: number;
  indicators: RegistryIndicator[];
  note_ar: string;
}

export interface UseIndicatorRegistryResult {
  data: IndicatorRegistryResponse | null;
  loading: boolean;
  error: unknown;
}

// المانيفست المبنيّ وقت البناء — إسقاط عموميّ من السجلّ الكنسيّ. القيم مُولَّدة، لكنّ
// أنواع المانيفست nullable (توليد آمن) فنُطبّعها إلى العقد غير الفارغ للعرض.
const INDICATORS: RegistryIndicator[] = INDICATORS_MANIFEST.map((m) => ({
  id: m.id,
  name_ar: m.name_ar ?? m.id,
  name_en: m.name_en ?? m.id,
  category: m.category ?? 'other',
  unit: m.unit ?? '',
  range: m.range,
  renderable: m.renderable ?? false,
  source_class: m.source_class,
  availability: m.availability,
}));

const MANIFEST: IndicatorRegistryResponse = {
  registry_version: REGISTRY_VERSION,
  content_digest: REGISTRY_DIGEST,
  count: INDICATORS.length,
  indicators: INDICATORS,
  note_ar: 'مانيفست مُولَّد وقت البناء من السجلّ الكنسيّ — للعرض/الحالة فقط.',
};

/**
 * سجلّ المؤشّرات من المانيفست المبنيّ وقت البناء. حتميّ ودائم التوفّر: لا جلب، لا
 * حالة تحميل/خطأ (يبقى العقد {data, loading, error} للتوافق مع المستهلك).
 */
export function useIndicatorRegistry(): UseIndicatorRegistryResult {
  return { data: MANIFEST, loading: false, error: null };
}
