// FieldView Field Water Brain — مستوحى من CropX (soil-to-sky): يوحّد رطوبة التربة +
// المطر المتوقَّع + الحرارة في قرار ريّ واحد واضح (اسقِ الآن / أجّل / راقب) مع ثقة
// وسبب. ليس بديلاً عن محرّك التوأم المائيّ FAO-56 (useComputeIrrigationPlan) — بل
// ملخّص قرار سريع يوجّه إليه للتخطيط التفصيليّ.
//
// صدق المصدر: القرار من إشارات حيّة فعليّة (رطوبة جهاز · تنبّؤ مطر · حرارة). عند
// غياب الرطوبة يُرجَع 'unknown' صراحةً ويُحال للتوأم المائيّ بدل قرار مُختلَق.
export type WaterDecision = 'irrigate_now' | 'soon' | 'defer' | 'watch' | 'unknown';

export interface WaterBrainInput {
  soilMoisturePct?: number | null;
  /** مجموع المطر المتوقَّع خلال الأيّام القليلة القادمة (مم). */
  forecastRainMm?: number | null;
  tempMaxC?: number | null;
}

export interface WaterBrainEvidence {
  label: string;
  value: string;
}

export interface WaterBrainResult {
  decision: WaterDecision;
  label: string;
  reason: string;
  /** ثقة القرار 0..100 حسب عدد الإشارات المتاحة وحدّتها. */
  confidence: number;
  evidence: WaterBrainEvidence[];
}

const DECISION_LABEL: Record<WaterDecision, string> = {
  irrigate_now: 'اسقِ الآن',
  soon: 'ريّ قريب',
  defer: 'أجّل الريّ',
  watch: 'راقب',
  unknown: 'غير محدَّد',
};

const RAIN_SIGNIFICANT_MM = 10; // مطر مؤثّر يؤجّل الريّ
const HEAT_THRESHOLD_C = 40; // حرارة مرتفعة تزيد الطلب المائيّ

export function evaluateWaterBrain(input: WaterBrainInput): WaterBrainResult {
  const pct = typeof input.soilMoisturePct === 'number' && Number.isFinite(input.soilMoisturePct) ? input.soilMoisturePct : null;
  const rain = typeof input.forecastRainMm === 'number' && Number.isFinite(input.forecastRainMm) ? input.forecastRainMm : null;
  const heat = typeof input.tempMaxC === 'number' && Number.isFinite(input.tempMaxC) ? input.tempMaxC : null;

  const evidence: WaterBrainEvidence[] = [
    { label: 'رطوبة التربة', value: pct != null ? `${Math.round(pct)}%` : '—' },
    { label: 'مطر متوقَّع', value: rain != null ? `${Math.round(rain)}مم` : '—' },
    { label: 'حرارة عظمى', value: heat != null ? `${Math.round(heat)}°` : '—' },
  ];

  if (pct == null) {
    return {
      decision: 'unknown',
      label: DECISION_LABEL.unknown,
      reason: 'لا قراءة رطوبة تربة — استخدم التوأم المائيّ للتقدير من ETc/الطقس.',
      confidence: 0,
      evidence,
    };
  }

  // مطر مؤثّر قادم ⇒ أجّل مهما كانت الرطوبة (تفادي الريّ قبل المطر).
  if (rain != null && rain >= RAIN_SIGNIFICANT_MM) {
    return {
      decision: 'defer',
      label: DECISION_LABEL.defer,
      reason: `مطر متوقَّع ${Math.round(rain)}مم — أجّل الريّ وأعِد التقييم بعده.`,
      confidence: 80,
      evidence,
    };
  }

  // قِسمة القرار حسب الرطوبة، مع تعديل الحرارة.
  const hot = heat != null && heat >= HEAT_THRESHOLD_C;
  let decision: WaterDecision;
  let reason: string;
  if (pct < 20) {
    decision = 'irrigate_now';
    reason = hot ? 'رطوبة منخفضة مع حرارة مرتفعة — الريّ عاجل.' : 'رطوبة منخفضة — الريّ مطلوب الآن.';
  } else if (pct < 35) {
    decision = hot ? 'irrigate_now' : 'soon';
    reason = hot ? 'رطوبة متوسّطة مع حرارة مرتفعة — قدّم الريّ.' : 'رطوبة متوسّطة — جهّز الريّ خلال يوم/يومين.';
  } else {
    decision = 'defer';
    reason = 'رطوبة كافية — لا حاجة للريّ الآن.';
  }

  // الثقة: رطوبة وحدها 65؛ + مطر 15؛ + حرارة 10 (حتّى 90؛ يبقى هامش لعدم اليقين).
  let confidence = 65;
  if (rain != null) confidence += 15;
  if (heat != null) confidence += 10;

  return { decision, label: DECISION_LABEL[decision], reason, confidence, evidence };
}
