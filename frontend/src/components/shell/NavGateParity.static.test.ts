import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const app = readFileSync(join(root, 'src/App.tsx'), 'utf8');
const navRail = readFileSync(join(root, 'src/components/shell/NavRail.tsx'), 'utf8');
const mobileTab = readFileSync(join(root, 'src/components/shell/MobileTabBar.tsx'), 'utf8');
const cmdPalette = readFileSync(join(root, 'src/components/shell/CommandPalette.tsx'), 'utf8');

// F-UI-01: المساران الديناميكيّان للورشة (/fields/:id/workspace و/field/:id/workspace)
// كانا يعرضان <FieldWorkspaceRouteShell/> مباشرةً متجاوزَين حارس renderPage (RBAC +
// علم الميزة). الحارس يؤكّد أنّهما يمرّان الآن عبر guardPage('field-workspace').
describe('F-UI-01 — dynamic workspace routes pass through the RBAC/feature gate', () => {
  it('defines a shared guardPage(targetPage, node) helper', () => {
    expect(app).toContain('const guardPage = (targetPage: PageId, node: React.ReactNode)');
    // الحارس يطبّق كِلا الفحصَين على الصفحة المستهدَفة.
    expect(app).toContain('canAccess(user?.role, targetPage)');
    expect(app).toContain('isRuntimePageEnabled(targetPage, featureRegistry)');
  });

  it('routes both workspace paths through guardPage instead of rendering the shell directly', () => {
    for (const path of ['/fields/:fieldId/workspace', '/field/:fieldId/workspace']) {
      const idx = app.indexOf(`path="${path}"`);
      expect(idx).toBeGreaterThan(-1);
      const block = app.slice(idx, idx + 220);
      expect(block).toContain("guardPage('field-workspace'");
    }
    // لا عرض مباشر للورشة كعنصر مسار غير محروس.
    expect(app).not.toContain('element={<FieldWorkspaceRouteShell />}');
  });
});

// F-UI-02: NavRail يُرشّح بـisRuntimePageEnabled بينما MobileTabBar وCommandPalette
// كانا يُغفلانه — فتظهر صفحة معطَّلة وقت‌تشغيلاً في التبويب/لوحة الأوامر بينما هي
// مخفيّة في الشريط. الحارس يؤكّد توحيد الترشيح عبر الأسطح الثلاثة.
describe('F-UI-02 — runtime feature filtering is unified across nav surfaces', () => {
  it('NavRail filters by isRuntimePageEnabled (baseline)', () => {
    expect(navRail).toContain('isRuntimePageEnabled(');
  });
  it('MobileTabBar filters by isRuntimePageEnabled', () => {
    expect(mobileTab).toContain('useFeatureRegistry');
    expect(mobileTab).toContain('isRuntimePageEnabled(i.id, featureRegistry)');
  });
  it('CommandPalette filters by isRuntimePageEnabled', () => {
    expect(cmdPalette).toContain('useFeatureRegistry');
    expect(cmdPalette).toContain('isRuntimePageEnabled(r.id, featureRegistry)');
  });
});
