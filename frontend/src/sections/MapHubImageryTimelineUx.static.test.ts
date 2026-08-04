import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'src/sections/MapHub.tsx'), 'utf8');
const rasterFields = readFileSync(
  join(process.cwd(), '../services/raster-service/routers/fields.py'),
  'utf8',
);
const platformFacade = readFileSync(
  join(process.cwd(), '../services/sahool-platform/api/routers/field_workspace_imagery.py'),
  'utf8',
);

describe('شريط المشاهد التاريخيّة — وقت الالتقاط والتمرير الأفقيّ', () => {
  it('العقد موصول من الكتالوج إلى البطاقة، لا مقطوعاً عند آخر ميل', () => {
    // كان `acquisition_datetime` مُصرَّحاً في raster-service وواجهة المنصّة ونوع الـTS،
    // ولا تقرؤه الشاشة — فالبطاقة تدّعي تاريخ التقاط بلا شاهد عليه.
    expect(rasterFields).toContain('"acquisition_datetime"');
    expect(platformFacade).toContain('"acquisition_datetime": row.get("acquisition_datetime")');
    expect(source).toContain('captureTime(d.acquisition_datetime, d.date)');
  });

  it('الساعة تُعرَض موسومة بـUTC، ولا تُحوَّل إلى توقيت المتصفّح', () => {
    // التاريخ المعروض مشتقّ خادميّاً من الطابع بـUTC؛ عرض الساعة محلّيّاً يضع سطرين
    // متناقضين على البطاقة الواحدة (تاريخ UTC وساعة قد تقع في يوم آخر).
    expect(source).toContain('data-testid="imagery-capture-time"');
    expect(source).not.toMatch(/toLocaleTimeString\([^)]*\)[^\n]*acquisition/);
  });

  it('تناقض الطابع مع تاريخ البطاقة يُعرَض ولا يُبتلَع', () => {
    expect(source).toContain('data-testid="imagery-capture-mismatch"');
    expect(source).toContain('capture.mismatch');
  });

  it('منطقة التمرير الأفقيّ مُدرَكة بلوحة المفاتيح وقارئ الشاشة', () => {
    // W3C ACT 0ssw9k: منطقة قابلة للتمرير يجب أن تكون قابلة للوصول تسلسليّاً، وأن
    // يُفهَم غرضها. الأزرار داخلها قابلة للتبويب، لكنّ المنطقة كانت بلا اسم ولا دور.
    const strip = source.split('data-testid="imagery-timeline-items"')[1]?.slice(0, 400) ?? '';
    expect(source).toContain('data-testid="imagery-timeline-items"');
    expect(strip).toContain('tabIndex={0}');
    expect(strip).toContain('role="group"');
    expect(strip).toContain('aria-label=');
  });

  it('البطاقة المختارة تُجلَب إلى المرأى بلا تحريك الصفحة', () => {
    // scrollIntoView يُمرّر كلّ سلف قابل للتمرير بما فيه الصفحة؛ الإزاحة المحسوبة
    // تحصر الأثر في الشريط وحده.
    expect(source).toContain('imageryTimelineScrollRef');
    expect(source).toContain('container.scrollTo(');
    expect(source).not.toContain('target.scrollIntoView(');
  });

  it('البطاقة النشطة مُعلَنة دلاليّاً لا بالحدّ الأخضر وحده', () => {
    expect(source).toContain("aria-current={active ? 'true' : undefined}");
  });
});
