// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة FieldView · شريط التنقّل الجانبيّ (NavRail)
// ───────────────────────────────────────────────────────────────
// يُشتقّ بالكامل من سجلّ المسارات (routes.ts) لا من قوائم مكرّرة. RTL،
// مُرشَّح بـcanAccess (RBAC) و isPageEnabled (أعلام الميزات)، التمييز النشط
// عبر الراوتر (موقع المسار الحاليّ)، والتنقّل عبر navigate(path). يُصلِح خطأ
// «رؤوس المجموعات الفارغة»: قسم تُرشَّح كلّ عناصره يُخفى بالكامل.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Leaf, LogOut, User, ChevronLeft, ChevronRight, Shield, ChevronDown,
} from 'lucide-react';
import { useAuthStore } from '../../hooks/useAuth';
import { wsService } from '../../services/websocket';
import { canAccess } from '../../lib/permissions';
import { NAV_SECTIONS, ALL_ROUTES, pageForPath, maturityBadge, type RouteDef } from '../../lib/routes';
import { isPageEnabled } from '../../lib/featureFlags';

interface NavRailProps {
  collapsed: boolean;
  setCollapsed: (c: boolean) => void;
  onNavigate?: () => void; // يُستدعى بعد التنقّل (لإغلاق درج الموبايل)
}

export default function NavRail({ collapsed, setCollapsed, onNavigate }: NavRailProps) {
  const { user, logout, isDemoMode } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const wsOk = wsService.isConnected();
  // الصفحة النشطة من مسار URL الحاليّ (مصدر الحقيقة للتمييز).
  const activePage = pageForPath(location.pathname);

  const [openSections, setOpenSections] = useState<Record<string, boolean>>(
    () => Object.fromEntries(NAV_SECTIONS.map((s) => [s.id, s.defaultOpen]))
  );

  const go = (r: RouteDef) => {
    navigate(r.path);
    onNavigate?.();
  };

  // زرّ عنصر تنقّل واحد — يحفظ التمييز النشط، الشارات، ووضع الأيقونات المطويّ.
  const renderItem = (item: RouteDef) => {
    const Icon = item.icon;
    const active = activePage === item.id;
    // شارة النضج (alpha/beta) تَخلُف «جديد» العشوائيّة؛ الشارة الدلاليّة
    // (AI/WOFOST/دمج…) تبقى مكمّلةً لها حين توجد.
    const mat = maturityBadge(item.maturity);
    return (
      <button key={item.id} onClick={() => go(item)}
        title={collapsed ? item.label : undefined}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
        style={{
          background: active ? '#1e3a1e' : 'transparent',
          borderRight: active ? '2px solid #16a34a' : '2px solid transparent',
          color: active ? '#4ade80' : '#94a3b8',
        }}>
        <Icon className="w-4 h-4 flex-shrink-0" />
        {!collapsed && (
          <>
            <span className="text-sm flex-1 text-right">{item.label}</span>
            {mat && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                title={`درجة النضج: ${mat.label}`}
                style={{ background: mat.bg, color: mat.fg }}>
                {mat.label}
              </span>
            )}
            {item.badge && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                style={{ background: '#16a34a22', color: '#4ade80' }}>
                {item.badge}
              </span>
            )}
          </>
        )}
      </button>
    );
  };

  // مُرشِّح موحّد: الصفحة مُفعّلة (علم الميزة) + يحقّ للدور فتحها (RBAC).
  const allowed = (r: RouteDef) => isPageEnabled(r.id) && canAccess(user?.role, r.id);

  return (
    <aside className="flex flex-col h-full" style={{
      width: collapsed ? 64 : 240,
      background: '#0d1117',
      borderLeft: '1px solid #1e293b',
      flexShrink: 0,
      transition: 'width .3s',
    }}>
      {/* الشعار + حالة NATS */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-slate-800">
        <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center flex-shrink-0">
          <Leaf className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-emerald-400 font-bold text-sm">سهول</div>
            <div className="flex items-center gap-1 text-[10px]">
              <span className={`w-1.5 h-1.5 rounded-full ${wsOk ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
              <span className="text-slate-500">{wsOk ? 'NATS متصل' : 'offline'}</span>
            </div>
          </div>
        )}
        <button onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'توسيع الشريط الجانبيّ' : 'طيّ الشريط الجانبيّ'}
          className="p-1 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-slate-300">
          {collapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* شارة الوضع التجريبيّ */}
      {isDemoMode && !collapsed && (
        <div className="mx-2 mt-2 px-2 py-1 rounded text-[10px] text-amber-400 text-center"
          style={{ background: '#2a1a00', border: '1px solid #f59e0b44' }}>
          ⚠️ وضع تجريبي
        </div>
      )}

      {/* التنقّل — مُرشَّح حسب الدور وعلم الميزة (لا تظهر صفحة محجوبة).
          مطويّ: كلّ العناصر المسموح بها كأيقونات (بلا رؤوس أقسام).
          مفتوح: أقسام قابلة للطيّ؛ قسم بلا عناصر مسموح بها يُخفى بالكامل. */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {collapsed
          ? ALL_ROUTES.filter(allowed).map(renderItem)
          : NAV_SECTIONS.map((section) => {
              const items = section.items.filter(allowed);
              if (items.length === 0) return null; // إخفاء القسم الفارغ (إصلاح الخطأ)
              const open = openSections[section.id];
              return (
                <div key={section.id} className="pt-1">
                  <button
                    onClick={() => setOpenSections((s) => ({ ...s, [section.id]: !s[section.id] }))}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-slate-500 hover:text-slate-300 transition-colors">
                    <span className="text-[11px] font-semibold tracking-wide flex-1 text-right">{section.label}</span>
                    <ChevronDown className="w-3.5 h-3.5 transition-transform"
                      style={{ transform: open ? 'rotate(0deg)' : 'rotate(-90deg)' }} />
                  </button>
                  {open && (
                    <div className="space-y-0.5 mt-0.5">
                      {items.map(renderItem)}
                    </div>
                  )}
                </div>
              );
            })}
      </nav>

      {/* المستخدم */}
      {!collapsed && (
        <div className="px-3 py-4 border-t border-slate-800">
          <div className="flex items-center gap-2 px-2 py-2 rounded-lg" style={{ background: '#1e293b' }}>
            <div className="w-7 h-7 rounded-full bg-emerald-700 flex items-center justify-center flex-shrink-0">
              <User className="w-3.5 h-3.5 text-emerald-300" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-slate-200 truncate">{user?.full_name || user?.email || 'مستخدم'}</div>
              <div className="text-[10px] text-slate-500 flex items-center gap-1">
                <Shield className="w-2.5 h-2.5" />{user?.role || 'farmer'}
              </div>
            </div>
            <button onClick={logout} title="خروج"
              className="p-1 hover:text-red-400 text-slate-500 transition-colors">
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
