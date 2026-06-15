// authStorage.ts — مصدر واحد للحقيقة لقراءة بيانات الجلسة من التخزين.
//
// خلفيّة (bug سابق): useAuth.ts يكتب التوكن/المستأجِر في sessionStorage، وapi.ts
// يقرأ من sessionStorage (صحيح)، لكن websocket.ts كان يقرأ من localStorage —
// فيرجع دائماً فارغاً ويسقط على التوكن الحرفيّ 'demo' لكلّ مستخدم مُصادَق عليه،
// أي أنّ اتّصال الإشعارات لم يكن يحمل توكن المستخدم الحقيقيّ إطلاقاً.
//
// لمنع تكرار هذا الانحراف: كلّ قرّاء التخزين يمرّون عبر هذه الدوال (لا وصول
// مباشر للـStorage بمفاتيح مكرّرة). sessionStorage هو مصدر الحقيقة (يطابق useAuth).

export const STORAGE_KEYS = {
  accessToken: 'sahool_access_token',
  tenantId: 'sahool_tenant_id',
  user: 'sahool_user',
} as const;

const DEFAULT_TENANT = 'default';

// وصول آمن لـsessionStorage (قد يُرمى في بيئات SSR أو وضع الخصوصيّة الصارم).
function safeRead(key: string): string | null {
  try {
    if (typeof sessionStorage === 'undefined') return null;
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

/** توكن الوصول (JWT) من الجلسة، أو null إن لم يوجد. */
export function getAccessToken(): string | null {
  return safeRead(STORAGE_KEYS.accessToken);
}

/** مُعرّف المستأجِر، مع قيمة افتراضيّة 'default' (يطابق سلوك api.ts السابق). */
export function getTenantId(): string {
  return safeRead(STORAGE_KEYS.tenantId) || DEFAULT_TENANT;
}
