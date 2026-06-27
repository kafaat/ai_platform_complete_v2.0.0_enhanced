// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة FieldView · الشريط العلويّ السياقيّ (ContextBar)
// ───────────────────────────────────────────────────────────────
// عنوان الصفحة/الفُتات (breadcrumb) من سجلّ المسارات، مبدّل السمة (useTheme)،
// مؤشّر NATS وعلامة المستأجِر التجاريّة (سلوك مطابق لـTopBar السابق)، إضافةً
// لمحدّدات سياقيّة بسيطة (حقل/سنة/طبقة) كعناصر <select> عاديّة (لاحقاً تُوصَل
// ببيانات حقيقيّة). RTL. لا نخترع لغة بصريّة جديدة — نفس رموز اللوحة.
// ═══════════════════════════════════════════════════════════════
import { useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Menu, Wifi, WifiOff, AlertTriangle, ChevronLeft,
} from 'lucide-react';
import { useAuthStore } from '../../hooks/useAuth';
import { wsService } from '../../services/websocket';
import ThemeToggle from '../ThemeToggle';
import type { Theme } from '../../hooks/useTheme';
import { NAV_SECTIONS, pageForPath, routeForPage } from '../../lib/routes';

interface ContextBarProps {
  onMenu: () => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  // العلامة التجاريّة للمستأجِر (#206) — اختياريّة. غائبة ⇒ سلوك افتراضيّ.
  tenantName?: string | null;
  tenantLogo?: string | null;
}

// نمط موحّد لمحدّد سياقيّ بسيط (<select>) — نفس رموز اللوحة الداكنة.
const selectClass =
  'hidden lg:inline-flex text-xs rounded-xl px-3 py-2 bg-[rgb(var(--sahool-surface-2))] text-[rgb(var(--sahool-text))] border border-[rgb(var(--sahool-border))] focus:outline-none focus:border-[rgb(var(--sahool-border-focus))]';

export default function ContextBar({ onMenu, theme, setTheme, tenantName, tenantLogo }: ContextBarProps) {
  const location = useLocation();
  const { isDemoMode } = useAuthStore();
  const wsOk = wsService.isConnected();

  // الصفحة النشطة + قسمها (للفُتات) من مسار URL الحاليّ.
  const activePage = pageForPath(location.pathname);
  const route = activePage ? routeForPage(activePage) : undefined;
  const section = activePage
    ? NAV_SECTIONS.find((s) => s.items.some((i) => i.id === activePage))
    : undefined;
  const Icon = route?.icon ?? LayoutDashboard;

  return (
    <header className="flex items-center gap-3 px-4 py-3 border-b sahool-glass sahool-safe-top sticky top-0 z-30">
      <button onClick={onMenu} aria-label="فتح القائمة"
        className="md:hidden p-2 rounded-xl hover:bg-[rgb(var(--sahool-surface-2))] text-[rgb(var(--sahool-muted))]">
        <Menu className="w-5 h-5" />
      </button>

      {/* شعار المستأجِر — يُعرَض فقط عند وجود رابط فعليّ (لا صورة مكسورة). */}
      {tenantLogo && (
        <img src={tenantLogo} alt={tenantName || 'شعار المستأجِر'} loading="lazy" decoding="async"
          className="h-6 w-auto max-w-[120px] object-contain flex-shrink-0" />
      )}

      {/* الفُتات: القسم ‹ الصفحة */}
      <Icon className="w-5 h-5 text-emerald-500 flex-shrink-0" aria-hidden="true" />
      <div className="flex items-center gap-1.5 min-w-0">
        {section && (
          <>
            <span className="hidden sm:inline text-xs text-[rgb(var(--sahool-muted))] truncate">{section.label}</span>
            <ChevronLeft className="hidden sm:inline w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
          </>
        )}
        <h1 className="text-base font-bold text-[rgb(var(--sahool-text))] truncate">{route?.label ?? 'لوحة المعلومات'}</h1>
      </div>

      {/* اسم المستأجِر — يظهر بجوار العنوان فقط حين يوفّره التكوين. */}
      {tenantName && (
        <span className="hidden sm:inline text-sm text-[rgb(var(--sahool-muted))] truncate max-w-[180px]">
          · {tenantName}
        </span>
      )}

      <div className="mr-auto flex items-center gap-2">
        {/* محدّدات سياقيّة (حقل/سنة/طبقة) — عناصر مبدئيّة تُوصَل ببيانات لاحقاً. */}
        <select aria-label="الحقل" className={selectClass} defaultValue="">
          <option value="">كلّ الحقول</option>
        </select>
        <select aria-label="السنة" className={selectClass} defaultValue="2026">
          <option value="2026">٢٠٢٦</option>
          <option value="2025">٢٠٢٥</option>
        </select>
        <select aria-label="الطبقة" className={selectClass} defaultValue="ndvi">
          <option value="ndvi">NDVI</option>
          <option value="ndwi">NDWI</option>
          <option value="rgb">RGB</option>
        </select>

        {isDemoMode && (
          <span className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-amber-950 text-amber-400 border border-amber-900">
            <AlertTriangle className="w-3 h-3" /> تجريبي
          </span>
        )}
        <span className={`hidden sm:flex items-center gap-1 px-2 py-1 rounded-full text-[11px] border ${wsOk ? 'bg-emerald-950 text-emerald-400 border-emerald-900' : 'bg-slate-800 text-slate-500 border-slate-700'}`}>
          {wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
          NATS
        </span>
        <ThemeToggle theme={theme} setTheme={setTheme} />
      </div>
    </header>
  );
}
