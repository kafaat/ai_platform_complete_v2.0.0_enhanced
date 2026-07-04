// SAHOOL v8.0 — App.tsx (النهائية)
// ترحيل إلى React Router + قشرة FieldView: التوجيه القائم على الحالة سابقاً
// (page/setPage) صار محوّلاً رقيقاً فوق الراوتر — page يُشتقّ من مسار URL،
// و setPage = navigate(path). هذا يحفظ renderPage() وكلّ الصفحات (٦٦) بلا
// إعادة كتابة، ويُمكّن الروابط العميقة وزرّ الرجوع، مع حفظ كلّ البوّابات
// (canAccess + isPageEnabled) كما هي تماماً.
import { useState, useEffect, Suspense, lazy, useCallback } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2, Shield } from 'lucide-react';
import { useAuthStore } from './hooks/useAuth';
import { useFarms } from './hooks/useApi';
import { useTenantConfig } from './hooks/useTenantConfig';
import { useTheme } from './hooks/useTheme';
import { wsService } from './services/websocket';
import ToastContainer from './components/ToastContainer';
import { canAccess, canCreateFarm } from './lib/permissions';
import { isPageEnabled } from './lib/featureFlags';
import { ALL_ROUTES, pageForPath, pathForPage } from './lib/routes';
import AppShell from './components/shell/AppShell';
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
const AcceptInvitationPage = lazy(() => import('./pages/AcceptInvitationPage'));
const DashboardPage       = lazy(() => import('./sections/DashboardPage'));
const SatellitePage       = lazy(() => import('./sections/SatellitePage'));
const FieldManagementPage = lazy(() => import('./sections/FieldManagementPage'));
const MyFieldsPage        = lazy(() => import('./sections/MyFieldsPage'));
const AnalyticsPage       = lazy(() => import('./sections/AnalyticsPage'));
const AlertSystemPage     = lazy(() => import('./sections/AlertSystemPage'));
const ReportsPage         = lazy(() => import('./sections/ReportsPage'));
const SQLWorkspacePage    = lazy(() => import('./sections/SQLWorkspacePage'));
const ChatbotPage         = lazy(() => import('./sections/ChatbotPage').then(m => ({ default: m.ChatbotPage })));
const HybridIndexPage     = lazy(() => import('./sections/HybridIndexPage').then(m => ({ default: m.HybridIndexPage })));
const SettingsPage        = lazy(() => import('./sections/SettingsPage'));
const TasksPage           = lazy(() => import('./sections/TasksPage'));
const ActivitiesPage      = lazy(() => import('./sections/ActivitiesPage'));
const RecommendationPage  = lazy(() => import('./sections/RecommendationPage'));
const SpatialIndicatorsPage = lazy(() => import('./sections/SpatialIndicatorsPage'));
const IrrigationWaterPage = lazy(() => import('./sections/IrrigationWaterPage'));
const LabSamplingPage = lazy(() => import('./sections/LabSamplingPage'));
const IrrigationPlanPage = lazy(() => import('./sections/IrrigationPlanPage'));
const WaterTwinPage = lazy(() => import('./sections/WaterTwinPage'));
const EtcDualPage = lazy(() => import('./sections/EtcDualPage'));
const CropStatePage = lazy(() => import('./sections/CropStatePage'));
const ScenarioComparePage = lazy(() => import('./sections/ScenarioComparePage'));
const NlGisPage = lazy(() => import('./sections/NlGisPage'));
const GisToolsPage = lazy(() => import('./sections/GisToolsPage'));
const PortfolioPage = lazy(() => import('./sections/PortfolioPage'));
const PortfolioCommandPage = lazy(() => import('./sections/PortfolioCommandPage'));
const CalibrationPage = lazy(() => import('./sections/CalibrationPage'));
const CalibrationWorkbenchPage = lazy(() => import('./sections/CalibrationWorkbenchPage'));
const LineagePage = lazy(() => import('./sections/LineagePage'));
const EvidenceMapPage = lazy(() => import('./sections/EvidenceMapPage'));
const DeviceTwinPage = lazy(() => import('./sections/DeviceTwinPage'));
const ReplayMapPage = lazy(() => import('./sections/ReplayMapPage'));
const LearningDashboardPage = lazy(() => import('./sections/LearningDashboardPage'));
const DecisionStudioPage = lazy(() => import('./sections/DecisionStudioPage'));
const DecisionConfidencePage = lazy(() => import('./sections/DecisionConfidencePage'));
const ExecutionFeedbackPage = lazy(() => import('./sections/ExecutionFeedbackPage'));
const AgronomicTimelinePage = lazy(() => import('./sections/AgronomicTimelinePage'));
const PestEscalationPage  = lazy(() => import('./sections/PestEscalationPage'));
const FieldIntelligencePage = lazy(() => import('./sections/FieldIntelligencePage'));
const InventoryPage       = lazy(() => import('./sections/InventoryPage'));
const EquipmentPage       = lazy(() => import('./sections/EquipmentPage'));
const DevicesPage         = lazy(() => import('./sections/DevicesPage'));
const IrrigationOpsPage   = lazy(() => import('./sections/IrrigationOpsPage'));
const IrrigationNetworkPage = lazy(() => import('./sections/IrrigationNetworkPage'));
const WeatherAdvicePage   = lazy(() => import('./sections/WeatherAdvicePage'));
const MasterDataPage      = lazy(() => import('./sections/MasterDataPage'));
const DocumentsPage       = lazy(() => import('./sections/DocumentsPage'));
const GovernancePage      = lazy(() => import('./sections/GovernancePage'));
const FarmCreatePage      = lazy(() => import('./sections/FarmCreatePage'));
const FieldAppPreview     = lazy(() => import('./sections/FieldAppPreview'));
const OperationCommand    = lazy(() => import('./sections/OperationCommand'));
const FieldMapCenter      = lazy(() => import('./sections/FieldMapCenter'));
// Map Hub الموحّد (المرحلة 1) — السطح الأساسيّ «الحقول والخريطة» طراز FieldView:
// قائمة حقول باحثة + خريطة طبقات/مقارنة/رسم/دبابيس + درج تفاصيل + إنشاء داخل المركز،
// مع وضع تضاريس 3D كسول. يَخلُف FieldManagementPage كافتراضيّ لصفحة fields.
const MapHub              = lazy(() => import('./sections/MapHub'));
const FarmMapOverview     = lazy(() => import('./sections/FarmMapOverview'));
const FieldWorkspaceMapCard = lazy(() => import('./sections/FieldWorkspaceMapCard'));
const FieldTasksCabin     = lazy(() => import('./sections/FieldTasksCabin'));
const RecommendationFlow  = lazy(() => import('./sections/RecommendationFlow'));
const HybridMonitor       = lazy(() => import('./sections/HybridMonitor'));
const AnalyzeCabin        = lazy(() => import('./sections/AnalyzeCabin'));
const SetupCabin          = lazy(() => import('./sections/SetupCabin'));
const UnifiedCabin        = lazy(() => import('./sections/UnifiedCabin'));
const FieldRanking        = lazy(() => import('./sections/FieldRanking'));
const ProblemFields       = lazy(() => import('./sections/ProblemFields'));
const EconomicsDashboard  = lazy(() => import('./sections/EconomicsDashboard'));
const YieldAnalysisPage   = lazy(() => import('./sections/YieldAnalysisPage'));
const PhenologyView       = lazy(() => import('./sections/PhenologyView'));
const ScoutingView        = lazy(() => import('./sections/ScoutingView'));
const PrescriptionBuilderPage = lazy(() => import('./sections/PrescriptionBuilderPage'));
const FarmAdvisoryReport  = lazy(() => import('./sections/FarmAdvisoryReport'));
const OperationCenterWallPage = lazy(() => import('./sections/OperationCenterWallPage'));
const AdminRuntimePage = lazy(() => import('./sections/AdminRuntimePage'));
const DecisionRuntimePage = lazy(() => import('./sections/DecisionRuntimePage'));
const GisExpertPage = lazy(() => import('./sections/GisExpertPage'));
const ApprovalsConsolePage = lazy(() => import('./sections/ApprovalsConsolePage'));
const AgroZonesPanel = lazy(() => import('./components/agrozones/AgroZonesPanel'));
const YemeniCalendarPanel = lazy(() => import('./components/calendars/YemeniCalendarPanel'));
const ClimateAnalogsPanel = lazy(() => import('./components/climate/ClimateAnalogsPanel'));

export type PageId =
  | 'dashboard' | 'hybrid-index' | 'satellite' | 'fields' | 'farm-map' | 'field-workspace'
  | 'analytics' | 'alerts' | 'reports' | 'chatbot'
  | 'tasks' | 'settings' | 'recommendations' | 'spatial-indicators'
  | 'lab-sampling' | 'irrigation' | 'irrigation-plan' | 'water-twin' | 'etc-dual' | 'crop-state' | 'scenario-compare' | 'nl-gis' | 'portfolio' | 'portfolio-command' | 'calibration' | 'calibration-workbench' | 'lineage' | 'evidence-map' | 'replay-map' | 'learning-dashboard' | 'decision-studio' | 'decision-confidence' | 'decision-runtime' | 'execution-feedback' | 'agronomic-timeline' | 'pest-escalation' | 'field-intelligence'
  | 'inventory' | 'equipment' | 'devices' | 'device-twin' | 'irrigation-ops' | 'irrigation-network'
  | 'activities' | 'master-data' | 'documents' | 'governance' | 'admin-runtime' | 'approvals-console'
  | 'weather-advice' | 'field-app' | 'command' | 'map-center' | 'tasks-cabin' | 'rec-flow' | 'hybrid-monitor' | 'analyze-cabin' | 'setup-cabin' | 'unified-cabin' | 'field-ranking' | 'problem-fields' | 'economics' | 'yield-analysis' | 'phenology' | 'scouting' | 'prescriptions' | 'advisory-report'
  | 'operations-wall' | 'sql-workspace' | 'gis-tools' | 'gis-expert'
  | 'agro-zones' | 'yemeni-calendars' | 'climate-analogs';

// ملاحظة ترحيل: FEATURE_FLAGS و isPageEnabled انتقلا إلى `lib/featureFlags.ts`،
// وبنية القائمة (المجموعات) انتقلت إلى سجلّ المسارات `lib/routes.ts` (بنية معلومات
// جديدة بأقسام). القشرة (NavRail/ContextBar/MobileTabBar) تُشتقّ منهما، و App هنا
// يبقى محوّلاً للتوجيه فوق الراوتر مع حفظ renderPage وكلّ البوّابات.

function Loader() {
  return (
    <ErrorBoundary>
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 text-emerald-500 animate-spin" />
    </div>
  </ErrorBoundary>
  );
}

// ملاحظة ترحيل: مكوّنا Sidebar/TopBar السابقان حلّ محلّهما القشرة الجديدة
// (components/shell/*): NavRail + ContextBar + MobileTabBar، مُشتقّة من lib/routes.ts.


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
  // ── محوّل التوجيه (Router Adapter) ──────────────────────────────
  // page يُشتقّ من مسار URL الحاليّ (مصدر الحقيقة)؛ المسار المجهول/القديم يقع
  // على 'dashboard' (تُعيد <Routes> توجيهه لـ«/»). setPage يصبح navigate(path)
  // — فتُبقي الصفحات (التي تستدعي setPage) عاملةً بلا تعديل، مع روابط عميقة ورجوع.
  const location = useLocation();
  const navigate = useNavigate();
  const page: PageId = pageForPath(location.pathname) ?? 'dashboard';
  const setPage = useCallback((p: PageId) => { navigate(pathForPage(p)); }, [navigate]);
  // الشاشة الأوّليّة ما قبل المصادقة: إن حمل الرابط ?token= نعرض قبول الدعوة
  // (شاشة عموميّة محميّة بالـtoken — ليست PageId، مثل signup). وإلّا تسجيل الدخول.
  const [authScreen, setAuthScreen] = useState<'login' | 'signup' | 'accept-invitation'>(
    () => (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('token')
      ? 'accept-invitation'
      : 'login')
  );

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

  // (إغلاق درج الموبايل عند تغيّر المسار انتقل إلى AppShell.)

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
          {authScreen === 'accept-invitation'
            ? <AcceptInvitationPage onLogin={() => setAuthScreen('login')} />
            : authScreen === 'signup'
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
    // حارس الميزة: صفحة محجوبة خلف علم مُطفأ (لا خلفيّة جاهزة) ⇒ لافتة صريحة بدل
    // شاشة مكسورة. تبقى في اتّحاد PageId والمُصيِّر؛ تُعاد بالتفعيل (VITE_ENABLE_*).
    if (!isPageEnabled(page)) {
      return (
        <div className="flex flex-col items-center justify-center h-64 text-center" dir="rtl">
          <Shield className="w-10 h-10 text-amber-500 mb-3" />
          <h2 className="text-lg font-bold text-slate-100">الميزة غير مفعّلة</h2>
          <p className="text-sm text-slate-400 mt-1">هذه الشاشة بانتظار جهوزيّة خدمتها الخلفيّة.</p>
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
      // مركز الخرائط: السطح الموحّد الجديد (Map Hub). FieldMapCenter السابق يبقى
      // مُستورَداً ومتاحاً (يُحتفَظ به مرجعاً) لكنّ الـMap Hub يَخلُفه افتراضيّاً.
      case 'map-center':   return <MapHub />;
      case 'farm-map':     return <FarmMapOverview />;
      case 'field-workspace': return <FieldWorkspaceMapCard />;
      case 'tasks-cabin':  return <FieldTasksCabin />;
      case 'rec-flow':     return <RecommendationFlow />;
      case 'hybrid-monitor': return <HybridMonitor />;
      case 'analyze-cabin': return <AnalyzeCabin />;
      case 'setup-cabin': return <SetupCabin />;
      case 'unified-cabin': return <UnifiedCabin />;
      case 'field-ranking': return <FieldRanking />;
      case 'problem-fields': return <ProblemFields />;
      case 'economics':    return <EconomicsDashboard />;
      case 'yield-analysis': return <YieldAnalysisPage />;
      case 'phenology':    return <PhenologyView />;
      case 'scouting':     return <ScoutingView />;
      case 'prescriptions': return <PrescriptionBuilderPage />;
      case 'advisory-report': return <FarmAdvisoryReport />;
      case 'operations-wall': return <OperationCenterWallPage />;
      case 'field-app':    return <FieldAppPreview />;
      case 'hybrid-index': return <HybridIndexPage />;
      case 'satellite':    return <SatellitePage />;
      // «الحقول والخريطة»: المرحلة 1 تجعل Map Hub الموحّد السطح الأساسيّ.
      // FieldManagementPage السابق يبقى مُستورَداً ومتاحاً (لم يُحذَف) لكنّه لم يَعُد
      // الافتراضيّ لهذا المسار — الـMap Hub يَخلُفه (يشمل إنشاء/استيراد الحقل داخله).
      case 'fields':       return <MyFieldsPage />;
      case 'recommendations': return <RecommendationPage />;
      case 'lab-sampling': return <LabSamplingPage />;
      case 'irrigation':   return <IrrigationWaterPage />;
      case 'irrigation-plan': return <IrrigationPlanPage />;
      case 'water-twin': return <WaterTwinPage />;
      case 'etc-dual': return <EtcDualPage />;
      case 'crop-state': return <CropStatePage />;
      case 'scenario-compare': return <ScenarioComparePage />;
      case 'nl-gis': return <NlGisPage />;
      case 'sql-workspace': return <SQLWorkspacePage />;
      case 'gis-tools': return <GisToolsPage />;
      case 'portfolio': return <PortfolioPage />;
      case 'portfolio-command': return <PortfolioCommandPage />;
      case 'calibration': return <CalibrationPage />;
      case 'calibration-workbench': return <CalibrationWorkbenchPage />;
      case 'lineage': return <LineagePage />;
      case 'evidence-map': return <EvidenceMapPage />;
      case 'replay-map': return <ReplayMapPage />;
      case 'learning-dashboard': return <LearningDashboardPage />;
      case 'decision-studio': return <DecisionStudioPage />;
      case 'decision-confidence': return <DecisionConfidencePage />;
      case 'execution-feedback': return <ExecutionFeedbackPage />;
      case 'agronomic-timeline': return <AgronomicTimelinePage />;
      case 'pest-escalation': return <PestEscalationPage />;
      case 'field-intelligence': return <FieldIntelligencePage />;
      case 'spatial-indicators': return <SpatialIndicatorsPage />;
      case 'inventory':    return <InventoryPage />;
      case 'equipment':    return <EquipmentPage />;
      case 'devices':      return <DevicesPage />;
      case 'device-twin':  return <DeviceTwinPage />;
      case 'irrigation-ops': return <IrrigationOpsPage />;
      case 'irrigation-network': return <IrrigationNetworkPage />;
      case 'weather-advice': return <WeatherAdvicePage />;
      case 'agro-zones':   return <AgroZonesPanel />;
      case 'yemeni-calendars': return <YemeniCalendarPanel />;
      case 'climate-analogs': return <ClimateAnalogsPanel />;
      case 'master-data':  return <MasterDataPage />;
      case 'documents':    return <DocumentsPage />;
      case 'governance':   return <GovernancePage />;
      case 'admin-runtime': return <AdminRuntimePage />;
      case 'approvals-console': return <ApprovalsConsolePage />;
      case 'decision-runtime': return <DecisionRuntimePage />;
      case 'gis-expert': return <GisExpertPage />;
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

  // محتوى الصفحة الحاليّة (نفس renderPage السابق) ملفوفاً بـSuspense — هدف عرض
  // واحد لكلّ مسار مُسجَّل (page مُشتقّ من URL، فالمحتوى يتبع المسار تلقائيّاً).
  const pageContent = <Suspense fallback={<Loader />}>{renderPage()}</Suspense>;

  return (
    <ErrorBoundary>
    <>
      <AppShell
        theme={theme} setTheme={setTheme}
        tenantName={branding?.name_ar ?? null} tenantLogo={branding?.logo_url ?? null}
      >
        {/* جدول المسارات: كلّ مسار مُسجَّل يعرض نفس محتوى renderPage (المُصيِّر القديم
            سليم بالكامل). المسار المجهول/القديم ⇒ إعادة توجيه إلى «/». بوّابات RBAC
            وعلم الميزة تبقى داخل renderPage تماماً كما كانت (لا تغيير في السياسة). */}
        <Routes>
          {ALL_ROUTES.map((r) => (
            <Route key={r.id} path={r.path} element={pageContent} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
      {/* Toast overlay — يظهر فوق كل شيء */}
      <ToastContainer />
    </>
    </ErrorBoundary>
  );
}
