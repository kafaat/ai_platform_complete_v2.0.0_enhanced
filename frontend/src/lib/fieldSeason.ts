// FieldView Season Command Center — مستوحى من Cropin/Cropwise: يعرض المرحلة الحاليّة
// للموسم النشط + التقدّم عبر خطّ الزمن + إجراء الطور المقترَح، من نقطة phenology الحيّة
// (/api/v1/fields/{id}/phenology). صدق: عند غياب البذار/المحصول تُعرَض حالة
// available=false بسببها الصريح بدل تقدير مُلفَّق.
export interface SeasonPhenologyStageLite {
  name_ar: string;
  day_start: number;
  day_end: number;
  status: 'past' | 'current' | 'upcoming';
}

export interface SeasonPhenologyLite {
  available: boolean;
  reason_ar?: string;
  crop?: string;
  days_after_sowing?: number;
  current_stage?: { name_ar?: string } | null;
  current_stage_kc?: number | null;
  timeline?: SeasonPhenologyStageLite[];
}

export interface SeasonSummary {
  available: boolean;
  reason: string | null;
  crop: string | null;
  stageName: string | null;
  daysAfterSowing: number | null;
  kc: number | null;
  /** تقدّم الموسم % = das ÷ آخر يوم في خطّ الزمن. */
  progressPct: number | null;
  stages: Array<{ name: string; status: 'past' | 'current' | 'upcoming' }>;
  nextStageName: string | null;
}

export function summarizeSeason(p: SeasonPhenologyLite | null | undefined): SeasonSummary {
  const empty: SeasonSummary = {
    available: false,
    reason: null,
    crop: null,
    stageName: null,
    daysAfterSowing: null,
    kc: null,
    progressPct: null,
    stages: [],
    nextStageName: null,
  };

  if (!p) return empty;
  if (!p.available) return { ...empty, reason: p.reason_ar ?? 'مراحل الموسم غير متاحة.', crop: p.crop ?? null };

  const timeline = p.timeline ?? [];
  const das = typeof p.days_after_sowing === 'number' ? p.days_after_sowing : null;
  const lastEnd = timeline.reduce((m, s) => Math.max(m, s.day_end), 0);
  const progressPct = das != null && lastEnd > 0 ? Math.max(0, Math.min(100, Math.round((das / lastEnd) * 100))) : null;

  const currentStage = timeline.find((s) => s.status === 'current') ?? null;
  const stageName = p.current_stage?.name_ar ?? currentStage?.name_ar ?? null;
  const nextStage = timeline.find((s) => s.status === 'upcoming') ?? null;

  return {
    available: true,
    reason: null,
    crop: p.crop ?? null,
    stageName,
    daysAfterSowing: das,
    kc: typeof p.current_stage_kc === 'number' ? p.current_stage_kc : null,
    progressPct,
    stages: timeline.map((s) => ({ name: s.name_ar, status: s.status })),
    nextStageName: nextStage?.name_ar ?? null,
  };
}
