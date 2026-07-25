// ═══════════════════════════════════════════════════════════════
// SAHOOL — قشرة FieldView · الشريط السفليّ للموبايل (MobileTabBar)
// ───────────────────────────────────────────────────────────────
// يعيد استخدام BottomTabBar من ds/merge لعرض أهمّ الأقسام (IA) في أسفل
// الشاشة على الموبايل. كلّ تبويب يفتح أوّل صفحة مسموح بها في قسمه (RBAC).
// نُخفي قسماً ليس فيه أيّ صفحة مسموح بها للدور الحاليّ. التمييز النشط من
// مسار URL (الراوتر مصدر الحقيقة). يظهر فقط على الشاشات الصغيرة (md:hidden).
// ═══════════════════════════════════════════════════════════════
import { createElement } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { BottomTabBar } from '../ds';
import { useAuthStore } from '../../hooks/useAuth';
import { canAccess } from '../../lib/permissions';
import { isPageEnabled } from '../../lib/featureFlags';
import { isRuntimePageEnabled, useFeatureRegistry } from '../../hooks/useFeatureRegistry';
import { NAV_SECTIONS, pageForPath, type NavSection } from '../../lib/routes';

// الأقسام المعروضة في الشريط السفليّ (أهمّها — البقيّة عبر شريط التنقّل الكامل).
const PRIMARY_SECTION_IDS = ['overview', 'fields-map', 'field-health', 'irrigation-crop', 'operations'];

export default function MobileTabBar() {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const activePage = pageForPath(location.pathname);
  // سجلّ الميزات الحيّ — نُرشِّح به تماماً كـNavRail كي لا يظهر عنصر معطَّل وقت‌تشغيلاً
  // في شريط تبويب الموبايل بينما هو مخفيّ في NavRail (توحيد ترشيح التنقّل — F-UI-02).
  const featureRegistry = useFeatureRegistry();

  const allowedItems = (s: NavSection) =>
    s.items.filter((i) => isPageEnabled(i.id) && isRuntimePageEnabled(i.id, featureRegistry) && canAccess(user?.role, i.id) && !i.hidden);

  // أقسام لها عنصر مسموح به واحد على الأقلّ، ضمن المجموعة الأساسيّة.
  const sections = NAV_SECTIONS
    .filter((s) => PRIMARY_SECTION_IDS.includes(s.id))
    .map((s) => ({ section: s, items: allowedItems(s) }))
    .filter((x) => x.items.length > 0);

  if (sections.length === 0) return null;

  // القسم النشط = القسم الذي يحوي الصفحة الحاليّة.
  const activeSectionId =
    sections.find((x) => x.items.some((i) => i.id === activePage))?.section.id
    ?? sections[0].section.id;

  const tabs = sections.map(({ section }) => ({
    id: section.id,
    label: section.label,
    icon: createElement(section.icon, { size: 16 }),
  }));

  return (
    <div className="md:hidden">
      <BottomTabBar
        tabs={tabs}
        active={activeSectionId}
        onChange={(sectionId) => {
          const target = sections.find((x) => x.section.id === sectionId);
          // افتح أوّل صفحة مسموح بها في القسم.
          if (target?.items[0]) navigate(target.items[0].path);
        }}
      />
    </div>
  );
}
