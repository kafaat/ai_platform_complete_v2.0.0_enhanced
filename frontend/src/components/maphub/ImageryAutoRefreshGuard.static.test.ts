import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');

// FINDING-007 / v3-Finding-5: تأثير auto-refresh في MapHub كان يستدعي
// refreshFieldImagery لكلّ تاريخ مختار بلا فحص توفّر COG — فيُعيد معالجة تاريخ
// تاريخيّ له أصل جاهز (هدر + قد يُعيد كتابة أصل). الحارس يؤكّد أنّ الحارس has_cog
// مضبوط: لا إطلاق حين التاريخ التاريخيّ يملك COG جاهزاً، والإطلاق يبقى لـlatest/غياب COG.
describe('MapHub imagery auto-refresh has_cog guard', () => {
  it('short-circuits refresh when the selected historical date already has a COG', () => {
    // نحصر الفحص على كتلة تأثير auto-refresh (حول refreshFieldImagery).
    const idx = mapHub.indexOf('refreshFieldImagery(fieldId, selectedImageryDate)');
    expect(idx).toBeGreaterThan(-1);
    const block = mapHub.slice(Math.max(0, idx - 900), idx);
    // يبحث عن خيار التاريخ المختار ويقرأ has_cog قبل الإطلاق.
    expect(block).toContain('availableImageryDates.find');
    expect(block).toContain('readyOption?.has_cog');
    // «latest» يُستثنى من الحارس (يبقى يُطلق لضمان أحدث مشهد).
    expect(block).toContain("selectedImageryDate !== 'latest'");
  });

  it('re-evaluates when available dates load (has_cog signal in effect deps)', () => {
    const idx = mapHub.indexOf('refreshFieldImagery(fieldId, selectedImageryDate)');
    const after = mapHub.slice(idx, idx + 600);
    // مصفوفة الاعتماديّات تشمل availableImageryDates كي يُعاد التقييم عند وصول الإشارة.
    expect(after).toContain('availableImageryDates]');
  });
});
