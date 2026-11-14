// ═══════════════════════════════════════════════════════════════
// SAHOOL UI-3B — Auth API module
// Low-risk extraction from services/api.ts. Keep api.ts as compatibility facade.
// ═══════════════════════════════════════════════════════════════

import { MOCK_MODE, tryReal, authApi, authEnrollmentApi, kongApi } from './client';

// ══════════════════════════════════════════════════════════════════
// AUTH
// ══════════════════════════════════════════════════════════════════
// عقد auth-service: /auth/login و/auth/register يتوقّعان `email` (لا username).
export interface LoginPayload { email: string; password: string; mfa_code?: string; }
// auth-service يردّ حقولاً مسطّحة (TokenResponse: user_id/role/full_name/tenant_id،
// بلا كائن user مُتداخل). نُطبّعها أدناه إلى {user:{...}} كي يقرأها useAuth بثبات.
// user اختياريّ (غائب في الردّ الخام) ويحوي id (من user_id) لتفادي ضياعه.
export interface AuthResponse {
  access_token: string;
  // قد تكون null حين لا يتوفّر Redis (auth-service لا يُصدِر refresh) — نُبقيها كما
  // هي بدل طمسها بـ'' (سلسلة فارغة تُلتبَس كتوكن صالح). يطابق عقد TokenResponse.
  refresh_token: string | null;
  tenant_id?: string;
  role?: string;
  user_id?: number;
  full_name?: string;
  user?: { id?: number; username?: string; role: string; tenant_id?: string; email?: string; full_name?: string };
}

export const login = (payload: LoginPayload): Promise<AuthResponse> =>
  // أمان (P0-2): المصادقة لا تسقط على fallback وهمي. الفشل يظهر بوضوح
  // بدل منح admin زائف. وضع التجريب فقط عبر MOCK_MODE الصريح، وبدور farmer.
  // mfa_code يُرسَل فقط إن وُجد (الخادم يتطلّبه للحسابات المُفعّل لها MFA).
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh', user:{ username:payload.email, email:payload.email, role:'farmer' } } as AuthResponse)
    : authApi.post('/auth/login', {
        email: payload.email,
        password: payload.password,
        ...(payload.mfa_code ? { mfa_code: payload.mfa_code } : {}),
      }).then(r => {
        // الردّ الخام مسطّح ⇒ نطبّعه إلى {user:{...}} (كان login يُعيد الخام مباشرةً
        // فيصبح data.user = undefined وقت التشغيل، فيضيع user_id/full_name).
        const d = r.data as { access_token: string; refresh_token?: string | null; role?: string;
          full_name?: string; tenant_id?: string; user_id?: number };
        return {
          access_token: d.access_token,
          refresh_token: d.refresh_token ?? null,
          tenant_id: d.tenant_id,
          role: d.role,
          user_id: d.user_id,
          full_name: d.full_name,
          user: { id: d.user_id, username: payload.email, email: payload.email,
            role: d.role ?? 'farmer', tenant_id: d.tenant_id, full_name: d.full_name },
        } as AuthResponse;
      });

// شكل خطأ أكسيوس/FastAPI كما تقرؤه الواجهة (response.status/data.detail + message).
// نوع موحّد بدل any المتناثر في معالِجات catch وحُرّاس .response?.status عبر الشاشات.
export interface ApiErrorDetailItem { msg?: string; message_ar?: string }
export interface ApiError {
  response?: {
    status?: number;
    headers?: Record<string, string | boolean | undefined>;
    data?: {
      detail?: string | ApiErrorDetailItem[] | { message_ar?: string; msg?: string };
      message_ar?: string;
    };
  };
  message?: string;
}

// يضيّق unknown → ApiError بأمان (يقرأ الحقول كاختياريّة فقط، لا يفترض شكلاً صلباً).
export function asApiError(e: unknown): ApiError {
  return (e ?? {}) as ApiError;
}

/** يفحص ما إذا كان خطأ تسجيل الدخول يعني "MFA مطلوب" (الخادم يردّ 401 مع
 *  الرأس X-MFA-Required: true حين تصحّ كلمة المرور لكن يلزم رمز TOTP). */
export function isMfaRequiredError(e: unknown): boolean {
  const err = asApiError(e);
  const status = err.response?.status;
  const header = err.response?.headers?.['x-mfa-required'];
  return status === 401 && (header === 'true' || header === true);
}

// يستخرج رسالة خطأ مقروءة من ردّ FastAPI (detail قد يكون نصّاً أو مصفوفة كائنات).
/**
 * يستخرج أخطاء الحقول من استجابة 422 (FastAPI): ``detail: [{loc:[...], msg}]`` →
 * ``[{field, msg}]`` حيث field = آخر مقطع في loc (بعد 'body'). فارغة إن لم تكن 422
 * حقليّة. تُمكّن الواجهةَ من ربط الخطأ بالحقل بدل رسالة واحدة عامّة (continuation-3 P2).
 */
export function apiFieldErrors(e: unknown): { field: string; msg: string }[] {
  const err = asApiError(e);
  const d = err.response?.data?.detail;
  if (!Array.isArray(d)) return [];
  const out: { field: string; msg: string }[] = [];
  for (const raw of d) {
    const item = raw as { loc?: unknown; msg?: unknown; message_ar?: unknown };
    const loc = Array.isArray(item.loc) ? item.loc : [];
    const segs = (loc as unknown[]).filter((s) => s !== 'body' && typeof s === 'string');
    const field = segs.length ? String(segs[segs.length - 1]) : '';
    const msg = item.msg || item.message_ar || '';
    if (msg) out.push({ field, msg: String(msg) });
  }
  return out;
}

export function apiErrorMessage(e: unknown, fallback: string): string {
  const err = asApiError(e);
  const d = err.response?.data?.detail ?? err.response?.data?.message_ar;
  if (Array.isArray(d)) {
    const msgs = d.map((x) => x?.msg || x?.message_ar || '').filter(Boolean);
    return msgs.length ? msgs.join('، ') : fallback;
  }
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') return d.message_ar || d.msg || fallback;
  if (err.response?.status === 409) {
    return 'تعارض أثناء الحفظ: غالباً يوجد حقل بنفس الاسم أو تتداخل الحدود مع حقل قائم. غيّر الاسم أو صحّح الحدود ثم أعد المحاولة.';
  }
  return err.message || fallback;
}

export interface RegisterPayload { full_name: string; email: string; password: string }
// التسجيل: الخلفيّة تُصدر توكناً مباشرةً (تسجيل دخول تلقائيّ). الدور يُثبَّت
// 'farmer' خادم-جانبيّاً (منع تصعيد الصلاحيّات) — لا يُرسَل دور من العميل.
export const register = (payload: RegisterPayload): Promise<AuthResponse> =>
  MOCK_MODE
    ? Promise.resolve({ access_token:'demo_token', refresh_token:'demo_refresh',
        user:{ username:payload.email, email:payload.email, role:'farmer', full_name:payload.full_name } } as AuthResponse)
    : authApi.post('/auth/register', payload).then(r => {
    const d = r.data as { access_token: string; refresh_token?: string | null; role?: string;
      full_name?: string; tenant_id?: string; user_id?: number };
    return {
      access_token: d.access_token,
      refresh_token: d.refresh_token ?? null,
      tenant_id: d.tenant_id,
      role: d.role,
      user_id: d.user_id,
      full_name: d.full_name ?? payload.full_name,
      user: { id: d.user_id, username: payload.email, email: payload.email, role: d.role ?? 'farmer',
        tenant_id: d.tenant_id, full_name: d.full_name ?? payload.full_name },
    } as AuthResponse;
  });

// S7 — يُبطل الخادمُ jti التوكن ويمسح كوكي البلاطات (HttpOnly) فلا يبقيان صالحَين بعد
// «الخروج». التوكن يُمرَّر صراحةً لأنّ useAuth يمسح التخزين قبل النداء (فلا يجده الـinterceptor).
// withCredentials كي يُرسَل الكوكي ويُطبَّق مسحُه عبر الأصول؛ مهلة قصيرة: أفضل-جهد لا يُعلِّق.
export const LOGOUT_TIMEOUT_MS = 5000;
export const logout = (accessToken?: string | null) =>
  tryReal(
    () =>
      authApi
        .post('/auth/logout', {}, {
          timeout: LOGOUT_TIMEOUT_MS,
          withCredentials: true,
          ...(accessToken ? { headers: { Authorization: `Bearer ${accessToken}` } } : {}),
        })
        .then(r => r.data),
    () => ({ status:'ok' }),
  );

// ── Password Reset & MFA & Change-Password ─────────────────────────
// ربط حيّ مع auth-service (لا fallback وهميّ — مسارات أمان حسّاسة). الأشكال
// تطابق services/auth/main.py تماماً. أخطاء FastAPI تُقرأ عبر apiErrorMessage.

/** طلب إعادة تعيين كلمة المرور بالبريد. الخادم يردّ دائماً برسالة موحّدة
 *  (منع تعداد البريد) — حتى لو لم يكن مسجّلاً. */
export const requestPasswordReset = (email: string): Promise<{ message: string }> =>
  authApi.post<{ message: string }>('/auth/password-reset/request', { email }).then(r => r.data);

/** تأكيد إعادة التعيين برمز من البريد + كلمة مرور جديدة. 400 لرمز غير صالح/منتهٍ. */
export const confirmPasswordReset = (
  token: string,
  newPassword: string,
): Promise<{ message: string }> =>
  authApi
    .post<{ message: string }>('/auth/password-reset/confirm', { token, new_password: newPassword })
    .then(r => r.data);

export interface MfaSetupResponse {
  secret: string;            // سرّ base32 — يُعرَض مرّة واحدة فقط
  provisioning_uri: string;  // otpauth://… (لتطبيق المصادقة / QR)
  message: string;
  // تدفّق إثبات التسجيل فقط: إثبات مرحلة التفعيل (لمرّة واحدة) وعمره بالثواني.
  // غائبان حين يبدأ الاقتران مستخدمٌ بجلسة عاديّة (SettingsPage).
  enrollment_token?: string;
  expires_in?: number;
}

/** ردّ /auth/mfa/activate: رموز الاسترداد تُعرَض مرّة واحدة فقط (لا توكنات جلسة). */
export interface MfaActivateResponse {
  message: string;
  mfa_enabled: boolean;
  recovery_codes?: string[];
  recovery_codes_notice?: string;
}

/** يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri. لا يُفعّل بعد —
 *  التفعيل يتطلّب تأكيد أوّل رمز عبر mfaActivate. (يتطلّب توكناً صالحاً) */
export const mfaSetup = (): Promise<MfaSetupResponse> =>
  authApi.post<MfaSetupResponse>('/auth/mfa/setup').then(r => r.data);

/** يفعّل MFA بعد تأكيد أوّل رمز صحيح من تطبيق المصادقة. */
export const mfaActivate = (code: string): Promise<MfaActivateResponse> =>
  authApi
    .post<MfaActivateResponse>('/auth/mfa/activate', { code })
    .then(r => r.data);

/** يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله توكن مسروق بلا الجهاز). */
export const mfaDisable = (code: string): Promise<{ message: string; mfa_enabled: boolean }> =>
  authApi
    .post<{ message: string; mfa_enabled: boolean }>('/auth/mfa/disable', { code })
    .then(r => r.data);

// ── تسجيل MFA الإلزاميّ عند الدخول (bootstrap enrollment) ─────────────
// دورٌ حسّاس بلا MFA مُفعّل: كلمة المرور الصحيحة لا تُصدِر جلسة بل 403 بجسم
// {detail, enrollment_token, expires_in, token_type:"Bearer"} (services/auth/routers/session.py).
// الإثبات صالح لـ/auth/mfa/setup وحده؛ setup يُعيد إثباتاً ثانياً لـ/auth/mfa/activate وحده.
// كلاهما لمرّة واحدة وقصير الأجل، ويبقى في ذاكرة المكوّن فقط (لا Storage، لا سجلّ).
// لا نعتمد الترويسة X-MFA-Enrollment-Required: CORS خدمة المصادقة لا يكشفها للمتصفّح.

export interface MfaEnrollmentChallenge {
  enrollment_token: string;
  expires_in?: number;  // ثوانٍ (TTL الخادم)
}

/** يستخرج تحدّي التسجيل من خطأ الدخول: 403 + enrollment_token نصّيّ غير فارغ، وإلّا null
 *  (403 عاديّ بلا إثبات يبقى خطأً عاديّاً). */
export function mfaEnrollmentChallenge(e: unknown): MfaEnrollmentChallenge | null {
  const res = asApiError(e).response;
  if (res?.status !== 403) return null;
  const data = res.data as { enrollment_token?: unknown; expires_in?: unknown } | undefined;
  const token = data?.enrollment_token;
  if (typeof token !== 'string' || !token) return null;
  const ttl = data?.expires_in;
  return {
    enrollment_token: token,
    ...(typeof ttl === 'number' && Number.isFinite(ttl) && ttl > 0 ? { expires_in: ttl } : {}),
  };
}

// تصنيف أخطاء setup/activate بالإثبات — قرار الواجهة: إعادة المحاولة أم البدء من الدخول.
//   network     لا ردّ (شبكة/مهلة) — المحاولة ممكنة؛ إن كان الإثبات استُهلك سيردّ 401 لاحقاً.
//   bad_code    400/422 في activate: رمز خاطئ (المحاولة ممكنة بنفس الإثبات).
//   restart     401/404/409: الإثبات منتهٍ/مُستهلَك أو تغيّرت حالة الحساب ⇒ سجّل الدخول مجدّداً.
//   locked      429: قفل MFA بعد محاولات فاشلة.
//   unavailable 502/503/504: Redis/التشفير/البوّابة غير متاحة.
export type MfaEnrollmentErrorKind =
  'network' | 'bad_code' | 'restart' | 'locked' | 'unavailable' | 'other';

export function classifyMfaEnrollmentError(e: unknown): MfaEnrollmentErrorKind {
  const res = asApiError(e).response;
  const status = res?.status;
  if (!res || !status) return 'network';
  if (status === 400 || status === 422) return 'bad_code';
  if (status === 401 || status === 404 || status === 409) return 'restart';
  if (status === 429) return 'locked';
  if (status === 502 || status === 503 || status === 504) return 'unavailable';
  return 'other';
}

const enrollmentProofHeaders = (proof: string) => ({ headers: { Authorization: `Bearer ${proof}` } });

/** setup بإثبات كلمة المرور (لا بتوكن جلسة). يُعيد السرّ + otpauth + إثبات التفعيل. */
export const mfaEnrollmentSetup = (setupProof: string): Promise<MfaSetupResponse> =>
  authEnrollmentApi
    .post<MfaSetupResponse>('/auth/mfa/setup', {}, enrollmentProofHeaders(setupProof))
    .then(r => r.data);

/** activate بإثبات مرحلة التفعيل + أوّل رمز TOTP. يُعيد رموز الاسترداد (مرّة واحدة). */
export const mfaEnrollmentActivate = (
  activationProof: string,
  code: string,
): Promise<MfaActivateResponse> =>
  authEnrollmentApi
    .post<MfaActivateResponse>('/auth/mfa/activate', { code }, enrollmentProofHeaders(activationProof))
    .then(r => r.data);

/** تغيير كلمة المرور لمستخدم مُصادَق (يتطلّب الحاليّة + الجديدة). */
export const changePassword = (
  currentPassword: string,
  newPassword: string,
): Promise<{ message: string }> =>
  authApi
    .post<{ message: string }>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    .then(r => r.data);

// ── Email/Phone Verification (تأكيد البريد/الهاتف — soft) ──────────
// تحقّق ناعم بعد التسجيل: المستخدم يطلب رمز OTP من ٦ أرقام (Redis قصير الأجل
// على الخادم) ثمّ يؤكّده فيُعلَّم الحساب verified_email/verified_phone. التسليم
// STUB خادميّاً (سجلّ، لا بوّابة بريد/SMS فعليّة بعد). لا fallback وهميّ.
export type VerifyChannel = 'email' | 'phone';

export interface VerificationStatus {
  verified_email: boolean;
  verified_phone: boolean;
}

/** حالة تحقّق الحساب الحاليّة (بريد/هاتف) من الخادم. (يتطلّب توكناً) */
export const getVerificationStatus = (): Promise<VerificationStatus> =>
  authApi.get<VerificationStatus>('/auth/verify/status').then(r => r.data);

/** يطلب إصدار رمز تحقّق للقناة (بريد/هاتف). محدود المعدّل خادميّاً (429). */
export const requestVerification = (
  channel: VerifyChannel,
): Promise<{ message: string; delivered: boolean; channel: VerifyChannel; expires_in: number }> =>
  authApi
    .post<{ message: string; delivered: boolean; channel: VerifyChannel; expires_in: number }>(
      '/auth/verify/request',
      { channel },
    )
    .then(r => r.data);

/** يؤكّد رمز التحقّق للقناة. 400 لرمز غير صالح/منتهٍ. */
export const confirmVerification = (
  channel: VerifyChannel,
  code: string,
): Promise<{ message: string; channel: VerifyChannel; verified: boolean }> =>
  authApi
    .post<{ message: string; channel: VerifyChannel; verified: boolean }>(
      '/auth/verify/confirm',
      { channel, code },
    )
    .then(r => r.data);

// ── دعوات أعضاء المستأجِر (انضمام بأدوار أدنى لا عبر التسجيل الذاتيّ) ─────
// ربط حيّ مع auth-service (/auth/invitations*). المالك (owner) يدعو أعضاءً بأدوار
// أدنى حصراً (expert/farmer/viewer)؛ owner/admin مرفوضان خادم-جانبيّاً (منع تصعيد).
// القبول عموميّ محميّ بالـtoken: الدور والمستأجِر يُؤخذان من صفّ الدعوة فقط (لا من
// العميل). لا fallback وهميّ — أخطاء FastAPI تُقرأ عبر apiErrorMessage.
export type InviteableRole = 'expert' | 'farmer' | 'viewer';

export interface CreateInvitationResult {
  id: number;
  email: string;
  role: string;
  tenant_id: string;
  token: string;
  accept_url: string;     // مثل /accept-invitation?token=… (يُعرَض للنسخ)
  expires_at: string;
  status: string;
}
export interface PendingInvitation {
  id: number;
  email: string;
  role: string;
  status: string;
  expires_at: string | null;
  created_at: string | null;
}

/** يُنشئ دعوة عضو لمستأجِر الداعي (owner/admin فقط). 403 لغير المخوّل،
 *  422 لدور غير قابل للدعوة (owner/admin). يُعيد الـtoken ورابط القبول للنسخ. */
export const createInvitation = (payload: {
  email: string;
  role: InviteableRole;
}): Promise<CreateInvitationResult> =>
  authApi.post<CreateInvitationResult>('/auth/invitations', payload).then(r => r.data);

/** يسرد الدعوات المعلّقة لمستأجِر الداعي (owner/admin فقط)، tenant-scoped. */
export const listInvitations = (): Promise<PendingInvitation[]> =>
  authApi.get<PendingInvitation[]>('/auth/invitations').then(r => Array.isArray(r.data) ? r.data : []);

// ── أعضاء الفريق وتغيير الأدوار (admin فقط في الخلفيّة) ──────────
// GET /auth/users و PATCH /auth/users/{id}/role محميّان بـrequire_role("admin")،
// وتغيير الدور قد يتطلّب step-up MFA (رمز TOTP حديث عبر X-MFA-Code) حسب البيئة —
// عند 403 «يتطلّب رمز MFA» تُظهر الواجهة حقل الرمز وتعيد المحاولة، لا تخمين.
export interface TeamUser {
  id: number;
  email: string;
  full_name: string | null;
  role: string;
  active: boolean;
  created_at: string | null;
  tenant_id: string | null;
}

// C-37: الخادم لا يمنح عبر PATCH /auth/users/{id}/role إلّا الأدوار الأدنى من مالك
// المستأجِر (main.is_inviteable_role)، ولا يُعدّل/يُعطّل مالكاً/مشرفاً نظيراً (403).
// فالواجهة لا تعرض غير ما يقبله الخادم، وتُعطِّل أدوات الصفوف المحميّة.
export const ASSIGNABLE_ROLE_VALUES = ['expert', 'farmer', 'viewer'] as const;
export type AssignableRole = (typeof ASSIGNABLE_ROLE_VALUES)[number];

/** هل هذا الدور قابل للتعديل/التعطيل من مسار إدارة الفريق؟ owner/admin/مجهول ⇒ false. */
export const isAssignableRole = (role: string | null | undefined): role is AssignableRole =>
  (ASSIGNABLE_ROLE_VALUES as readonly string[]).includes(role ?? '');

export const listTeamUsers = (): Promise<TeamUser[]> =>
  authApi.get<TeamUser[]>('/auth/users').then(r => (Array.isArray(r.data) ? r.data : []));

// المستخدم الحاليّ من المنصّة — GET /api/v1/me (الهويّة + المستأجر + الدور).
// يُستعمَل لتحديث الدور بعد تغييره إداريّاً بلا خروج/دخول. نطبّع الحقول
// المختلفة بين الخدمات (user_id/name_ar) إلى شكل موحّد للمتجر.
export interface CurrentUser {
  user_id?: number;
  email?: string;
  full_name?: string;
  role?: string;
  tenant_id?: string;
}

// تهيئة مستأجِر جديد + أوّل مالك (إعداد B2B، admin المنصّة فقط عبر require_role).
// لا كلمة مرور/دور من المُهيِّئ: الدور 'owner' يُفرَض خادميّاً والمالك يضبط كلمته عبر
// رمز إعادة تعيين. 409 لبريد مسجّل، 403 لغير admin — تُعرَض كما هي بصدق.
export interface TenantProvisionResult {
  tenant_id: string;
  owner_user_id: number;
  owner_email: string;
  owner_role: string;
  setup_token: string | null;
  setup_link: string | null;
  message: string;
}

export const provisionTenant = (payload: {
  owner_email: string;
  owner_full_name: string;
  tenant_name?: string;
}): Promise<TenantProvisionResult> =>
  authApi.post<TenantProvisionResult>('/auth/tenants', payload).then(r => r.data);

export const getCurrentUser = (): Promise<CurrentUser> =>
  kongApi.get<Record<string, unknown>>('/api/v1/me').then(r => {
    const d = r.data ?? {};
    return {
      user_id: (d.user_id ?? d.id) as number | undefined,
      email: (d.email ?? d.sub) as string | undefined,
      full_name: (d.full_name ?? d.name_ar) as string | undefined,
      role: d.role as string | undefined,
      tenant_id: d.tenant_id as string | undefined,
    };
  });

/** يغيّر دور مستخدم (admin + step-up MFA إن فُعِّل). الخادم يُبطل جلسات
 *  المستخدم فوراً كي يسري الدور الجديد — يُعرَض ذلك للمشغّل بصدق. */
export const changeUserRole = (
  userId: number,
  role: AssignableRole,
  mfaCode?: string,
): Promise<{ id: number; email: string; role: string }> =>
  authApi
    .patch<{ id: number; email: string; role: string }>(
      `/auth/users/${userId}/role`,
      null,
      { params: { role }, headers: mfaCode ? { 'X-MFA-Code': mfaCode } : undefined },
    )
    .then(r => r.data);

/** يعطّل حساب عضو (admin + step-up MFA إن فُعِّل). التعطيل فوريّ — الخادم
 *  يُبطل كلّ جلسات الحساب. لا يوجد مسار «إعادة تفعيل» في الخلفيّة (قرار
 *  أمنيّ: الاستعادة عبر مشغّل القاعدة) — الواجهة لا تخترع زرّاً بلا مسار. */
export const deactivateUser = (userId: number, mfaCode?: string): Promise<{ message: string }> =>
  authApi
    .patch<{ message: string }>(`/auth/users/${userId}/deactivate`, null, {
      headers: mfaCode ? { 'X-MFA-Code': mfaCode } : undefined,
    })
    .then(r => r.data);

/** قبول دعوة (عموميّ، محميّ بالـtoken): يُنشئ المستخدِم وينضمّ لمستأجِر الداعي
 *  بدوره المدعوّ، ويُصدِر توكناً (دخول تلقائيّ). 400 لرمز غير صالح/منتهٍ/مستهلَك،
 *  409 لبريد مسجّل مسبقاً. الردّ بشكل AuthResponse (مطبَّع كـlogin/register). */
export const acceptInvitation = (payload: {
  token: string;
  password: string;
  full_name: string;
}): Promise<AuthResponse> =>
  authApi.post('/auth/invitations/accept', payload).then(r => {
    const d = r.data as { access_token: string; refresh_token?: string | null; role?: string;
      full_name?: string; tenant_id?: string; user_id?: number };
    return {
      access_token: d.access_token,
      refresh_token: d.refresh_token ?? null,
      tenant_id: d.tenant_id,
      role: d.role,
      user_id: d.user_id,
      full_name: d.full_name ?? payload.full_name,
      user: { id: d.user_id, username: '', email: '', role: d.role ?? 'viewer',
        tenant_id: d.tenant_id, full_name: d.full_name ?? payload.full_name },
    } as AuthResponse;
  });

/** يلغي دعوة معلّقة (owner/admin فقط)، tenant-scoped. 404 لدعوة غير موجودة/غير معلّقة. */
export const revokeInvitation = (id: number): Promise<{ message: string; id: number }> =>
  authApi.delete<{ message: string; id: number }>(`/auth/invitations/${id}`).then(r => r.data);
