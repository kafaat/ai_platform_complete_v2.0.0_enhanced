import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const popup = readFileSync(join(root, 'src/components/maphub/weather/WeatherProbePopup.ts'), 'utf8');
const reports = readFileSync(join(root, 'src/sections/ReportsPage.tsx'), 'utf8');

// F5-08: أزرار الطقس (إنشاء مهمّة/حفظ توصية) تحمل مفتاح idempotency ثابتاً فلا تُكرِّر عند إعادة المحاولة.
describe('F5-08 — weather popup actions carry a deterministic idempotency key', () => {
  it('both weather POSTs send an Idempotency-Key header', () => {
    const count = (popup.match(/'Idempotency-Key':/g) ?? []).length;
    expect(count).toBeGreaterThanOrEqual(2);
    expect(popup).toContain('wx-task:');
    expect(popup).toContain('wx-rec:');
  });
});

// continuation-3 P1: تصدير CSV في التقارير يُبطِل object URL بعد التنزيل (لا تسريب).
describe('ReportsPage — CSV export revokes its object URL', () => {
  it('revokeObjectURL is called after the download click', () => {
    expect(reports).toContain('URL.revokeObjectURL(url)');
  });
});
