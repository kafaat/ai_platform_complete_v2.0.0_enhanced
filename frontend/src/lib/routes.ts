// ═══════════════════════════════════════════════════════════════
// SAHOOL — سجلّ المسارات (Route Registry) · مصدر واحد للحقيقة
// ───────────────────────────────────────────────────────────────
// يربط كلّ PageId (التوجيه القائم على الحالة سابقاً) بمسار URL واحد، ضمن
// بنية معلومات (IA) جديدة بأقسام واضحة. هذا الملفّ هو المصدر الوحيد الذي
// تُشتقّ منه: قشرة التطبيق (شريط التنقّل/الشريط السفليّ)، جدول <Routes>،
// والتنقّل البرمجيّ (محوّل setPage↔navigate). لا فقدان لأيّ صفحة: كلّ معرّف
// في اتّحاد PageId مُمثَّل هنا تماماً (حارس وقت-التصريف أدناه يفرض ذلك).
//
// ── مخطّط الـURL (URL SCHEME) ──────────────────────────────────
// المسارات هرميّة وفق القسم الوظيفيّ، عربيّة-المعنى لكن لاتينيّة-المسار
// (تتوافق مع الروابط العميقة والمشاركة). لوحة المعلومات هي الجذر «/».
//   نظرة عامّة            → /                         (dashboard)
//                          /ops-wall, /alerts, /assistant, /reports …
//   الحقول والخريطة       → /fields, /fields/farm-map, /fields/workspace …
//   صحّة الحقل            → /health/indices, /health/satellite …
//   الريّ والمحصول        → /irrigation, /irrigation/plan, /crop/state …
//   البيانات والتحليل     → /analysis, /analysis/economics …
//   التقارير              → /reports, /advisory …
//   الذكاء المتقدّم        → /advanced/decision-studio, /advanced/lineage …
//   العمليّات             → /ops/tasks, /ops/inventory, /ops/equipment …
//   الإدارة والإعدادات    → /admin/master-data, /admin/governance, /settings …
//   معاينة التطبيق الموحّد → /preview/unified, /preview/command …
// المسار المجهول/القديم → إعادة توجيه إلى «/» (يُعالَج في App عبر <Navigate>).
// ═══════════════════════════════════════════════════════════════
import {
  LayoutDashboard, Satellite, Map as MapIcon, BarChart3, Bell,
  FileText, Bot, Settings, AlertTriangle,
  ClipboardList, Droplets, Bug, Activity,
  Boxes, Tractor, Cpu, Waypoints, Database, FolderArchive,
  ShieldCheck, Sprout, CloudRain, Smartphone, Layers, ListChecks, TrendingUp,
  CalendarRange, GitCompare, GitBranch, Crosshair, Search, History,
  FlaskConical, GitCommitHorizontal, SlidersHorizontal, MonitorPlay, Share2, Repeat, Gauge,
  Home, HeartPulse, FolderKanban, Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { PageId } from '../App';

// ── درجة نضج الصفحة (Maturity) ─────────────────────────────────
// تصنيف موحّد يَخلُف شارة «جديد» العشوائيّة: alpha (تجريبيّ مبكّر/محجوب خلف علم) ⇒
// beta (متقدّم/فريد لسهول، يعمل لكنّه قيد الصقل) ⇒ stable (أساسيّ ناضج). تُعرَض
// كشارة صغيرة في NavRail وتُلوَّن حسب الدرجة. الأساسيّ بلا شارة (stable مُلمَّح ضمناً).
export type Maturity = 'alpha' | 'beta' | 'stable';

// ── وصف عنصر مسار واحد ──────────────────────────────────────────
export interface RouteDef {
  id: PageId;          // معرّف الصفحة القديم (يبقى مصدر renderPage و canAccess)
  path: string;        // مسار URL الفريد (يبدأ بـ/)
  label: string;       // التسمية العربيّة (تُعرَض في القائمة/العنوان)
  icon: LucideIcon;    // أيقونة العنصر
  maturity?: Maturity; // درجة النضج (تُعرَض كشارة في NavRail؛ غيابها ⇒ أساسيّ ناضج)
  badge?: string;      // شارة دلاليّة اختياريّة («AI»/«WOFOST»/«دمج»…) لا «جديد»
}

// ── قسم في بنية المعلومات الجديدة ──────────────────────────────
export interface NavSection {
  id: string;          // معرّف القسم (لمفاتيح الطيّ)
  label: string;       // عنوان القسم العربيّ
  icon: LucideIcon;    // أيقونة القسم (للشريط السفليّ/المطويّ)
  defaultOpen: boolean; // هل يُفتح القسم افتراضيّاً في شريط التنقّل؟
  items: RouteDef[];
}

// ── بنية المعلومات الجديدة (IA) — مصدر القشرة والمسارات ─────────
export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'overview', label: 'نظرة عامّة', icon: Home, defaultOpen: true,
    items: [
      { id: 'dashboard',       path: '/',          label: 'لوحة المعلومات', icon: LayoutDashboard, maturity: 'stable' },
      { id: 'operations-wall', path: '/ops-wall',  label: 'جدار مركز العمليّات', icon: MonitorPlay, maturity: 'beta' },
      { id: 'alerts',          path: '/alerts',    label: 'التنبيهات', icon: Bell, maturity: 'stable' },
      { id: 'chatbot',         path: '/assistant', label: 'المستشار الذكي', icon: Bot, maturity: 'beta', badge: 'AI' },
    ],
  },
  {
    id: 'fields-map', label: 'الحقول والخريطة', icon: MapIcon, defaultOpen: false,
    items: [
      { id: 'fields',          path: '/fields',           label: 'إدارة الحقول', icon: MapIcon, maturity: 'stable' },
      { id: 'farm-map',        path: '/fields/farm-map',  label: 'خريطة المزرعة', icon: MapIcon, maturity: 'stable' },
      { id: 'field-workspace', path: '/fields/workspace', label: 'مساحة عمل الحقل', icon: Layers, maturity: 'beta' },
      { id: 'map-center',      path: '/fields/map-center', label: 'مركز الخرائط (معاينة)', icon: Layers, maturity: 'beta', badge: 'دمج' },
    ],
  },
  {
    id: 'field-health', label: 'صحّة الحقل', icon: HeartPulse, defaultOpen: false,
    items: [
      { id: 'satellite',          path: '/health/satellite', label: 'الأقمار الصناعية', icon: Satellite, maturity: 'stable' },
      { id: 'hybrid-index',       path: '/health/indices',   label: 'المؤشرات (17)', icon: BarChart3, maturity: 'stable', badge: 'WOFOST' },
      { id: 'spatial-indicators', path: '/health/spatial',   label: 'المؤشرات المكانية', icon: MapIcon, maturity: 'stable' },
      { id: 'phenology',          path: '/health/phenology', label: 'مراحل النموّ', icon: Sprout, maturity: 'stable' },
      { id: 'scouting',           path: '/health/scouting',  label: 'دليل الاستكشاف', icon: Bug, maturity: 'stable' },
      { id: 'pest-escalation',    path: '/health/pest',      label: 'تصعيد الآفة', icon: Bug, maturity: 'beta' },
      { id: 'prescriptions',      path: '/health/prescriptions', label: 'منشئ الوصفات (يدويّ)', icon: SlidersHorizontal, maturity: 'alpha' },
      { id: 'field-intelligence', path: '/health/maestro',   label: 'المايسترو', icon: Activity, maturity: 'beta' },
    ],
  },
  {
    id: 'irrigation-crop', label: 'الريّ والمحصول', icon: Droplets, defaultOpen: false,
    items: [
      { id: 'irrigation',        path: '/irrigation',          label: 'تحليل ماء الريّ', icon: Droplets, maturity: 'stable' },
      { id: 'irrigation-plan',   path: '/irrigation/plan',     label: 'خطّة الريّ المتنبّأ', icon: CalendarRange, maturity: 'beta' },
      { id: 'irrigation-ops',    path: '/irrigation/ops',      label: 'الري التشغيلي', icon: Waypoints, maturity: 'beta' },
      { id: 'irrigation-network', path: '/irrigation/network', label: 'توأم شبكة الريّ', icon: Share2, maturity: 'beta' },
      { id: 'portfolio',         path: '/irrigation/portfolio', label: 'توزيع ماء المزرعة', icon: Layers, maturity: 'beta' },
      { id: 'portfolio-command', path: '/irrigation/portfolio-command', label: 'مركز قيادة المحفظة', icon: Crosshair, maturity: 'beta' },
      { id: 'crop-state',        path: '/crop/state',          label: 'حالة المحصول الموحّدة', icon: Sprout, maturity: 'stable' },
      { id: 'weather-advice',    path: '/crop/weather',        label: 'الطقس والريّ', icon: CloudRain, maturity: 'stable' },
    ],
  },
  {
    id: 'data-analysis', label: 'البيانات والتحليل', icon: BarChart3, defaultOpen: false,
    items: [
      { id: 'analytics',     path: '/analysis',            label: 'التحليلات', icon: BarChart3, maturity: 'stable' },
      { id: 'economics',     path: '/analysis/economics',  label: 'الاقتصاد / ROI', icon: BarChart3, maturity: 'stable' },
      { id: 'yield-analysis', path: '/analysis/yield',     label: 'تحليل الغلّة', icon: Sprout, maturity: 'beta' },
      { id: 'field-ranking', path: '/analysis/field-ranking', label: 'ترتيب الحقول', icon: TrendingUp, maturity: 'stable' },
      { id: 'problem-fields', path: '/analysis/problem-fields', label: 'حقول المشكلات', icon: AlertTriangle, maturity: 'stable' },
      { id: 'nl-gis',        path: '/analysis/nl-gis',     label: 'استعلام GIS باللغة الطبيعيّة', icon: Search, maturity: 'alpha' },
      { id: 'sql-workspace', path: '/analysis/sql-workspace', label: 'ورشة SQL (DuckDB)', icon: Database, maturity: 'alpha', badge: 'SQL' },
      { id: 'scenario-compare', path: '/analysis/scenario-compare', label: 'مقارنة السياسات', icon: GitCompare, maturity: 'beta' },
    ],
  },
  {
    id: 'reports', label: 'التقارير', icon: FileText, defaultOpen: false,
    items: [
      { id: 'reports',         path: '/reports',         label: 'التقارير', icon: FileText, maturity: 'stable' },
      { id: 'advisory-report', path: '/reports/advisory', label: 'استشارة المزرعة', icon: FileText, maturity: 'stable' },
      { id: 'recommendations', path: '/reports/recommendations', label: 'التوصيات', icon: ClipboardList, maturity: 'stable' },
    ],
  },
  {
    id: 'advanced', label: 'الذكاء المتقدّم', icon: FlaskConical, defaultOpen: false,
    items: [
      { id: 'decision-studio',     path: '/advanced/decision-studio',     label: 'استوديو القرار', icon: FlaskConical, maturity: 'beta' },
      { id: 'decision-confidence', path: '/advanced/decision-confidence', label: 'ثقة القرار الموحَّدة', icon: Gauge, maturity: 'beta' },
      { id: 'execution-feedback',  path: '/advanced/execution-feedback',  label: 'رصد حلقة التنفيذ', icon: Repeat, maturity: 'beta' },
      { id: 'agronomic-timeline',  path: '/advanced/agronomic-timeline',  label: 'الخطّ الزمنيّ الأغرونوميّ', icon: GitCommitHorizontal, maturity: 'beta' },
      { id: 'learning-dashboard',  path: '/advanced/learning',            label: 'لوحة رصد التعلّم', icon: BarChart3, maturity: 'beta' },
      { id: 'calibration',         path: '/advanced/calibration',         label: 'حالة المعايرة الإقليميّة', icon: Activity, maturity: 'beta' },
      { id: 'calibration-workbench', path: '/advanced/calibration-workbench', label: 'منضدة المعايرة', icon: SlidersHorizontal, maturity: 'beta' },
      { id: 'lineage',             path: '/advanced/lineage',             label: 'سلسلة النَّسَب والدليل', icon: GitBranch, maturity: 'beta' },
      { id: 'evidence-map',        path: '/advanced/evidence-map',        label: 'خريطة الدليل', icon: ShieldCheck, maturity: 'alpha' },
      { id: 'replay-map',          path: '/advanced/replay-map',          label: 'إعادة تشغيل الموسم', icon: History, maturity: 'alpha' },
    ],
  },
  {
    id: 'operations', label: 'العمليّات', icon: FolderKanban, defaultOpen: false,
    items: [
      { id: 'tasks',       path: '/ops/tasks',       label: 'المهام الميدانية', icon: ClipboardList, maturity: 'stable' },
      { id: 'activities',  path: '/ops/activities',  label: 'العمليّات الزراعيّة', icon: Sprout, maturity: 'stable' },
      { id: 'inventory',   path: '/ops/inventory',   label: 'المخزون', icon: Boxes, maturity: 'stable' },
      { id: 'equipment',   path: '/ops/equipment',   label: 'المعدّات', icon: Tractor, maturity: 'stable' },
      { id: 'devices',     path: '/ops/devices',     label: 'أجهزة IoT', icon: Cpu, maturity: 'stable' },
      { id: 'device-twin', path: '/ops/device-twin', label: 'توائم الأجهزة وثقة الحسّاس', icon: Activity, maturity: 'beta' },
    ],
  },
  {
    id: 'preview', label: 'التطبيق الموحّد (معاينة)', icon: Smartphone, defaultOpen: false,
    items: [
      { id: 'unified-cabin',  path: '/preview/unified',  label: 'التطبيق الموحّد (معاينة)', icon: Smartphone, maturity: 'alpha', badge: '٦ وجهات' },
      { id: 'command',        path: '/preview/command',  label: 'مركز العمليّات (معاينة)', icon: Smartphone, maturity: 'alpha', badge: 'دمج' },
      { id: 'tasks-cabin',    path: '/preview/tasks',    label: 'كابينة المهام (معاينة)', icon: ListChecks, maturity: 'alpha', badge: 'دمج' },
      { id: 'rec-flow',       path: '/preview/rec-flow', label: 'توصية ← تنفيذ (معاينة)', icon: ClipboardList, maturity: 'alpha', badge: 'دمج' },
      { id: 'hybrid-monitor', path: '/preview/hybrid-monitor', label: 'المراقبة الهجينة (معاينة)', icon: Activity, maturity: 'alpha', badge: 'دمج' },
      { id: 'analyze-cabin',  path: '/preview/analyze',  label: 'التحليل (معاينة)', icon: BarChart3, maturity: 'alpha', badge: 'دمج' },
      { id: 'setup-cabin',    path: '/preview/setup',    label: 'الإعداد (معاينة)', icon: Settings, maturity: 'alpha', badge: 'دمج' },
      { id: 'field-app',      path: '/preview/field-app', label: 'تطبيق الحقل (معاينة)', icon: Smartphone, maturity: 'alpha' },
    ],
  },
  {
    id: 'admin', label: 'الإدارة والإعدادات', icon: Wrench, defaultOpen: false,
    items: [
      { id: 'master-data', path: '/admin/master-data', label: 'البيانات المرجعيّة', icon: Database, maturity: 'stable' },
      { id: 'documents',   path: '/admin/documents',   label: 'الوثائق', icon: FolderArchive, maturity: 'stable' },
      { id: 'governance',  path: '/admin/governance',  label: 'الحوكمة والتدقيق', icon: ShieldCheck, maturity: 'stable' },
      { id: 'settings',    path: '/settings',          label: 'الإعدادات', icon: Settings, maturity: 'stable' },
    ],
  },
];

// ── قائمة مُسطّحة بكلّ المسارات (للبحث/التحويل) ─────────────────
export const ALL_ROUTES: RouteDef[] = NAV_SECTIONS.flatMap((s) => s.items);

// ── عرض شارة النضج (مصدر واحد لـNavRail/CommandPalette) ─────────
// alpha/beta فقط تُعرَض (stable ناضج ⇒ بلا ضوضاء بصريّة). كلّ درجة لها تسمية
// عربيّة موجزة ولونان (نصّ/خلفيّة) منسجمان مع الثيم الداكن.
export const MATURITY_META: Record<Exclude<Maturity, 'stable'>, {
  label: string; fg: string; bg: string;
}> = {
  beta:  { label: 'تجريبيّ',  fg: '#fbbf24', bg: '#78350f33' }, // كهرماني
  alpha: { label: 'مبكّر',    fg: '#f472b6', bg: '#83184833' }, // وردي
};

/** بيانات عرض شارة النضج لعنصر مسار (null للأساسيّ الناضج/غير المُصنَّف). */
export function maturityBadge(m?: Maturity) {
  if (!m || m === 'stable') return null;
  return MATURITY_META[m];
}

// ── خرائط تحويل ثنائيّة الاتّجاه: PageId ↔ path ────────────────
const PAGE_TO_PATH = new Map<PageId, string>(ALL_ROUTES.map((r) => [r.id, r.path]));
const PATH_TO_PAGE = new Map<string, PageId>(ALL_ROUTES.map((r) => [r.path, r.id]));

/** مسار URL لمعرّف الصفحة (يقع على «/» إن غاب — لن يحدث: الحارس يضمن الاكتمال). */
export function pathForPage(id: PageId): string {
  return PAGE_TO_PATH.get(id) ?? '/';
}

/** معرّف الصفحة من مسار URL (null للمسار المجهول/القديم ⇒ إعادة توجيه لـ«/»). */
export function pageForPath(pathname: string): PageId | null {
  // تطبيع: إزالة الشرطة المائلة الزائدة (عدا الجذر) كي يتطابق «/fields/» مع «/fields».
  const norm = pathname.length > 1 && pathname.endsWith('/')
    ? pathname.replace(/\/+$/, '')
    : pathname;
  return PATH_TO_PAGE.get(norm) ?? null;
}

/** العنصر الكامل (تسمية/أيقونة) لمعرّف الصفحة — لعنوان الشريط العلويّ. */
export function routeForPage(id: PageId): RouteDef | undefined {
  return ALL_ROUTES.find((r) => r.id === id);
}

// ── حارس وقت-التصريف: كلّ PageId مُمثَّل في السجلّ (لا فقدان صفحة) ──
// إن ظهر خطأ نوع هنا: معرّف(ات) في اتّحاد PageId غير مُسجَّلة في NAV_SECTIONS.
type _RegisteredId = (typeof ALL_ROUTES)[number]['id'];
type _PagesMissingFromRegistry = Exclude<PageId, _RegisteredId>;
const _assertRegistryComplete: _PagesMissingFromRegistry extends never ? true : never = true;
void _assertRegistryComplete;
