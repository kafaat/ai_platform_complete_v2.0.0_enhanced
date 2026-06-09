// SAHOOL v8.0 — App.tsx (النهائية)
import { useState, useEffect, Suspense, lazy } from 'react';
import {
  LayoutDashboard, Satellite, Map, BarChart3, Bell,
  FileText, Bot, Settings, Loader2, Leaf, LogOut,
  User, ChevronLeft, ChevronRight, Shield, AlertTriangle,
  Wifi, WifiOff, ClipboardList,
} from 'lucide-react';
import { useAuthStore } from './hooks/useAuth';
import { wsService } from './services/websocket';
import ToastContainer from './components/ToastContainer';

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
const RecommendationPage  = lazy(() => import('./sections/RecommendationPage'));
const SpatialIndicatorsPage = lazy(() => import('./sections/SpatialIndicatorsPage'));

export type PageId =
  | 'dashboard' | 'hybrid-index' | 'satellite' | 'fields'
  | 'analytics' | 'alerts' | 'reports' | 'chatbot'
  | 'tasks' | 'settings' | 'recommendations' | 'spatial-indicators';

const NAV: { id: PageId; label: string; icon: any; badge?: string }[] = [
  { id:'dashboard',    label:'لوحة المعلومات', icon:LayoutDashboard },
  { id:'hybrid-index', label:'المؤشرات (17)',  icon:BarChart3, badge:'WOFOST' },
  { id:'satellite',    label:'الأقمار الصناعية', icon:Satellite },
  { id:'fields',       label:'إدارة الحقول',   icon:Map },
  { id:'recommendations', label:'التوصيات',    icon:ClipboardList },
  { id:'spatial-indicators', label:'المؤشرات المكانية', icon:Map },
  { id:'tasks',        label:'المهام الميدانية',icon:ClipboardList, badge:'6' },
  { id:'analytics',    label:'التحليلات',       icon:BarChart3 },
  { id:'alerts',       label:'التنبيهات',       icon:Bell, badge:'2' },
  { id:'reports',      label:'التقارير',        icon:FileText },
  { id:'chatbot',      label:'المستشار الذكي',  icon:Bot, badge:'AI' },
  { id:'settings',     label:'الإعدادات',       icon:Settings },
];

function Loader() {
  return (
    <ErrorBoundary>
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
    </div>
  </ErrorBoundary>
  );
}

function Sidebar({ page, setPage, collapsed, setCollapsed }: any) {
  const { user, logout, isDemoMode } = useAuthStore();
  const wsOk = wsService.isConnected();

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

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {NAV.map(item => {
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

function TopBar({ page, onMenu }: any) {
  const item = NAV.find(n => n.id === page);
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
      <Icon className="w-5 h-5 text-emerald-500" />
      <h1 className="text-base font-bold text-slate-100">{item?.label}</h1>
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
      </div>
    </header>
    </ErrorBoundary>
  );
}

export default function App() {
  const { isAuthenticated, user } = useAuthStore();
  const [page,       setPage]       = useState<PageId>('dashboard');
  const [collapsed,  setCollapsed]  = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Connect WebSocket after login
  useEffect(() => {
    if (isAuthenticated && user) {
      wsService.connect(1); // userId placeholder
      wsService.requestNotificationPermission();
    } else {
      wsService.disconnect();
    }
    return () => {};
  }, [isAuthenticated]);

  useEffect(() => { setMobileOpen(false); }, [page]);

  if (!isAuthenticated) {
    return (
      <>
        <Suspense fallback={<Loader />}><LoginPage /></Suspense>
        <ToastContainer />
      </>
    );
  }

  const renderPage = () => {
    switch(page) {
      case 'dashboard':    return <DashboardPage setPage={setPage} />;
      case 'hybrid-index': return <HybridIndexPage />;
      case 'satellite':    return <SatellitePage />;
      case 'fields':       return <FieldManagementPage />;
      case 'recommendations': return <RecommendationPage />;
      case 'spatial-indicators': return <SpatialIndicatorsPage />;
      case 'tasks':        return <TasksPage />;
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
          <TopBar page={page} onMenu={() => setMobileOpen(!mobileOpen)} />
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
