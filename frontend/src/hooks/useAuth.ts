// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — useAuth.ts (Zustand + persist)
// ═══════════════════════════════════════════════════════════════
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { login as apiLogin } from '../services/api';

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
  login: (email: string, password: string) => Promise<void>;
  loginDemo: () => void;
  logout: () => void;
  setTenant: (id: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      tenantId: null,
      user: null,
      isAuthenticated: false,
      isDemoMode: false,

      login: async (email: string, password: string) => {
        const data = await apiLogin({ username: email, password });
        const token    = data.access_token;
        const tenantId = data.user?.tenant_id || data.tenant_id || 'default';
        const user: AuthUser = {
          email: data.user?.email || email,
          full_name: data.user?.full_name,
          role: data.user?.role || data.role || 'farmer',
        };
        // حفظ في localStorage للـ interceptors
        sessionStorage.setItem('sahool_access_token', token);
        sessionStorage.setItem('sahool_tenant_id', tenantId);
        sessionStorage.setItem('sahool_user', JSON.stringify(user));
        set({ token, tenantId, user, isAuthenticated: true, isDemoMode: false });
      },

      loginDemo: () => {
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
    }),
    {
      name: 'sahool-auth',
      // استثناء الـ actions من الحفظ
      partialize: (s) => ({
        token:           s.token,
        tenantId:        s.tenantId,
        user:            s.user,
        isAuthenticated: s.isAuthenticated,
        isDemoMode:      s.isDemoMode,
      }),
    }
  )
);

// ── Helper hooks ──────────────────────────────────────────────
export const useIsAdmin = () => {
  const role = useAuthStore(s => s.user?.role);
  return role === 'admin';
};

export const useIsAuthenticated = () =>
  useAuthStore(s => s.isAuthenticated);

export const useTenantId = () =>
  useAuthStore(s => s.tenantId) || 'default';

export const useCurrentUser = () =>
  useAuthStore(s => s.user);

export const useAuthRole = () =>
  useAuthStore(s => s.user?.role || 'viewer');
