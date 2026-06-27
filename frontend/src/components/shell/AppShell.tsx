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
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import type { Theme } from '../../hooks/useTheme';
import NavRail from './NavRail';
import ContextBar from './ContextBar';
import MobileTabBar from './MobileTabBar';
import CommandPalette from './CommandPalette';

interface AppShellProps {
  theme: Theme;
  setTheme: (t: Theme) => void;
  tenantName?: string | null;
  tenantLogo?: string | null;
  children: ReactNode;
}

export default function AppShell({ theme, setTheme, tenantName, tenantLogo, children }: AppShellProps) {
  const location = useLocation();
  const reduce = useReducedMotion();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // إغلاق درج الموبايل عند تغيّر المسار (تنقّل ناجح).
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: 'rgb(var(--sahool-bg))' }}>
      <div className="flex flex-1 overflow-hidden">
        {/* شريط التنقّل الثابت — سطح المكتب */}
        <div className="hidden md:flex">
          <NavRail collapsed={collapsed} setCollapsed={setCollapsed} />
        </div>

        {/* درج التنقّل — الموبايل */}
        {mobileOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} />
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
          <main className="flex-1 overflow-y-auto sahool-safe-bottom" style={{ padding: 'var(--sahool-page-pad)' }}>
            {/* انتقال صفحة لطيف (تلاشٍ/انزلاق) مفتاحه مسار URL — مع mode="wait"
                كي يخرج القديم قبل دخول الجديد. يحترم prefers-reduced-motion
                (يُلغى التحريك تماماً، فيبقى التبديل فوريّاً بلا حركة). */}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={location.pathname}
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
                animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
                transition={{ duration: reduce ? 0 : 0.18, ease: 'easeOut' }}
              >
                {children}
              </motion.div>
            </AnimatePresence>
          </main>
        </div>
      </div>

      {/* لوحة الأوامر (⌘K) — تُدار حالتها داخليّاً، تُفتح عالميّاً. */}
      <CommandPalette />

      {/* الشريط السفليّ — الموبايل فقط */}
      <MobileTabBar />
    </div>
  );
}
