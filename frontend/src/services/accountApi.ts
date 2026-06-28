// ═══════════════════════════════════════════════════════════════
// accountApi.ts — دوالّ مجال المصادقة/الحساب (مُستخرَجة من api.ts)
// تسجيل الدخول/الخروج/التسجيل · إعادة تعيين كلمة المرور · MFA · تغيير كلمة
// المرور · تحقّق البريد/الهاتف · دعوات أعضاء المستأجِر · تكوين المستأجِر.
// وحدة ورقة (leaf module): تستورد العملاء من ./apiClients (authApi, kongApi,
// MOCK_MODE) بلا دورة استيراد. api.ts يعيد التصدير عبر `export *` فيبقى كلّ
// import من '.../services/api' يعمل دون تغيير. السلوك محفوظ: نسخ حرفيّ للدوالّ.
// مُعالِجات الأخطاء العامّة (asApiError/apiErrorMessage/isMfaRequiredError)
// تبقى في api.ts لأنّها مقطعيّة (cross-cutting) تستهلكها دوالّ أخرى هناك.
// ═══════════════════════════════════════════════════════════════

import { authApi, kongApi, MOCK_MODE, tryReal } from './apiClients';

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

export const logout = () =>
  tryReal(() => authApi.post('/auth/logout').then(r => r.data), () => ({ status:'ok' }));

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
}

/** يبدأ اقتران MFA: يولّد سرّاً ويُعيد provisioning_uri. لا يُفعّل بعد —
 *  التفعيل يتطلّب تأكيد أوّل رمز عبر mfaActivate. (يتطلّب توكناً صالحاً) */
export const mfaSetup = (): Promise<MfaSetupResponse> =>
  authApi.post<MfaSetupResponse>('/auth/mfa/setup').then(r => r.data);

/** يفعّل MFA بعد تأكيد أوّل رمز صحيح من تطبيق المصادقة. */
export const mfaActivate = (code: string): Promise<{ message: string; mfa_enabled: boolean }> =>
  authApi
    .post<{ message: string; mfa_enabled: boolean }>('/auth/mfa/activate', { code })
    .then(r => r.data);

/** يعطّل MFA — يتطلّب رمزاً صحيحاً حاليّاً (لا يُعطّله توكن مسروق بلا الجهاز). */
export const mfaDisable = (code: string): Promise<{ message: string; mfa_enabled: boolean }> =>
  authApi
    .post<{ message: string; mfa_enabled: boolean }>('/auth/mfa/disable', { code })
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
): Promise<{ message: string; channel: VerifyChannel; expires_in: number }> =>
  authApi
    .post<{ message: string; channel: VerifyChannel; expires_in: number }>(
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

// ── Tenant Config (#206): تكوين المستأجِر للعلامة التجاريّة + الوحدات/اللغة ──
// GET /api/v1/tenant/config → {branding:{logo_url, primary_color, name_ar}, units,
// language, crops}. الحقول كلّها اختياريّة/قد تكون null (الافتراضيّ): الواجهة
// تتجاهل أيّ حقل غائب وتُبقي سلوكها الحاليّ. أفضل-جهد: عند أيّ خطأ نُرجِع null
// (لا fallback مُفبرَك، ولا كسر) فتعمل الواجهة بالافتراضيّات كما هي اليوم.
export interface TenantBranding {
  logo_url:      string | null;
  primary_color: string | null;
  name_ar:       string | null;
}
export interface TenantConfig {
  branding: TenantBranding | null;
  units:    string | null;
  language: string | null;
  crops:    string[] | null;
}

/** يجلب تكوين المستأجِر (#206). أفضل-جهد: أيّ خطأ/استجابة غير صالحة ⇒ null
 *  فتُبقي الواجهة الافتراضيّات (لا كسر، لا علامة تجاريّة مُفبرَكة). */
export const fetchTenantConfig = (): Promise<TenantConfig | null> =>
  kongApi
    .get<TenantConfig>('/api/v1/tenant/config')
    .then((r) => (r.data && typeof r.data === 'object' ? r.data : null))
    .catch(() => null);
