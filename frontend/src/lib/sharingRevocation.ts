/**
 * An HTTP transport failure does not establish that a revocation was rolled back.
 * The server may have applied the write before its response was lost.
 */
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
    await request(`/api/v1/sharing/keys/${encodeURIComponent(keyId)}/revoke`);
    confirmed = true;
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
