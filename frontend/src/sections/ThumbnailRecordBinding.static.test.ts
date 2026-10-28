// حارس ساكن لتوصيل المصغّرات (thumb-web) في صفحتين ثقيلتين يصعب تركيبهما في jsdom.
// السلوك نفسه مُختبَر وحدويّاً في timelineByDay / captureTime / DateScrubber /
// ImageryTimelineThumb؛ هنا نثبت أنّ الصفحات تستهلك تلك الدوالّ لا نسخاً مضمَّنة منها.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const satellite = readFileSync(resolve(__dirname, 'SatellitePage.tsx'), 'utf8');
const mapHub = readFileSync(resolve(__dirname, 'MapHub.tsx'), 'utf8');
const api = readFileSync(resolve(__dirname, '../services/api.ts'), 'utf8');

describe('T2 — SatellitePage: صورة اليوم ووقته من سجلّ واحد', () => {
  it('لا ربطان مستقلّان (Map.set الأخير يغلب + find الأوّل يغلب)', () => {
    expect(satellite).not.toMatch(/timelineItems\.find\(/);
    expect(satellite).toContain('timelineRecordByDay(timelineItems)');
  });
});

describe('T5 — MapHub: عنوان تاريخ الالتقاط بسياسة UTC الموحّدة', () => {
  it('لا Intl.DateTimeFormat بلا منطقة؛ يستعمل captureLabel', () => {
    const block = mapHub.slice(mapHub.indexOf('const acquisitionLabel'), mapHub.indexOf('const visibleFields'));
    expect(block).not.toContain('Intl.DateTimeFormat');
    expect(block).toContain('captureLabel(');
  });
});

describe('T7 — المنتَج المعروض في المصغّرة موسوم', () => {
  it('النوع يحمل thumbnail_index الذي يُرجعه الخادم', () => {
    expect(api).toContain('thumbnail_index?: string | null');
  });
  it('SatellitePage يمرّر thumbProduct؛ MapHub يمرّر product', () => {
    expect(satellite).toContain('thumbProduct');
    expect(mapHub).toMatch(/<ImageryTimelineThumb[\s\S]{0,1200}product=\{/);
  });
});
