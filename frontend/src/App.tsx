// SAHOOL v8.0 — App.tsx (النهائية)
import { useState, useEffect, Suspense, lazy } from 'react';
import {
  LayoutDashboard, Satellite, Map, BarChart3, Bell,
  FileText, Bot, Settings, Loader2, Leaf, LogOut,
  User, ChevronLeft, ChevronRight, Shield, AlertTriangle,
  Wifi, WifiOff, ClipboardList, Droplets, Bug, Activity,
  Boxes, Tractor, Cpu, Waypoints, Database, FolderArchive,
  ShieldCheck, Sprout, CloudRain, Smartphone, Layers, ListChecks, TrendingUp,
  ChevronDown,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuthStore } from './hooks/useAuth';
import { useFarms } from './hooks/useApi';
import { useTenantConfig } from './hooks/useTenantConfig';
import { useTheme, type Theme } from './hooks/useTheme';
import { wsService } from './services/websocket';
import ToastContainer from './components/ToastContainer';
import ThemeToggle from './components/ThemeToggle';
import { canAccess, canCreateFarm } from './lib/permissions';
import { LoadingState } from './components/StateViews';

// ── Error Boundary ──────────────────────────────────────────
import React from 'react';
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: undefined };
  }
  static getDerivedStateFromError(error: Error) { return { hasError: true, error }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) { console.error('SAHOOL Error:', error, info); }
  render() {
    if (this.state.hasError) return (
      <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',
        height:'100vh',background:'#0f1117',color:'#fff',gap:16}}>
        <div style={{fontSize:48}}>🌿</div>
        <h2>حدث خطأ غير متوقع</h2>
        <p style={{color:'#9ca3af'}}>{this.state.error?.message}</p>
        <button onClick={() => window.location.reload()}
          style={{padding:'8px 16px',background:'#10b981',border:'none',borderRadius:8,color:'#fff',cursor:'pointer'}}>
          إعادة التحميل
        </button>
      </div>
    );
    return this.props.children;
  }
}


const LoginPage           = lazy(() => import('./pages/LoginPage'));
const SignupPage          = lazy(() => import('./pages/SignupPage'));
const DashboardPage       = lazy(() => import('./sections/DashboardPage'));
const SatellitePage       = lazy(() => import('./sections/SatellitePage'));
const FieldManagementPage = lazy(() => import('./sections/FieldManagementPage'));
const AnalyticsPage       = lazy(() => import('./sections/AnalyticsPage'));
const AlertSystemPage     = lazy(() => import('./sections/AlertSystemPage'));
const ReportsPage         = lazy(() => import('./sections/ReportsPage'));
const ChatbotPage         = lazy(() => import('./sections/ChatbotPage').then(m => ({ default: m.ChatbotPage })));
const HybridIndexPage     = lazy(() => import('./sections/HybridIndexPage').then(m => ({ default: m.HybridIndexPage })));
const SettingsPage        = lazy(() => import('./sections/SettingsPage'));
const TasksPage           = lazy(() => import('./sections/TasksPage'));
const ActivitiesPage      = lazy(() => import('./sections/ActivitiesPage'));
const RecommendationPage  = lazy(() => import('./sections/RecommendationPage'));
const SpatialIndicatorsPage = lazy(() => import('./sections/SpatialIndicatorsPage'));
const IrrigationWaterPage = lazy(() => import('./sections/IrrigationWaterPage'));
const PestEscalationPage  = lazy(() => import('./sections/PestEscalationPage'));
const FieldIntelligencePage = lazy(() => import('./sections/FieldIntelligencePage'));
const InventoryPage       = lazy(() => import('./sections/InventoryPage'));
const EquipmentPage       = lazy(() => import('./sections/EquipmentPage'));
const DevicesPage         = lazy(() => import('./sections/DevicesPage'));
const IrrigationOpsPage   = lazy(() => import('./sections/IrrigationOpsPage'));
const WeatherAdvicePage   = lazy(() => import('./sections/WeatherAdvicePage'));
const MasterDataPage      = lazy(() => import('./sections/MasterDataPage'));
const DocumentsPage       = lazy(() => import('./sections/DocumentsPage'));
const GovernancePage      = lazy(() => import('./sections/GovernancePage'));
const FarmCreatePage      = lazy(() => import('./sections/FarmCreatePage'));
const FieldAppPreview     = lazy(() => import('./sections/FieldAppPreview'));
const OperationCommand    = lazy(() => import('./sections/OperationCommand'));
const FieldMapCenter      = lazy(() => import('./sections/FieldMapCenter'));
const FieldTasksCabin     = lazy(() => import('./sections/FieldTasksCabin'));
const RecommendationFlow  = lazy(() => import('./sections/RecommendationFlow'));
const HybridMonitor       = lazy(() => import('./sections/HybridMonitor'));
const AnalyzeCabin        = lazy(() => import('./sections/AnalyzeCabin'));
const SetupCabin          = lazy(() => import('./sections/SetupCabin'));
const UnifiedCabin        = lazy(() => import('./sections/UnifiedCabin'));
const FieldRanking        = lazy(() => import('./sections/FieldRanking'));
const ProblemFields       = lazy(() => import('./sections/ProblemFields'));
const EconomicsDashboard  = lazy(() => import('./sections/EconomicsDashboard'));
const PhenologyView       = lazy(() => import('./sections/PhenologyView'));
const ScoutingView        = lazy(() => import('./sections/ScoutingView'));
const FarmAdvisoryReport  = lazy(() => import('./sections/FarmAdvisoryReport'));

export type PageId =
  | 'dashboard' | 'hybrid-index' | 'satellite' | 'fields'
  | 'analytics' | 'alerts' | 'reports' | 'chatbot'
  | 'tasks' | 'settings' | 'recommendations' | 'spatial-indicators'
  | 'irrigation' | 'pest-escalation' | 'field-intelligence'
  | 'inventory' | 'equipment' | 'devices' | 'irrigation-ops'
  | 'activities' | 'master-data' | 'documents' | 'governance'
  | 'weather-advice' | 'field-app' | 'command' | 'map-center' | 'tasks-cabin' | 'rec-flow' | 'hybrid-monitor' | 'analyze-cabin' | 'setup-cabin' | 'unified-cabin' | 'field-ranking' | 'problem-fields' | 'economics' | 'phenology' | 'scouting' | 'advisory-report';

type NavItem = { id: PageId; label: string; icon: LucideIcon; badge?: string };
type NavGroup = { id: string; label: string; defaultOpen: boolean; items: NavItem[] };

const NAV_GROUPS: NavGroup[] = [
  {
    id: 'home', label: 'الرئيسية', defaultOpen: true,
    items: [
      { id:'dashboard',    label:'لوحة المعلومات', icon:LayoutDashboard },
      { id:'alerts',       label:'التنبيهات',       icon:Bell },
      { id:'chatbot',      label:'المستشار الذكي',  icon:Bot, badge:'AI' },
      { id:'reports',      label:'التقارير',        icon:FileText },
    ],
  },
  {
    id: 'unified', label: 'التطبيق الموحّد (معاينة)', defaultOpen: true,
    items: [
      { id:'unified-cabin', label:'التطبيق الموحّد (معاينة)', icon:Smartphone, badge:'٦ وجهات' },
      { id:'command',      label:'مركز العمليّات (معاينة)', icon:Smartphone, badge:'دمج' },
      { id:'map-center',   label:'مركز الخرائط (معاينة)', icon:Layers, badge:'دمج' },
      { id:'tasks-cabin',  label:'كابينة المهام (معاينة)', icon:ListChecks, badge:'دمج' },
      { id:'rec-flow',     label:'توصية ← تنفيذ (معاينة)', icon:ClipboardList, badge:'دمج' },
      { id:'hybrid-monitor', label:'المراقبة الهجينة (معاينة)', icon:Activity, badge:'دمج' },
      { id:'analyze-cabin', label:'التحليل (معاينة)', icon: BarChart3, badge:'دمج' },
      { id:'setup-cabin', label:'الإعداد (معاينة)', icon: Settings, badge:'دمج' },
      { id:'field-app',    label:'تطبيق الحقل (معاينة)', icon:Smartphone, badge:'جديد' },
    ],
  },
  {
    id: 'fields-sat', label: 'الحقول والأقمار', defaultOpen: false,
    items: [
      { id:'fields',       label:'إدارة الحقول',   icon:Map },
      { id:'satellite',    label:'الأقمار الصناعية', icon:Satellite },
      { id:'hybrid-index', label:'المؤشرات (17)',  icon:BarChart3, badge:'WOFOST' },
      { id:'spatial-indicators', label:'المؤشرات المكانية', icon:Map },
    ],
  },
  {
    id: 'agri', label: 'الزراعة والري', defaultOpen: false,
    items: [
      { id:'irrigation',   label:'تحليل ماء الريّ', icon:Droplets },
      { id:'weather-advice', label:'الطقس والريّ',  icon:CloudRain },
      { id:'irrigation-ops', label:'الري التشغيلي', icon:Waypoints },
      { id:'pest-escalation', label:'تصعيد الآفة',  icon:Bug },
      { id:'phenology',    label:'مراحل النموّ',     icon:Sprout },
      { id:'scouting',     label:'دليل الاستكشاف',   icon:Bug },
      { id:'field-intelligence', label:'المايسترو', icon:Activity },
    ],
  },
  {
    id: 'analysis', label: 'التحليل والتقارير', defaultOpen: false,
    items: [
      { id:'analytics',    label:'التحليلات',       icon:BarChart3 },
      { id:'economics',    label:'الاقتصاد / ROI',   icon:BarChart3 },
      { id:'field-ranking', label:'ترتيب الحقول',    icon:TrendingUp },
      { id:'problem-fields', label:'حقول المشكلات',   icon:AlertTriangle },
      { id:'advisory-report', label:'استشارة المزرعة', icon: FileText },
      { id:'recommendations', label:'التوصيات',    icon:ClipboardList },
    ],
  },
  {
    id: 'operations', label: 'التشغيل', defaultOpen: false,
    items: [
      { id:'tasks',        label:'المهام الميدانية',icon:ClipboardList },
      { id:'activities',   label:'العمليّات الزراعيّة', icon:Sprout },
      { id:'inventory',    label:'المخزون',         icon:Boxes },
      { id:'equipment',    label:'المعدّات',         icon:Tractor },
      { id:'devices',      label:'أجهزة IoT',       icon:Cpu },
    ],
  },
  {
    id: 'admin', label: 'الإدارة', defaultOpen: false,
    items: [
      { id:'master-data',  label:'البيانات المرجعيّة', icon:Database },
      { id:'documents',    label:'الوثائق',         icon:FolderArchive },
      { id:'governance',   label:'الحوكمة والتدقيق', icon:ShieldCheck },
      { id:'settings',     label:'الإعدادات',       icon:Settings },
    ],
  },
];

// قائمة مُسطّحة لكل العناصر — للبحث عن العنوان/الأيقونة في TopBar عبر كل المجموعات.
const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap(g => g.items);

function Loader() {
  return (
    <ErrorBoundary>
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
    </div>
  </ErrorBoundary>
  );
}

interface SidebarProps {
  page: PageId;
  setPage: (p: PageId) => void;
  collapsed: boolean;
  setCollapsed: (c: boolean) => void;
}

function Sidebar({ page, setPage, collapsed, setCollapsed }: SidebarProps) {
  const { user, logout, isDemoMode } = useAuthStore();
  const wsOk = wsService.isConnected();
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(
    () => Object.fromEntries(NAV_GROUPS.map(g => [g.id, g.defaultOpen]))
  );

  // زرّ عنصر التنقّل — يحافظ على التمييز النشط، الشارات، ووضع الأيقونات المطويّ.
  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const active = page === item.id;
    return (
      <button key={item.id} onClick={() => setPage(item.id)}
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
            {item.badge && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                style={{ background:item.badge==='2'||item.badge==='6'?'#dc262622':'#16a34a22',
                  color:item.badge==='2'||item.badge==='6'?'#f87171':'#4ade80' }}>
                {item.badge}
              </span>
            )}
          </>
        )}
      </button>
    );
  };

  return (
    <ErrorBoundary>
    <aside className="flex flex-col h-full" style={{
      width: collapsed ? 64 : 240,
      background:'#0d1117',
      borderLeft:'1px solid #1e293b',
      flexShrink: 0,
      transition: 'width .3s',
    }}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-slate-800">
        <div className="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center flex-shrink-0">
          <Leaf className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-emerald-400 font-bold text-sm">سهول</div>
            <div className="flex items-center gap-1 text-[10px]">
              <span className={`w-1.5 h-1.5 rounded-full ${wsOk?'bg-emerald-400 animate-pulse':'bg-slate-600'}`} />
              <span className="text-slate-500">{wsOk?'NATS متصل':'offline'}</span>
            </div>
          </div>
        )}
        <button onClick={() => setCollapsed(!collapsed)}
          className="p-1 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-slate-300">
          {collapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* Demo badge */}
      {isDemoMode && !collapsed && (
        <div className="mx-2 mt-2 px-2 py-1 rounded text-[10px] text-amber-400 text-center"
          style={{ background:'#2a1a00', border:'1px solid #f59e0b44' }}>
          ⚠️ وضع تجريبي
        </div>
      )}

      {/* Nav — مُرشَّح حسب صلاحيّة الدور (RBAC فعليّ: لا تظهر صفحة لا يحقّ فتحها).
          مطويّ: كل العناصر المسموح بها كأيقونات (بلا رؤوس مجموعات).
          مفتوح: مجموعات قابلة للطيّ؛ مجموعة بلا عناصر مسموح بها تُخفى بالكامل. */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {collapsed
          ? NAV_ITEMS.filter(item => canAccess(user?.role, item.id)).map(renderItem)
          : NAV_GROUPS.map(group => {
              const items = group.items.filter(item => canAccess(user?.role, item.id));
              if (items.length === 0) return null;
              const open = openGroups[group.id];
              return (
                <div key={group.id} className="pt-1">
                  <button
                    onClick={() => setOpenGroups(s => ({ ...s, [group.id]: !s[group.id] }))}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-slate-500 hover:text-slate-300 transition-colors">
                    <span className="text-[11px] font-semibold tracking-wide flex-1 text-right">{group.label}</span>
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

      {/* User */}
      {!collapsed && (
        <div className="px-3 py-4 border-t border-slate-800">
          <div className="flex items-center gap-2 px-2 py-2 rounded-lg" style={{ background:'#1e293b' }}>
            <div className="w-7 h-7 rounded-full bg-emerald-700 flex items-center justify-center flex-shrink-0">
              <User className="w-3.5 h-3.5 text-emerald-300" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-slate-200 truncate">{user?.full_name||user?.email||'مستخدم'}</div>
              <div className="text-[10px] text-slate-500 flex items-center gap-1">
                <Shield className="w-2.5 h-2.5" />{user?.role||'farmer'}
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
    </ErrorBoundary>
  );
}

interface TopBarProps {
  page: PageId;
  onMenu: () => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  // العلامة التجاريّة للمستأجِر (#206) — اختياريّة. غائبة ⇒ سلوك افتراضيّ كما اليوم.
  tenantName?: string | null;
  tenantLogo?: string | null;
}

function TopBar({ page, onMenu, theme, setTheme, tenantName, tenantLogo }: TopBarProps) {
  const item = NAV_ITEMS.find(n => n.id === page);
  const Icon = item?.icon || LayoutDashboard;
  const { isDemoMode } = useAuthStore();
  const wsOk = wsService.isConnected();

  return (
    <ErrorBoundary>
    <header className="flex items-center gap-3 px-4 py-3 border-b"
      style={{ background:'#0d1117', borderColor:'#1e293b' }}>
      <button onClick={onMenu} className="md:hidden p-2 rounded-lg hover:bg-slate-800 text-slate-400">
        <LayoutDashboard className="w-5 h-5" />
      </button>
      {/* شعار المستأجِر — يُعرَض فقط عند وجود رابط فعليّ (لا صورة مكسورة عند null). */}
      {tenantLogo && (
        <img src={tenantLogo} alt={tenantName || 'شعار المستأجِر'}
          className="h-6 w-auto max-w-[120px] object-contain flex-shrink-0" />
      )}
      <Icon className="w-5 h-5 text-emerald-500" />
      <h1 className="text-base font-bold text-slate-100">{item?.label}</h1>
      {/* اسم المستأجِر — يظهر بجوار العنوان فقط حين يوفّره التكوين. */}
      {tenantName && (
        <span className="hidden sm:inline text-sm text-slate-400 truncate max-w-[180px]">
          · {tenantName}
        </span>
      )}
      <div className="mr-auto flex items-center gap-2">
        {isDemoMode && (
          <span className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-amber-950 text-amber-400 border border-amber-900">
            <AlertTriangle className="w-3 h-3" /> تجريبي
          </span>
        )}
        <span className={`hidden sm:flex items-center gap-1 px-2 py-1 rounded-full text-[11px] border ${wsOk?'bg-emerald-950 text-emerald-400 border-emerald-900':'bg-slate-800 text-slate-500 border-slate-700'}`}>
          {wsOk ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
          NATS
        </span>
        <ThemeToggle theme={theme} setTheme={setTheme} />
      </div>
    </header>
    </ErrorBoundary>
  );
}

export default function App() {
  const { isAuthenticated, user, isDemoMode, logout } = useAuthStore();
  // السمة (فاتح/داكن) على مستوى الجذر — تُطبَّق على <html> وتُحفظ في localStorage.
  const { theme, setTheme } = useTheme();
  // بوّابة التأهيل: بعد المصادقة نفحص وجود مزرعة. مُعطَّلة قبل المصادقة وفي الوضع
  // التجريبيّ (لا تُطلق الطلب، فالاستعلام لا يعمل إلا حين isAuthenticated && !isDemoMode).
  const farms = useFarms(isAuthenticated && !isDemoMode);
  // تكوين المستأجِر (#206) — أفضل-جهد. null ⇒ تبقى الواجهة على الافتراضيّات تماماً.
  const tenantConfig = useTenantConfig();
  const branding = tenantConfig.data?.branding ?? null;
  // اللون الأساسيّ للمستأجِر كمتغيّر CSS تراكُبيّ (--tenant-primary). نضبطه فقط حين
  // يوفّره التكوين، ونُزيله عند غيابه كي يعود السلوك الافتراضيّ (لا تلوين عالق).
  useEffect(() => {
    const root = document.documentElement;
    const color = branding?.primary_color;
    if (color) root.style.setProperty('--tenant-primary', color);
    else root.style.removeProperty('--tenant-primary');
  }, [branding?.primary_color]);
  const [page,       setPage]       = useState<PageId>('dashboard');
  const [collapsed,  setCollapsed]  = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authScreen, setAuthScreen] = useState<'login' | 'signup'>('login');

  // Connect WebSocket after login — بهويّة المستخدم الفعليّة (لا الثابت 1 الذي كان
  // يسرّب إشعارات المستخدم 1 للجميع). بلا id: لا نتّصل (الخادم يجب أن يتحقّق بالتوكن).
  useEffect(() => {
    if (isAuthenticated && user?.id) {
      wsService.connect(user.id);
      wsService.requestNotificationPermission();
    } else {
      wsService.disconnect();
    }
    return () => {};
  }, [isAuthenticated, user?.id]);

  useEffect(() => { setMobileOpen(false); }, [page]);

  // خروج فعليّ عند انتهاء الجلسة (Phase 2): api.ts يُطلق 'sahool:auth:unauthorized'
  // عند 401 أو عند اكتشاف توكن منتهٍ محلياً. نُحوّل ذلك إلى logout فترجع الواجهة
  // لشاشة الدخول (سابقاً كان الحدث بلا مستمع فيبقى التطبيق عالقاً بلا توكن). وضع
  // التجريب مُستثنى: لا نُخرج المستخدم التجريبيّ على 401 خلفيّ (توكنه وهميّ أصلاً).
  useEffect(() => {
    const onUnauthorized = () => { if (!isDemoMode) logout(); };
    window.addEventListener('sahool:auth:unauthorized', onUnauthorized);
    return () => window.removeEventListener('sahool:auth:unauthorized', onUnauthorized);
  }, [isDemoMode, logout]);

  if (!isAuthenticated) {
    return (
      <>
        <Suspense fallback={<Loader />}>
          {authScreen === 'signup'
            ? <SignupPage onLogin={() => setAuthScreen('login')} />
            : <LoginPage onSignup={() => setAuthScreen('signup')} />}
        </Suspense>
        <ToastContainer />
      </>
    );
  }

  // بوّابة التأهيل الإجباريّة: مستخدم مُصادَق لكن بلا مزرعة لا يبلغ اللوحة حتى ينشئ
  // واحدة. الوضع التجريبيّ يتجاوزها (الاستعلام مُعطَّل ⇒ يبقى pending ⇒ نتخطّاه صراحةً).
  // أثناء جلب القائمة نُظهر تحميلاً. عند الخطأ (503/انقطاع) لا نحبس المستخدم — نمرّره
  // للّوحة (الصفحات نفسها تعرض حالات خطأ صادقة)، فلا نقفل التطبيق على عطل قاعدة عابر.
  // البوّابة لمن يملك farm:create (owner) فقط — غير المالك لا يُحبَس في إنشاء
  // مزرعة لا يستطيع إكمالها (403)؛ يمرّ مباشرةً للوحة (صفحاته تعرض حالاتها).
  if (!isDemoMode && canCreateFarm(user?.role)) {
    if (farms.isLoading) {
      return (
        <ErrorBoundary>
          <div className="flex items-center justify-center h-screen" style={{ background: '#0f1117' }}>
            <LoadingState message="جارٍ تحضير مزرعتك…" />
          </div>
          <ToastContainer />
        </ErrorBoundary>
      );
    }
    if (farms.isSuccess && (farms.data?.length ?? 0) === 0) {
      return (
        <ErrorBoundary>
          <div className="min-h-screen overflow-y-auto p-4 md:p-8" style={{ background: '#0f1117' }}>
            <Suspense fallback={<Loader />}>
              {/* عند النجاح يُبطَل كاش المزارع ⇒ farms.data يمتلئ ⇒ تتجاوز البوّابة تلقائيّاً */}
              <FarmCreatePage onCreated={() => farms.refetch()} />
            </Suspense>
          </div>
          <ToastContainer />
        </ErrorBoundary>
      );
    }
  }

  const renderPage = () => {
    // حارس RBAC: صفحة لا يحقّ للدور فتحها (عبر زر/رابط داخليّ) تُمنَع صراحةً.
    if (!canAccess(user?.role, page)) {
      return (
        <div className="flex flex-col items-center justify-center h-64 text-center" dir="rtl">
          <Shield className="w-10 h-10 text-amber-500 mb-3" />
          <h2 className="text-lg font-bold text-slate-100">لا تملك صلاحيّة هذه الصفحة</h2>
          <p className="text-sm text-slate-400 mt-1">دورك الحاليّ لا يسمح بالوصول إلى هذا القسم.</p>
          <button onClick={() => setPage('dashboard')}
            className="mt-4 px-4 py-2 rounded-lg text-sm text-emerald-400 border border-emerald-900 hover:bg-emerald-950">
            العودة للوحة المعلومات
          </button>
        </div>
      );
    }
    switch(page) {
      case 'dashboard':    return <DashboardPage setPage={setPage} />;
      case 'command':      return <OperationCommand />;
      case 'map-center':   return <FieldMapCenter />;
      case 'tasks-cabin':  return <FieldTasksCabin />;
      case 'rec-flow':     return <RecommendationFlow />;
      case 'hybrid-monitor': return <HybridMonitor />;
      case 'analyze-cabin': return <AnalyzeCabin />;
      case 'setup-cabin': return <SetupCabin />;
      case 'unified-cabin': return <UnifiedCabin />;
      case 'field-ranking': return <FieldRanking />;
      case 'problem-fields': return <ProblemFields />;
      case 'economics':    return <EconomicsDashboard />;
      case 'phenology':    return <PhenologyView />;
      case 'scouting':     return <ScoutingView />;
      case 'advisory-report': return <FarmAdvisoryReport />;
      case 'field-app':    return <FieldAppPreview />;
      case 'hybrid-index': return <HybridIndexPage />;
      case 'satellite':    return <SatellitePage />;
      case 'fields':       return <FieldManagementPage />;
      case 'recommendations': return <RecommendationPage />;
      case 'irrigation':   return <IrrigationWaterPage />;
      case 'pest-escalation': return <PestEscalationPage />;
      case 'field-intelligence': return <FieldIntelligencePage />;
      case 'spatial-indicators': return <SpatialIndicatorsPage />;
      case 'inventory':    return <InventoryPage />;
      case 'equipment':    return <EquipmentPage />;
      case 'devices':      return <DevicesPage />;
      case 'irrigation-ops': return <IrrigationOpsPage />;
      case 'weather-advice': return <WeatherAdvicePage />;
      case 'master-data':  return <MasterDataPage />;
      case 'documents':    return <DocumentsPage />;
      case 'governance':   return <GovernancePage />;
      case 'tasks':        return <TasksPage />;
      case 'activities':   return <ActivitiesPage />;
      case 'analytics':    return <AnalyticsPage />;
      case 'alerts':       return <AlertSystemPage />;
      case 'reports':      return <ReportsPage />;
      case 'chatbot':      return <ChatbotPage />;
      case 'settings':     return <SettingsPage />;
      default:             return <DashboardPage setPage={setPage} />;
    }
  };

  return (
    <ErrorBoundary>
    <>
      <div className="flex h-screen overflow-hidden" style={{ background:'#0f1117' }}>
        <div className="hidden md:flex">
          <Sidebar page={page} setPage={setPage} collapsed={collapsed} setCollapsed={setCollapsed} />
        </div>
        {mobileOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/60 md:hidden" onClick={() => setMobileOpen(false)} />
            <div className="fixed right-0 top-0 h-full z-50 md:hidden">
              <Sidebar page={page} setPage={(p: PageId) => { setPage(p); setMobileOpen(false); }}
                collapsed={false} setCollapsed={() => {}} />
            </div>
          </>
        )}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <TopBar page={page} onMenu={() => setMobileOpen(!mobileOpen)} theme={theme} setTheme={setTheme}
            tenantName={branding?.name_ar ?? null} tenantLogo={branding?.logo_url ?? null} />
          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Suspense fallback={<Loader />}>{renderPage()}</Suspense>
          </main>
        </div>
      </div>
      {/* Toast overlay — يظهر فوق كل شيء */}
      <ToastContainer />
    </>
    </ErrorBoundary>
  );
}
