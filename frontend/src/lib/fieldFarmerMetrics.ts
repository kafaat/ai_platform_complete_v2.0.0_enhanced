// FieldView 4-Metric Farmer View — مستوحى من Kisan360/Farmonaut: يبسّط حالة الحقل
// إلى أربعة مؤشّرات يفهمها الفلاح فوراً — صحة النبات · الماء/الرطوبة · التغذية/النيتروجين
// · خطر الطقس — بدل عرض كلّ المؤشّرات الخام. التفاصيل تبقى اختياريّة في الشاشات الأخرى.
//
// صدق المصدر: كلّ مؤشّر مشتقّ من قيمة حقيقيّة (NDVI الحيّ · رطوبة تربة جهاز · توصية
// نيتروجين التربة · تنبّؤ الطقس). عند غياب الإشارة تُعرَض الحالة 'unknown' صراحةً بدل
// رقم ملفَّق. العتبات موثّقة أدناه وقابلة للمراجعة الزراعيّة.
export type FarmerMetricStatus = 'good' | 'watch' | 'risk' | 'unknown';
export type FarmerMetricKey = 'health' | 'water' | 'nutrition' | 'weather';

export interface FarmerMetric {
  key: FarmerMetricKey;
  label: string;
  status: FarmerMetricStatus;
  value: string;
  reason: string;
}

export interface FarmerMetricsInput {
  /** NDVI الحيّ (0..1). */
  ndvi?: number | null;
  /** رطوبة التربة % من أحدث قراءة جهاز. */
  soilMoisturePct?: number | null;
  /** حالة النيتروجين من توصية التربة. */
  nitrogenStatus?: 'adequate' | 'deficit' | 'excess' | null;
  /** إشارات الطقس القادم (قِيَم فعليّة من التنبّؤ). */
  weather?: { tempMaxC?: number | null; windMs?: number | null; rainMm?: number | null } | null;
}

const STATUS_ORDER: Record<FarmerMetricStatus, number> = { risk: 0, watch: 1, unknown: 2, good: 3 };

function healthMetric(ndvi?: number | null): FarmerMetric {
  if (ndvi == null || !Number.isFinite(ndvi)) {
    return { key: 'health', label: 'صحة النبات', status: 'unknown', value: '—', reason: 'لا يوجد NDVI حيّ للحقل بعد.' };
  }
  const v = `NDVI ${ndvi.toFixed(2)}`;
  if (ndvi >= 0.6) return { key: 'health', label: 'صحة النبات', status: 'good', value: v, reason: 'غطاء نباتيّ قويّ.' };
  if (ndvi >= 0.35) return { key: 'health', label: 'صحة النبات', status: 'watch', value: v, reason: 'غطاء متوسّط — راقب الإجهاد.' };
  return { key: 'health', label: 'صحة النبات', status: 'risk', value: v, reason: 'غطاء ضعيف — إجهاد محتمل.' };
}

function waterMetric(pct?: number | null): FarmerMetric {
  if (pct == null || !Number.isFinite(pct)) {
    return { key: 'water', label: 'الماء/الرطوبة', status: 'unknown', value: '—', reason: 'لا قراءة رطوبة تربة من الأجهزة.' };
  }
  const v = `رطوبة ${Math.round(pct)}%`;
  if (pct >= 35) return { key: 'water', label: 'الماء/الرطوبة', status: 'good', value: v, reason: 'رطوبة كافية.' };
  if (pct >= 20) return { key: 'water', label: 'الماء/الرطوبة', status: 'watch', value: v, reason: 'رطوبة متوسّطة — قد يلزم ريّ قريباً.' };
  return { key: 'water', label: 'الماء/الرطوبة', status: 'risk', value: v, reason: 'رطوبة منخفضة — الريّ مطلوب.' };
}

function nutritionMetric(status?: 'adequate' | 'deficit' | 'excess' | null): FarmerMetric {
  if (status == null) {
    return { key: 'nutrition', label: 'التغذية/النيتروجين', status: 'unknown', value: '—', reason: 'تتطلّب تحليل تربة/توصية نيتروجين.' };
  }
  if (status === 'adequate') return { key: 'nutrition', label: 'التغذية/النيتروجين', status: 'good', value: 'كافٍ', reason: 'النيتروجين ضمن النطاق.' };
  if (status === 'excess') return { key: 'nutrition', label: 'التغذية/النيتروجين', status: 'watch', value: 'زائد', reason: 'نيتروجين زائد — قلّل التسميد.' };
  return { key: 'nutrition', label: 'التغذية/النيتروجين', status: 'risk', value: 'نقص', reason: 'نقص نيتروجين — يلزم تسميد.' };
}

function weatherMetric(w?: FarmerMetricsInput['weather']): FarmerMetric {
  if (!w || (w.tempMaxC == null && w.windMs == null && w.rainMm == null)) {
    return { key: 'weather', label: 'خطر الطقس', status: 'unknown', value: '—', reason: 'لا تنبّؤ طقس متاح.' };
  }
  const risks: string[] = [];
  if (w.tempMaxC != null && w.tempMaxC >= 42) risks.push(`حرارة ${Math.round(w.tempMaxC)}°`);
  if (w.windMs != null && w.windMs >= 10) risks.push(`رياح ${Math.round(w.windMs)}م/ث`);
  if (w.rainMm != null && w.rainMm >= 10) risks.push(`مطر ${Math.round(w.rainMm)}مم`);
  if (risks.length >= 2) return { key: 'weather', label: 'خطر الطقس', status: 'risk', value: risks.join(' · '), reason: 'ظروف خطرة — أجّل الرشّ/الريّ.' };
  if (risks.length === 1) return { key: 'weather', label: 'خطر الطقس', status: 'watch', value: risks[0], reason: 'انتباه لظرف طقس واحد.' };
  return { key: 'weather', label: 'خطر الطقس', status: 'good', value: 'مستقرّ', reason: 'لا مخاطر طقس قريبة.' };
}

export function buildFarmerMetrics(input: FarmerMetricsInput): FarmerMetric[] {
  return [
    healthMetric(input.ndvi),
    waterMetric(input.soilMoisturePct),
    nutritionMetric(input.nitrogenStatus),
    weatherMetric(input.weather),
  ];
}

/** أسوأ حالة عبر المؤشّرات الأربعة (للترويسة/الفرز). */
export function worstFarmerStatus(metrics: FarmerMetric[]): FarmerMetricStatus {
  return metrics.reduce<FarmerMetricStatus>(
    (worst, m) => (STATUS_ORDER[m.status] < STATUS_ORDER[worst] ? m.status : worst),
    'good',
  );
}
