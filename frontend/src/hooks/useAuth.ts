// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — useAuth.ts (Zustand + persist)
// ═══════════════════════════════════════════════════════════════
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { login as apiLogin, register as apiRegister, acceptInvitation as apiAcceptInvitation, getCurrentUser as apiGetCurrentUser } from '../services/api';

interface AuthUser {
  id?: number;
  email: string;
  full_name?: string;
  role: string;
  tenant_id?: string;
}

interface AuthState {
  token: string | null;
  tenantId: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  isDemoMode: boolean;
  // Actions
  login: (email: string, password: string, mfaCode?: string) => Promise<void>;
  signup: (data: { full_name: string; email: string; password: string }) => Promise<void>;
  acceptInvite: (data: { token: string; password: string; full_name: string }) => Promise<void>;
  loginDemo: () => void;
  logout: () => void;
  setTenant: (id: string) => void;
  // يُعيد قراءة المستخدم الحاليّ من الخادم (GET /api/v1/me) — يُحدّث الدور بعد
  // تغييره إداريّاً (يكمّل «أعضاء الفريق والأدوار»: الخادم يُبطل الجلسة، وهذا
  // يجلب الدور الجديد فوراً بلا خروج/دخول). لا يُغيّر شيئاً في وضع التجريب.
  refreshUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      tenantId: null,
      user: null,
      isAuthenticated: false,
      isDemoMode: false,

      login: async (email: string, password: string, mfaCode?: string) => {
        // mfaCode اختياريّ — يُمرَّر فقط للحسابات المُفعّل لها MFA. الخادم يرفض
        // بـ401 + X-MFA-Required إن لزم رمز ولم يُرسَل (يلتقطه LoginPage).
        const data = await apiLogin({ email, password, ...(mfaCode ? { mfa_code: mfaCode } : {}) });
        const token    = data.access_token;
        // Fail-closed (forensic F-01): never fabricate a 'default' tenant from a malformed
        // auth response — reject the login so the app cannot enter a bogus tenant context.
        const tenantId = data.user?.tenant_id || data.tenant_id;
        if (!token || !tenantId) throw new Error('auth response missing token or tenant identity');
        const user: AuthUser = {
          id: data.user?.id,
          email: data.user?.email || email,
          full_name: data.user?.full_name,
          role: data.user?.role || data.role || 'farmer',
        };
        // التوكن في sessionStorage فقط (لا localStorage) — يقرؤه الـ interceptor.
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', tenantId);
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ token, tenantId, user, isAuthenticated: true, isDemoMode: false });
      },

      signup: async (data: { full_name: string; email: string; password: string }) => {
        // تسجيل حقيقيّ → توكن مباشر (دخول تلقائيّ). الدور دائماً farmer خادم-جانبيّاً.
        const res = await apiRegister(data);
        const token    = res.access_token;
        const tenantId = res.user?.tenant_id || res.tenant_id;
        if (!token || !tenantId) throw new Error('registration response missing token or tenant identity');
        const user: AuthUser = {
          id: res.user?.id,
          email: res.user?.email || data.email,
          full_name: res.user?.full_name || data.full_name,
          role: res.user?.role || res.role || 'farmer',
          tenant_id: tenantId,
        };
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', tenantId);
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ token, tenantId, user, isAuthenticated: true, isDemoMode: false });
      },

      acceptInvite: async (data: { token: string; password: string; full_name: string }) => {
        // قبول دعوة → توكن مباشر (دخول تلقائيّ). الدور والمستأجِر من صفّ الدعوة
        // خادم-جانبيّاً (لا يختارهما العميل) — العضو ينضمّ لمستأجِر الداعي بدوره المدعوّ.
        const res = await apiAcceptInvitation(data);
        const token    = res.access_token;
        const tenantId = res.user?.tenant_id || res.tenant_id;
        if (!token || !tenantId) throw new Error('invitation response missing token or tenant identity');
        const user: AuthUser = {
          id: res.user?.id,
          email: res.user?.email || '',
          full_name: res.user?.full_name || data.full_name,
          role: res.user?.role || res.role || 'viewer',
          tenant_id: tenantId,
        };
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', tenantId);
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ token, tenantId, user, isAuthenticated: true, isDemoMode: false });
      },

      loginDemo: () => {
        // Fail-closed (forensic P0): the demo session must be unreachable in production builds.
        if (import.meta.env.PROD) {
          throw new Error('demo login is disabled in production');
        }
        const token    = 'demo_token_not_real';
        const tenantId = 'demo_tenant';
        // أمان: وضع التجريب يستخدم farmer لا admin (منع صلاحيات زائفة)
        const user: AuthUser = { email: 'demo@sahool.ye', full_name: 'مستخدم تجريبي', role: 'farmer' };
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', tenantId);
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ token, tenantId, user, isAuthenticated: true, isDemoMode: true });
      },

      logout: () => {
        sessionStorage.removeItem('sahool_access_token');
        sessionStorage.removeItem('sahool_tenant_id');
        sessionStorage.removeItem('sahool_user');
        set({ token: null, tenantId: null, user: null, isAuthenticated: false, isDemoMode: false });
      },

      setTenant: (id: string) => {
        sessionStorage.setItem('sahool_tenant_id', id);
        set({ tenantId: id });
      },

      refreshUser: async () => {
        // وضع التجريب لا خادم له — لا نلمس الحالة (تفادي مسح مستخدم تجريبيّ).
        if (get().isDemoMode || !get().token) return;
        const me = await apiGetCurrentUser();
        const prev = get().user;
        const user: AuthUser = {
          id: me.user_id ?? prev?.id,
          email: me.email ?? prev?.email ?? '',
          full_name: me.full_name ?? prev?.full_name,
          role: me.role ?? prev?.role ?? 'farmer',
          tenant_id: me.tenant_id ?? prev?.tenant_id,
        };
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ user, tenantId: me.tenant_id ?? get().tenantId });
      },
    }),
    {
      name: 'sahool-auth',
      // FIX (مراجعة #241): التوكن يُكتَب في sessionStorage (جلسة لكلّ تبويب)، لكنّ
      // persist الافتراضيّ يحفظ الحالة في localStorage — فيُعاد ترطيب
      // isAuthenticated=true في تبويب جديد بينما sessionStorage فارغ (لا توكن)،
      // فيظهر المستخدم مُصادَقاً بلا توكن حتى أوّل 401. توحيد التخزين على
      // sessionStorage يجعل عمر حالة المصادقة مطابقاً لعمر التوكن (نفس التبويب)،
      // ويُلغي أيضاً قلق #236 من تسريب التوكن لـlocalStorage (الكلّ session-scoped).
      storage: createJSONStorage(() => sessionStorage),
      // استثناء الـ actions من الحفظ
      partialize: (s) => ({
        token:           s.token,
        tenantId:        s.tenantId,
        user:            s.user,
        isAuthenticated: s.isAuthenticated,
        isDemoMode:      s.isDemoMode,
      }),
      // ضمان تطابق token/isAuthenticated مع المفتاح القانونيّ (#236): التوكن مصدر
      // الحقيقة في sessionStorage['sahool_access_token']؛ نُعيد المزامنة عند الترطيب.
      onRehydrateStorage: () => (state) => {
        if (!state) return;
        const t = sessionStorage.getItem('sahool_access_token');
        state.token = t;
        state.isAuthenticated = !!t;
      },
    }
  )
);

// ── Helper hooks ──────────────────────────────────────────────
export const useIsAuthenticated = () =>
  useAuthStore(s => s.isAuthenticated);

export const useTenantId = () =>
  useAuthStore(s => s.tenantId) || 'default';

export const useCurrentUser = () =>
  useAuthStore(s => s.user);

export const useAuthRole = () =>
  useAuthStore(s => s.user?.role || 'viewer');
