import { useLocation } from 'react-router';
import { Menu, ChevronLeft, AlertTriangle } from 'lucide-react';
import { useAuthStore } from '../../hooks/useAuth';
import ThemeToggle from '../ThemeToggle';
import ConnectionStatus from '../ConnectionStatus';
import type { Theme } from '../../hooks/useTheme';
import { NAV_SECTIONS, pageForPath, routeForPage } from '../../lib/routes';

interface ContextBarProps {
  onMenu: () => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  tenantName?: string | null;
  tenantLogo?: string | null;
}

export default function ContextBar({ onMenu, theme, setTheme, tenantName, tenantLogo }: ContextBarProps) {
  const { pathname } = useLocation();
  const activePage = pageForPath(pathname);
  const route = activePage ? routeForPage(activePage) : undefined;
  const section = NAV_SECTIONS.find(s => s.items.some(i => i.id === activePage));
  // Demo mode must stay visible at every width: the NavRail shows it only when expanded.
  const isDemoMode = useAuthStore(s => s.isDemoMode);
  return <header className="ops-context">
    <button onClick={onMenu} aria-label="فتح القائمة" className="ops-menu-toggle ops-button"><Menu size={20} /></button>
    {tenantLogo && <img src={tenantLogo} alt={tenantName || 'شعار المزرعة'} className="ops-tenant-logo" />}
    <div className="ops-context-title">
      <p>{tenantName || 'مركز عمليات سهول'}{section && <> <ChevronLeft size={12} aria-hidden="true" /> {section.label}</>}</p>
      <h1>{route?.label ?? 'مزرعتك'}</h1>
    </div>
    <div className="ops-context-tools">{isDemoMode && <span className="ops-demo-badge" role="status"><AlertTriangle size={12} aria-hidden="true" /> تجريبي</span>}<ConnectionStatus /><ThemeToggle theme={theme} setTheme={setTheme} /></div>
  </header>;
}
