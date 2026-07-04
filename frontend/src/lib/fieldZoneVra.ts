// FieldView Zone & VRA readiness — مستوحى من GeoPard/EOS/OneSoil: يجعل مسار
// Field → Zone → Action (مناطق إنتاجيّة ثمّ وصفة تطبيق متغيّر) جزءاً واضحاً من
// FieldView بدل صفحة منفصلة. لا يعيد بناء المحرّكات القائمة (v60 مناطق · v62 وصفات)؛
// يقيس الجاهزيّة من إشارات حقيقيّة ويوجّه إلى التدفّق الموجود.
//
// صدق المصدر: الجاهزيّة مشتقّة من (حقل نشط · عدد مشاهد جاهزة للعنقدة · عدد الوصفات
// المحفوظة فعلاً). لا اختلاق — «محجوب» صريح حين تنقص المدخلات.
export type ZoneVraStepStatus = 'ready' | 'blocked' | 'done';
export type ZoneVraStepKey = 'field' | 'zone' | 'action';

export interface ZoneVraStep {
  key: ZoneVraStepKey;
  label: string;
  status: ZoneVraStepStatus;
  hint: string;
}

export interface ZoneVraReadinessInput {
  hasField: boolean;
  /** عدد مشاهد الصور الجاهزة (COG) — الأساس لعنقدة المناطق الإنتاجيّة. */
  imageryReadyCount: number;
  /** عدد الوصفات المحفوظة للحقل فعلاً. */
  prescriptionCount: number;
}

export interface ZoneVraReadiness {
  steps: ZoneVraStep[];
  /** هل تتوفّر مدخلات كافية لبناء مناطق الآن؟ */
  canBuildZones: boolean;
  summary: string;
}

export function buildZoneVraReadiness(input: ZoneVraReadinessInput): ZoneVraReadiness {
  const canBuildZones = input.hasField && input.imageryReadyCount >= 1;

  const field: ZoneVraStep = {
    key: 'field',
    label: 'الحقل',
    status: input.hasField ? 'ready' : 'blocked',
    hint: input.hasField ? 'حقل نشط محدَّد.' : 'اختر حقلاً أولاً.',
  };

  const zone: ZoneVraStep = {
    key: 'zone',
    label: 'المناطق الإنتاجيّة',
    status: !input.hasField ? 'blocked' : input.imageryReadyCount >= 1 ? 'ready' : 'blocked',
    hint: !input.hasField
      ? 'بانتظار حقل.'
      : input.imageryReadyCount >= 1
        ? `${input.imageryReadyCount} مشهد جاهز — ابنِ المناطق من NDVI.`
        : 'تحتاج صورة جاهزة (COG) لعنقدة المناطق — شغّل تجهيز الصور.',
  };

  const action: ZoneVraStep = {
    key: 'action',
    label: 'وصفة التطبيق المتغيّر',
    status: !input.hasField
      ? 'blocked'
      : input.prescriptionCount > 0
        ? 'done'
        : canBuildZones
          ? 'ready'
          : 'blocked',
    hint: !input.hasField
      ? 'بانتظار حقل.'
      : input.prescriptionCount > 0
        ? `${input.prescriptionCount} وصفة محفوظة — صدّرها للمعدّات.`
        : canBuildZones
          ? 'جاهز لإنشاء وصفة تسميد/ريّ/رشّ متغيّرة من المناطق.'
          : 'تحتاج مناطق أولاً.',
  };

  const summary = !input.hasField
    ? 'اختر حقلاً لبدء مسار المناطق والوصفات.'
    : canBuildZones
      ? input.prescriptionCount > 0
        ? 'المسار مكتمل: مناطق ووصفات جاهزة للتصدير.'
        : 'جاهز: ابنِ المناطق ثمّ أنشئ وصفة تطبيق متغيّر.'
      : 'المسار محجوب: جهّز صورة جاهزة أولاً لعنقدة المناطق.';

  return { steps: [field, zone, action], canBuildZones, summary };
}
