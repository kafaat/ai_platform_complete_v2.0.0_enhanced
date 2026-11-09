/** Rendering policy for the field-change API: source reality is not comparability. */
export interface FieldChangeAvailability {
  available: boolean;
  real_data?: boolean;
  status?: string;
  reason_codes?: string[];
  note?: string;
}

/** Human-readable refusal; never mislabel real imagery as missing when comparison fails. */
export function unavailableFieldChangeMessage(change: FieldChangeAvailability): string {
  if (typeof change.note === 'string' && change.note.trim()) return change.note;
  if (change.real_data === true) {
    if (change.reason_codes?.includes('no_common_valid_pixels')) {
      return 'توجد صور COG حقيقيّة للتاريخين، لكن لا توجد بكسلات صالحة مشتركة؛ المقارنة غير قابلة للتقييم.';
    }
    return 'توجد صور COG حقيقيّة، لكن لم تتحقّق شروط تقييم التغيّر؛ لا نتيجة تغيّر محسوبة.';
  }
  return 'لا توجد بيانات COG حقيقيّة لأحد التاريخين — لا تغيّر محسوب.';
}
