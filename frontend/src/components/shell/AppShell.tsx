// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة FieldView · الهيكل (AppShell)
// ───────────────────────────────────────────────────────────────
// يجمع شريط التنقّل (NavRail) + الشريط العلويّ السياقيّ (ContextBar) +
// الشريط السفليّ للموبايل (MobileTabBar) حول المحتوى (children = جدول
// <Routes>). يحلّ محلّ Sidebar+TopBar القديمين. RTL، نفس رموز اللوحة.
// التنقّل كلّه عبر الراوتر؛ يُغلَق درج الموبايل عند تغيّر المسار.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import type { Theme } from '../../hooks/useTheme';
import NavRail from './NavRail';
import ContextBar from './ContextBar';
import MobileTabBar from './MobileTabBar';

interface AppShellProps {
  theme: Theme;
  setTheme: (t: Theme) => void;
  tenantName?: string | null;
  tenantLogo?: string | null;
  children: ReactNode;
}

export default function AppShell({ theme, setTheme, tenantName, tenantLogo, children }: AppShellProps) {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // إغلاق درج الموبايل عند تغيّر المسار (تنقّل ناجح).
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: '#0f1117' }}>
      <div className="flex flex-1 overflow-hidden">
        {/* شريط التنقّل الثابت — سطح المكتب */}
        <div className="hidden md:flex">
          <NavRail collapsed={collapsed} setCollapsed={setCollapsed} />
        </div>

        {/* درج التنقّل — الموبايل */}
        {mobileOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/60 md:hidden" onClick={() => setMobileOpen(false)} />
            <div className="fixed right-0 top-0 h-full z-50 md:hidden">
              <NavRail collapsed={false} setCollapsed={() => {}} onNavigate={() => setMobileOpen(false)} />
            </div>
          </>
        )}

        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <ContextBar
            onMenu={() => setMobileOpen((v) => !v)}
            theme={theme} setTheme={setTheme}
            tenantName={tenantName} tenantLogo={tenantLogo}
          />
          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            {children}
          </main>
        </div>
      </div>

      {/* الشريط السفليّ — الموبايل فقط */}
      <MobileTabBar />
    </div>
  );
}
