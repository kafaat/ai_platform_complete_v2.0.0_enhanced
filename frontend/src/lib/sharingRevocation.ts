/**
 * An HTTP transport failure does not establish that a revocation was rolled back.
 * The server may have applied the write before its response was lost.
 */
/** A route advertised only on newer backends; absence/invalid shapes are UNSUPPORTED. */
export function supportsSharingKeyRevocation(response: unknown): boolean {
  if (!response || typeof response !== 'object') return false;
  const caps = (response as { capabilities?: unknown }).capabilities;
  return caps !== null && typeof caps === 'object' &&
    (caps as { revoke_keys?: unknown }).revoke_keys === true;
}

export const SHARING_REVOKE_UNAVAILABLE_AR =
  'إلغاء المفاتيح غير متاح على إصدار الخادم الحالي؛ لم يُنفَّذ أي طلب إلغاء.';

export type SharingRevocationOutcome = 'confirmed' | 'unknown' | 'confirmed_refresh_unavailable';

export const SHARING_REVOKE_UNKNOWN_AR =
  'تعذّر التحقق من نتيجة الإلغاء؛ حدّث القائمة للتحقق من حالة المفتاح.';
export const SHARING_REVOKE_REFRESH_FAILED_AR =
  'أكّد الخادم الإلغاء، لكن تعذّر تحديث القائمة؛ حدّثها للتحقق من الحالة.';

/** Refresh even when the revocation response is lost; never imply no side effect. */
export async function revokeAndReconcileSharingKey(
  keyId: string,
  request: (url: string) => Promise<unknown>,
  refresh: () => Promise<unknown>,
): Promise<SharingRevocationOutcome> {
  let confirmed = false;
  try {
    const receipt = await request(`/api/v1/sharing/keys/${encodeURIComponent(keyId)}/revoke`);
    confirmed = typeof receipt === 'object' && receipt !== null &&
      'key_id' in receipt && receipt.key_id === keyId &&
      'status' in receipt && receipt.status === 'revoked';
  } catch {
    // Could be a lost response after the server committed; outcome is unknown.
  }

  try {
    await refresh();
  } catch {
    // A failed refresh cannot undo an already confirmed server response.
    return confirmed ? 'confirmed_refresh_unavailable' : 'unknown';
  }
  return confirmed ? 'confirmed' : 'unknown';
}
