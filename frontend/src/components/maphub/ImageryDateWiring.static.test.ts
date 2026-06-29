import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = process.cwd();
const hubMap = readFileSync(join(root, 'src/components/maphub/HubMap.tsx'), 'utf8');
const hubMapGL = readFileSync(join(root, 'src/components/maphub/HubMapGL.tsx'), 'utf8');
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const api = readFileSync(join(root, 'src/services/api.ts'), 'utf8');

describe('MapHub imagery date wiring regression', () => {
  it('does not hard-code date=latest inside Leaflet/MapLibre tile URL builders', () => {
    // عقد التاريخ (D): يمرّر imageryDate المختار شرطيّاً ولا يُثبّت 'latest' (يُسقطه حين latest/فارغ).
    expect(hubMap).toContain("imageryDate && imageryDate !== 'latest'");
    expect(hubMapGL).toContain("imageryDate && imageryDate !== 'latest'");
    expect(hubMap).not.toContain("date: 'latest' });");
    expect(hubMapGL).not.toContain("date: 'latest' });");
  });

  it('fetches available CDSE dates and passes the selected date into both map engines and compare maps', () => {
    expect(api).toContain('fetchFieldImageryAvailableDates');
    expect(mapHub).toContain('data-testid="imagery-date-switcher"');
    expect(mapHub).toContain('selectedImageryDate === \'latest\' ? null : selectedImageryDate');
    expect(mapHub).toContain('imageryDate={imageryDate ?? null}');
  });
});
