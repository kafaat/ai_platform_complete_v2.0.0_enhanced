import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس تسريب: خطّاف الاختبار E2E `window.__hubmap` يعرِّض دوالّ تعديل داخليّة للخريطة
// (addPin · getDraw().addFeatures · project/unproject). يجب أن يبقى **محروساً خلف
// عَلَم البناء `VITE_E2E_HOOKS`** فلا يتسرّب إلى بناء الإنتاج/Docker. هذا الحارس يقفل
// البوّابة: يفشل إن أُسنِد `__hubmap` دون سبقه بحارس `VITE_E2E_HOOKS`.
const src = readFileSync(
  join(process.cwd(), 'src/components/maphub/HubMapGL.tsx'),
  'utf8',
);

describe('__hubmap test bridge production-leak guard', () => {
  it('exposes window.__hubmap only behind the VITE_E2E_HOOKS build flag', () => {
    const guard = "import.meta.env.VITE_E2E_HOOKS !== '1'";
    const assignIdx = src.indexOf('.__hubmap =');
    expect(assignIdx).toBeGreaterThan(-1); // الخطّاف موجود
    const guardIdx = src.indexOf(guard);
    expect(guardIdx).toBeGreaterThan(-1); // الحارس موجود
    // الإسناد يقع بعد الحارس (داخل نفس التأثير المحروس) — لا تسريب غير محروس.
    expect(assignIdx).toBeGreaterThan(guardIdx);
  });

  it('has no unconditional window.__hubmap assignment', () => {
    // لا يجوز أن يُسنَد __hubmap في سطر لا يسبقه الحارس ضمن نافذة قريبة.
    const guardIdx = src.indexOf("import.meta.env.VITE_E2E_HOOKS !== '1'");
    const assignIdx = src.indexOf('.__hubmap =');
    // المسافة بين الحارس والإسناد صغيرة (نفس كتلة التأثير) — لا إسناد منفصل مُبكّر.
    expect(assignIdx - guardIdx).toBeGreaterThan(0);
    expect(assignIdx - guardIdx).toBeLessThan(1200);
  });
});
