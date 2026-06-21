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

// ── وصف عنصر مسار واحد ──────────────────────────────────────────
export interface RouteDef {
  id: PageId;          // معرّف الصفحة القديم (يبقى مصدر renderPage و canAccess)
  path: string;        // مسار URL الفريد (يبدأ بـ/)
  label: string;       // التسمية العربيّة (تُعرَض في القائمة/العنوان)
  icon: LucideIcon;    // أيقونة العنصر
  badge?: string;      // شارة اختياريّة («جديد»/«AI»…)
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
      { id: 'dashboard',       path: '/',          label: 'لوحة المعلومات', icon: LayoutDashboard },
      { id: 'operations-wall', path: '/ops-wall',  label: 'جدار مركز العمليّات', icon: MonitorPlay, badge: 'جديد' },
      { id: 'alerts',          path: '/alerts',    label: 'التنبيهات', icon: Bell },
      { id: 'chatbot',         path: '/assistant', label: 'المستشار الذكي', icon: Bot, badge: 'AI' },
    ],
  },
  {
    id: 'fields-map', label: 'الحقول والخريطة', icon: MapIcon, defaultOpen: false,
    items: [
      { id: 'fields',          path: '/fields',           label: 'إدارة الحقول', icon: MapIcon },
      { id: 'farm-map',        path: '/fields/farm-map',  label: 'خريطة المزرعة', icon: MapIcon },
      { id: 'field-workspace', path: '/fields/workspace', label: 'مساحة عمل الحقل', icon: Layers, badge: 'جديد' },
      { id: 'map-center',      path: '/fields/map-center', label: 'مركز الخرائط (معاينة)', icon: Layers, badge: 'دمج' },
    ],
  },
  {
    id: 'field-health', label: 'صحّة الحقل', icon: HeartPulse, defaultOpen: false,
    items: [
      { id: 'satellite',          path: '/health/satellite', label: 'الأقمار الصناعية', icon: Satellite },
      { id: 'hybrid-index',       path: '/health/indices',   label: 'المؤشرات (17)', icon: BarChart3, badge: 'WOFOST' },
      { id: 'spatial-indicators', path: '/health/spatial',   label: 'المؤشرات المكانية', icon: MapIcon },
      { id: 'phenology',          path: '/health/phenology', label: 'مراحل النموّ', icon: Sprout },
      { id: 'scouting',           path: '/health/scouting',  label: 'دليل الاستكشاف', icon: Bug },
      { id: 'pest-escalation',    path: '/health/pest',      label: 'تصعيد الآفة', icon: Bug },
      { id: 'field-intelligence', path: '/health/maestro',   label: 'المايسترو', icon: Activity },
    ],
  },
  {
    id: 'irrigation-crop', label: 'الريّ والمحصول', icon: Droplets, defaultOpen: false,
    items: [
      { id: 'irrigation',        path: '/irrigation',          label: 'تحليل ماء الريّ', icon: Droplets },
      { id: 'irrigation-plan',   path: '/irrigation/plan',     label: 'خطّة الريّ المتنبّأ', icon: CalendarRange },
      { id: 'irrigation-ops',    path: '/irrigation/ops',      label: 'الري التشغيلي', icon: Waypoints },
      { id: 'irrigation-network', path: '/irrigation/network', label: 'توأم شبكة الريّ', icon: Share2, badge: 'جديد' },
      { id: 'portfolio',         path: '/irrigation/portfolio', label: 'توزيع ماء المزرعة', icon: Layers },
      { id: 'portfolio-command', path: '/irrigation/portfolio-command', label: 'مركز قيادة المحفظة', icon: Crosshair, badge: 'جديد' },
      { id: 'crop-state',        path: '/crop/state',          label: 'حالة المحصول الموحّدة', icon: Sprout },
      { id: 'weather-advice',    path: '/crop/weather',        label: 'الطقس والريّ', icon: CloudRain },
    ],
  },
  {
    id: 'data-analysis', label: 'البيانات والتحليل', icon: BarChart3, defaultOpen: false,
    items: [
      { id: 'analytics',     path: '/analysis',            label: 'التحليلات', icon: BarChart3 },
      { id: 'economics',     path: '/analysis/economics',  label: 'الاقتصاد / ROI', icon: BarChart3 },
      { id: 'field-ranking', path: '/analysis/field-ranking', label: 'ترتيب الحقول', icon: TrendingUp },
      { id: 'problem-fields', path: '/analysis/problem-fields', label: 'حقول المشكلات', icon: AlertTriangle },
      { id: 'nl-gis',        path: '/analysis/nl-gis',     label: 'استعلام GIS باللغة الطبيعيّة', icon: Search, badge: 'جديد' },
      { id: 'scenario-compare', path: '/analysis/scenario-compare', label: 'مقارنة السياسات', icon: GitCompare },
    ],
  },
  {
    id: 'reports', label: 'التقارير', icon: FileText, defaultOpen: false,
    items: [
      { id: 'reports',         path: '/reports',         label: 'التقارير', icon: FileText },
      { id: 'advisory-report', path: '/reports/advisory', label: 'استشارة المزرعة', icon: FileText },
      { id: 'recommendations', path: '/reports/recommendations', label: 'التوصيات', icon: ClipboardList },
    ],
  },
  {
    id: 'advanced', label: 'الذكاء المتقدّم', icon: FlaskConical, defaultOpen: false,
    items: [
      { id: 'decision-studio',     path: '/advanced/decision-studio',     label: 'استوديو القرار', icon: FlaskConical, badge: 'جديد' },
      { id: 'decision-confidence', path: '/advanced/decision-confidence', label: 'ثقة القرار الموحَّدة', icon: Gauge, badge: 'جديد' },
      { id: 'execution-feedback',  path: '/advanced/execution-feedback',  label: 'رصد حلقة التنفيذ', icon: Repeat, badge: 'جديد' },
      { id: 'agronomic-timeline',  path: '/advanced/agronomic-timeline',  label: 'الخطّ الزمنيّ الأغرونوميّ', icon: GitCommitHorizontal, badge: 'جديد' },
      { id: 'learning-dashboard',  path: '/advanced/learning',            label: 'لوحة رصد التعلّم', icon: BarChart3 },
      { id: 'calibration',         path: '/advanced/calibration',         label: 'حالة المعايرة الإقليميّة', icon: Activity },
      { id: 'calibration-workbench', path: '/advanced/calibration-workbench', label: 'منضدة المعايرة', icon: SlidersHorizontal, badge: 'جديد' },
      { id: 'lineage',             path: '/advanced/lineage',             label: 'سلسلة النَّسَب والدليل', icon: GitBranch },
      { id: 'evidence-map',        path: '/advanced/evidence-map',        label: 'خريطة الدليل', icon: ShieldCheck, badge: 'جديد' },
      { id: 'replay-map',          path: '/advanced/replay-map',          label: 'إعادة تشغيل الموسم', icon: History, badge: 'جديد' },
    ],
  },
  {
    id: 'operations', label: 'العمليّات', icon: FolderKanban, defaultOpen: false,
    items: [
      { id: 'tasks',       path: '/ops/tasks',       label: 'المهام الميدانية', icon: ClipboardList },
      { id: 'activities',  path: '/ops/activities',  label: 'العمليّات الزراعيّة', icon: Sprout },
      { id: 'inventory',   path: '/ops/inventory',   label: 'المخزون', icon: Boxes },
      { id: 'equipment',   path: '/ops/equipment',   label: 'المعدّات', icon: Tractor },
      { id: 'devices',     path: '/ops/devices',     label: 'أجهزة IoT', icon: Cpu },
      { id: 'device-twin', path: '/ops/device-twin', label: 'توائم الأجهزة وثقة الحسّاس', icon: Activity, badge: 'جديد' },
    ],
  },
  {
    id: 'preview', label: 'التطبيق الموحّد (معاينة)', icon: Smartphone, defaultOpen: false,
    items: [
      { id: 'unified-cabin',  path: '/preview/unified',  label: 'التطبيق الموحّد (معاينة)', icon: Smartphone, badge: '٦ وجهات' },
      { id: 'command',        path: '/preview/command',  label: 'مركز العمليّات (معاينة)', icon: Smartphone, badge: 'دمج' },
      { id: 'tasks-cabin',    path: '/preview/tasks',    label: 'كابينة المهام (معاينة)', icon: ListChecks, badge: 'دمج' },
      { id: 'rec-flow',       path: '/preview/rec-flow', label: 'توصية ← تنفيذ (معاينة)', icon: ClipboardList, badge: 'دمج' },
      { id: 'hybrid-monitor', path: '/preview/hybrid-monitor', label: 'المراقبة الهجينة (معاينة)', icon: Activity, badge: 'دمج' },
      { id: 'analyze-cabin',  path: '/preview/analyze',  label: 'التحليل (معاينة)', icon: BarChart3, badge: 'دمج' },
      { id: 'setup-cabin',    path: '/preview/setup',    label: 'الإعداد (معاينة)', icon: Settings, badge: 'دمج' },
      { id: 'field-app',      path: '/preview/field-app', label: 'تطبيق الحقل (معاينة)', icon: Smartphone, badge: 'جديد' },
    ],
  },
  {
    id: 'admin', label: 'الإدارة والإعدادات', icon: Wrench, defaultOpen: false,
    items: [
      { id: 'master-data', path: '/admin/master-data', label: 'البيانات المرجعيّة', icon: Database },
      { id: 'documents',   path: '/admin/documents',   label: 'الوثائق', icon: FolderArchive },
      { id: 'governance',  path: '/admin/governance',  label: 'الحوكمة والتدقيق', icon: ShieldCheck },
      { id: 'settings',    path: '/settings',          label: 'الإعدادات', icon: Settings },
    ],
  },
];

// ── قائمة مُسطّحة بكلّ المسارات (للبحث/التحويل) ─────────────────
export const ALL_ROUTES: RouteDef[] = NAV_SECTIONS.flatMap((s) => s.items);

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
