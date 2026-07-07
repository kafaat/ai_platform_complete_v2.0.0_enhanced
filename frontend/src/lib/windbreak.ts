// windbreak.ts — عقد «الرياح السائدة + المصدّ» (V73-UI) + مساعِدات عرض نقيّة.
//
// يطابق مخرَج GET /api/v1/fields/{id}/wind/prevailing: إمّا computed:true بحمولة
// وردة رياح + توصية مصدّ، أو computed:false + reason. الواجهة تعرض المحسوب بقيمته
// والمتعذّر بسببه صراحةً (لا اختلاق) — فلسفة الخلفيّة نفسها. مساعِدات نقيّة (بلا React).

export interface CompassPoint {
  deg?: number;
  key?: string;
  label_ar?: string;
}

export interface WindbreakRec {
  status?: 'ok' | 'unknown';
  prevailing_from?: CompassPoint;
  wind_towards?: CompassPoint;
  barrier_orientation_deg?: number;
  plant_side?: string | null;
  note_ar?: string;
  protected_downwind_m?: number;
  protected_upwind_m?: number;
  protection_basis?: string;
}

export interface WindPrevailingResponse {
  field_id?: string;
  source?: string;
  resolution?: string;
  computed?: boolean;
  reason?: string;
  years?: number;
  n_observations?: number;
  prevailing?: CompassPoint;
  wind_rose?: Record<string, number>;
  windbreak?: WindbreakRec;
}

/** أعلى قطاعات وردة الرياح تكراراً (تنازليّاً) — لعرض «من أين تأتي الرياح غالباً». */
export function topRoseSectors(
  rose: Record<string, number> | undefined,
  limit = 3,
): Array<{ key: string; count: number }> {
  if (!rose) return [];
  return Object.entries(rose)
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

/** سبب التعذّر بالعربيّة (المجهول يُعرَض كما هو بصدق). */
export function windMissingReasonAr(reason?: string): string {
  const map: Record<string, string> = {
    nasa_power_wind_unavailable: 'مصدر رياح NASA POWER غير متاح حاليّاً',
    insufficient_observations: 'تاريخ الرياح غير كافٍ لتحديد اتّجاه سائد',
    no_prevailing_wind: 'لا اتّجاه سائد',
  };
  return (reason && map[reason]) || reason || 'غير متاح';
}

/** وصف عمق الحماية بالعربيّة (يحترم صدق الخلفيّة: بلا ارتفاع لا رقم متر). */
export function protectionSummaryAr(w?: WindbreakRec): string {
  if (!w) return '—';
  if (typeof w.protected_downwind_m === 'number') {
    return `حماية ~${w.protected_downwind_m}م أمام الريح`;
  }
  return 'أدخِل ارتفاع الأشجار لتقدير عمق الحماية (~10×الارتفاع)';
}
