// Planting Advisor — يجيب «ماذا أزرع بعد محصولي؟» من محرّكات backend المُخزَّنة:
// rotation/suggest (ترتيب good/acceptable/avoid بأسباب يمنيّة مُوثَّقة) +
// planting/check (ملاءمة الشهر الحاليّ لحكم الخادم). صدق: الترتيب والأسباب
// والأحكام كلّها من الخادم — الواجهة تعرض ولا تعيد الحكم؛ محصول غير معروف يمرّ
// بـmessage_ar كما جاء؛ وdisclaimer الخادم («توجّه لا تفرض») يُعرَض.

import type { PlantingFit } from './yemeniCalendar';

export interface RotationCandidate {
  previous_crop: string;
  candidate_crop: string;
  rating: 'good' | 'acceptable' | 'avoid' | string;
  rating_ar: string;
  reasons_ar: string[];
}

export interface RotationSuggestResponse {
  supported: boolean;
  previous_crop?: string;
  ranked?: RotationCandidate[];
  yemen_note_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
}

export interface GroupedCandidates {
  good: RotationCandidate[];
  acceptable: RotationCandidate[];
  avoid: RotationCandidate[];
}

/** تجميع المرشّحين بتصنيف الخادم — تصنيف غريب يُهمَل بصدق (لا يُخترَع رفّ له). */
export function groupRanked(resp: RotationSuggestResponse | null | undefined): GroupedCandidates {
  const g: GroupedCandidates = { good: [], acceptable: [], avoid: [] };
  if (!resp?.supported || !Array.isArray(resp.ranked)) return g;
  for (const c of resp.ranked) {
    if (c.rating === 'good') g.good.push(c);
    else if (c.rating === 'acceptable') g.acceptable.push(c);
    else if (c.rating === 'avoid') g.avoid.push(c);
  }
  return g;
}

export function ratingColor(rating: string | null | undefined): string {
  if (rating === 'good') return '#86efac';
  if (rating === 'acceptable') return '#fde68a';
  if (rating === 'avoid') return '#fca5a5';
  return '#64748b';
}

/** الشهر الحاليّ 1-12 من تاريخ ISO (لا Date.now في الاختبارات — يُمرَّر التاريخ). */
export function monthOfIso(dateIso: string | null | undefined): number | null {
  if (!dateIso) return null;
  const m = Number(String(dateIso).slice(5, 7));
  return Number.isInteger(m) && m >= 1 && m <= 12 ? m : null;
}

export type { PlantingFit };
