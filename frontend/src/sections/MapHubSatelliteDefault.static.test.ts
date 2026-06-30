// حارس ساكن: يقفل سلوك «صورة الحقل الخام هي الافتراضيّ» + الأسطورة العموديّة الموحَّدة
// (قرار المستخدم المؤكَّد). يمنع الانحدار إلى افتراضيّ NDVI أو الأسطورة الأفقيّة القديمة.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const mapHub = readFileSync(join(here, 'MapHub.tsx'), 'utf8');
const myFields = readFileSync(join(here, 'MyFieldsPage.tsx'), 'utf8');

describe('MapHub: صورة الحقل الافتراضيّة + أسطورة المقياس العموديّة', () => {
  it('لا يفتح الطقس افتراضيّاً عند القدوم من «حقولي»', () => {
    expect(mapHub).not.toContain("|| initialSearch.get('source') === 'my-fields';");
    expect(myFields).not.toContain('weather=1');
    expect(myFields).not.toContain('showWeather: true');
  });

  it('الافتراضيّ صورة الحقل الخام (بلا طبقة مؤشّر مفروضة NDVI)', () => {
    // مؤشّر صريح بالرابط يُحترَم، وإلّا null (صورة القمر الصناعيّ الخام).
    expect(mapHub).toContain('requestedCdseOpen ? (routeIndicator ?? null)');
    expect(mapHub).not.toContain("requestedCdseOpen ? (routeIndicator || 'ndvi')");
    // لا يُحقَن index=ndvi في رابط الانتقال من «حقولي».
    expect(myFields).not.toContain('index=ndvi');
  });

  it('أسطورة المقياس عموديّة موحَّدة (MapIndicatorLegend) تظهر عند تفعيل مؤشّر', () => {
    expect(mapHub).toContain('MapIndicatorLegend');
    expect(mapHub).toContain('INDEX_DOMAIN');
    // مشروطة بوجود مؤشّر نشط (لا تظهر فوق صورة الحقل المجرّدة).
    expect(mapHub).toContain('indicatorActive &&');
  });
});
