// Why an advisor chat request failed, in words the farmer can act on.
//
// Before: every failure (expired login, advisor not deployed, gateway timeout, approval store
// down) showed the same "check your connection and log in" message, so a 503 from the advisor
// read as a login problem and the real cause never reached the screen.

export type AdvisorFailureKind = 'auth' | 'unavailable' | 'timeout' | 'rejected' | 'network';

export interface AdvisorFailure {
  kind: AdvisorFailureKind;
  status: number | null;
  // Short machine reason from the server (FastAPI ``detail`` string), when it sent one.
  reasonCode: string | null;
  messageAr: string;
}

const REASON_CODE = /^[a-z][a-z0-9_.-]{1,63}$/;

function pickReasonCode(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const rec = data as Record<string, unknown>;
  for (const key of ['reason_code', 'detail', 'error']) {
    const v = rec[key];
    // Only a code-shaped string: never echo free text or a stack trace into the chat.
    if (typeof v === 'string' && REASON_CODE.test(v)) return v;
    if (v && typeof v === 'object') {
      const inner = (v as Record<string, unknown>).reason_code;
      if (typeof inner === 'string' && REASON_CODE.test(inner)) return inner;
    }
  }
  return null;
}

export function describeAdvisorFailure(err: unknown): AdvisorFailure {
  const e = (err ?? {}) as { response?: { status?: unknown; data?: unknown }; code?: unknown };
  const status = typeof e.response?.status === 'number' ? e.response.status : null;
  const reasonCode = pickReasonCode(e.response?.data);
  const suffix = reasonCode ? ` (${reasonCode})` : '';

  if (status === 401 || status === 403) {
    return { kind: 'auth', status, reasonCode,
      messageAr: 'انتهت الجلسة أو لا تملك صلاحيّة المستشار. سجّل الدخول ثمّ أعد المحاولة.' };
  }
  if (status === 504 || e.code === 'ECONNABORTED') {
    return { kind: 'timeout', status, reasonCode,
      messageAr: `انتهت مهلة المستشار قبل أن يجيب${suffix}. أعد المحاولة بعد قليل.` };
  }
  if (status === 502 || status === 503) {
    return { kind: 'unavailable', status, reasonCode,
      messageAr: `المستشار أو أحد مصادر أدلّته غير متاح الآن${suffix}. لم تُولَّد أيّ إجابة.` };
  }
  if (status !== null) {
    return { kind: 'rejected', status, reasonCode,
      messageAr: `رفض المستشار الطلب (HTTP ${status})${suffix}.` };
  }
  return { kind: 'network', status: null, reasonCode: null,
    messageAr: 'تعذّر الوصول إلى المستشار. تحقّق من الاتّصال ثمّ أعد المحاولة.' };
}
