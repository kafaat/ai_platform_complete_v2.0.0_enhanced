import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس ساكن لعرض «تاريخ الالتقاط»: MapHub يعرض وقت التقاط المشهد الحقيقيّ (من كتالوج
// STAC عبر acquisition_datetime) بجانب مبدّل التاريخ. صدق: عند غياب الوقت يعرض التاريخ
// وحده (acquisition_date تاريخ بلا ساعة) — لا اختلاق ساعة. يقرأ MapHub.tsx + api.ts.
const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(root, 'src/services/api.ts'), 'utf8');

describe('MapHub shows honest satellite acquisition date', () => {
  it('api parses acquisition_datetime into the imagery date option', () => {
    expect(api).toContain('acquisition_datetime');
    // النوع يحمل الحقل (ISO8601 أو null عند غياب المشهد).
    expect(api).toContain('acquisition_datetime?: string | null');
  });

  it('MapHub derives acquisitionLabel from the real scene time (fallback to date only)', () => {
    expect(mapHub).toContain('acquisitionLabel');
    expect(mapHub).toContain('selectedScene');
    // الوقت الحقيقيّ حين توفّره، وإلّا التاريخ وحده (لا ساعة مُختلَقة).
    expect(mapHub).toContain('selectedScene.acquisition_datetime');
    expect(mapHub).toContain('return selectedScene.date;');
  });

  it('MapHub renders the acquisition-date line with a testid', () => {
    expect(mapHub).toContain('data-testid="imagery-acquisition-date"');
    expect(mapHub).toContain('تاريخ الالتقاط:');
  });
});
