// v54 guard: TrueColor must be a real raster-service Sentinel-2 layer, not just a UI default.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const mapHub = readFileSync(join(here, 'MapHub.tsx'), 'utf8');
const hubMap = readFileSync(join(here, '../components/maphub/HubMap.tsx'), 'utf8');
const hubMapGL = readFileSync(join(here, '../components/maphub/HubMapGL.tsx'), 'utf8');
// باني رابط البلاطة استُخرِج إلى وحدة مُشترَكة قابلة للاختبار (indicatorTileUrl.ts) —
// نتحقّق من العقد فيها، ومن أنّ كِلا المحرّكَين (HubMap/HubMapGL) يستعملانه.
const tileUrl = readFileSync(join(here, '../components/maphub/indicatorTileUrl.ts'), 'utf8');
const api = readFileSync(join(here, '../services/api.ts'), 'utf8');
const layerRegistry = readFileSync(join(here, '../lib/layerRegistry.ts'), 'utf8');

describe('v54 TrueColor runtime verification', () => {
  it('keeps TrueColor as the protected default and checks raster-service tilejson (Element84 COG)', () => {
    expect(mapHub).toContain("const RAW_IMAGERY_INDEX_ID = 'truecolor'");
    expect(mapHub).toContain('rasterApi');
    expect(mapHub).toContain('/v1/fields/${fieldId}/tilejson');
    expect(mapHub).toContain('index: RAW_IMAGERY_INDEX_ID');
    expect(mapHub).toContain('truecolor-runtime-readiness');
    expect(mapHub).toContain('TRUECOLOR_UNAVAILABLE_MESSAGE');
  });

  it('renders TrueColor through raster-service cdse-tiles with field polygon clipping, not as the basemap', () => {
    // البلاطة مُقولَبة: `${segment}/{z}/{x}/{y}.png` حيث segment = cdse-tiles الحيّ افتراضاً
    // (أو /tiles المحفوظ حين التاريخ has_cog). المنطق في الباني المُشترَك (indicatorTileUrl.ts).
    expect(tileUrl).toContain('/v1/fields/${field.id}/${segment}/{z}/{x}/{y}.png');
    expect(tileUrl).toContain("preferPersistedCog ? 'tiles' : 'cdse-tiles'");
    expect(tileUrl).toContain("params.set('poly'");
    expect(tileUrl).toContain("params.set('bbox_w'");
    expect(tileUrl).toContain('access_token');
    // وكِلا المحرّكَين يستعملان الباني المُشترَك فينطبق العقد عليهما.
    expect(hubMap).toContain('indicatorTileUrl(');
    expect(hubMapGL).toContain('indicatorTileUrl(');
  });

  it('does not show numeric scale legends for TrueColor', () => {
    expect(layerRegistry).toContain("id: 'truecolor'");
    expect(layerRegistry).toContain("source: 'truecolor'");
    const truecolorEntry = layerRegistry.slice(layerRegistry.indexOf("id: 'truecolor'"), layerRegistry.indexOf("id: 'ndvi'"));
    expect(truecolorEntry).not.toContain('colormap:');
    expect(mapHub).toContain('indicatorActive !== RAW_IMAGERY_INDEX_ID');
  });

  it('API tile builders preserve truecolor and do not normalize it back to ndvi', () => {
    expect(api).toContain('normalizeIndicatorIndex(index)');
    expect(api).toContain('/v1/fields/${fieldId}/cdse-tiles/{z}/{x}/{y}.png');
    expect(api).not.toContain("truecolor: 'ndvi'");
  });
});
