import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(root, 'src/services/api.ts'), 'utf8');

// V8-05 PR2 — الثابت الأقوى: اختيار المؤشّر/التاريخ **بلا أثر جانبيّ** إطلاقاً. لا معالجة
// تُطلَق من الاختيار (ولا حتى «latest»). كان الحارس السابق (FINDING-007) يسمح لـ«latest»
// بإطلاق refreshFieldImagery؛ الآن أُزيل تماماً — التجهيز صريح عبر زرّ «عالِج هذا التاريخ».
describe('MapHub date selection is side-effect-free (V8-05 PR2)', () => {
  it('never calls refreshFieldImagery — selection triggers no processing', () => {
    expect(mapHub.includes('refreshFieldImagery(')).toBe(false);
  });

  it('the selection effect only bumps the tile cache (no network, no processing)', () => {
    const idx = mapHub.indexOf('اختيار المؤشّر/التاريخ **بلا أثر جانبيّ**');
    expect(idx).toBeGreaterThan(-1);
    // نافذة كتلة التأثير حول الشرح.
    const block = mapHub.slice(idx, idx + 900);
    expect(block).toContain('setImageryTs(Date.now())');
    // لا استدعاء معالجة داخل تأثير الاختيار.
    expect(block).not.toContain('processFieldImageryDate(');
  });

  it('exposes an explicit "process this date" button wired to process-date', () => {
    expect(mapHub).toContain('data-testid="btn-process-date"');
    expect(mapHub).toContain('processFieldImageryDate(');
    // الزرّ يظهر لتاريخٍ غير جاهز له مشهد فقط (لا يظهر لـlatest/الجاهز).
    expect(mapHub).toContain('opt.has_cog');
    expect(mapHub).toContain('opt.scene_id');
    // api client يستدعي مسار البوّابة الصريح.
    expect(api).toContain("/api/v1/fields/${fieldId}/imagery/process-date");
    expect(api).toContain('reused_existing_job');
  });

  it('surfaces the dual-value AOI cloud contract (#636) in the timeline', () => {
    // يقرأ سحابة الحقل (AOI) مفضّلةً وسحابة المشهد صراحةً.
    expect(mapHub).toContain('d.aoi_cloud_pct');
    expect(mapHub).toContain('d.scene_cloud_pct');
    // api يُمرّر الحقلين من العقد الخادميّ.
    expect(api).toContain('aoi_cloud_pct');
    expect(api).toContain('scene_cloud_pct');
  });
});
