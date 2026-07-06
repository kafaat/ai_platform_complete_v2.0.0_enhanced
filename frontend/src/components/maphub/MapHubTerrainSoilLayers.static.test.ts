import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// حارس ساكن لطبقات التضاريس/التربة في MapHub (V31.6/31.7): يثبّت أسلاك المبدّلات،
// والإغلاق الآمن (البلاطة تُعرَض فقط حين available)، والرسائل الصادقة عند غياب المصدر،
// والأساطير، وإخلاء المسؤوليّة الإلزاميّ لـSoilGrids. سدّ فجوة أشار إليها التدقيق الخارجيّ
// (لا حراسة اختباريّة لهذه الطبقات الجديدة). مسح مصدر (لا تصيير) — يقرأ MapHub.tsx.
const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const hubMapGL = readFileSync(join(root, 'src/components/maphub/HubMapGL.tsx'), 'utf8');

describe('MapHub terrain + soil layer wiring (static guard)', () => {
  it('exposes the three terrain toggles + the soil toggle by testid', () => {
    expect(mapHub).toContain('testid="btn-hillshade"');
    expect(mapHub).toContain('testid="btn-slope"');
    expect(mapHub).toContain('testid="btn-contours"');
    expect(mapHub).toContain('testid="btn-soil"');
  });

  it('renders raster tiles only when the layer reports available (fail-closed)', () => {
    // البلاطة تُبنى فقط عند available:true — لا عرض لهندسة/مصدر غير جاهز.
    expect(mapHub).toContain('showHillshade && hillshadeTj?.available ? hillshadeTileUrl');
    expect(mapHub).toContain('showSlope && slopeTj?.available ? slopeTileUrl');
    expect(mapHub).toContain('showSoil && soilTj?.available ? soilTileUrl');
  });

  it('shows an honest unavailable message per layer (no silent blank)', () => {
    expect(mapHub).toContain('data-testid="hillshade-unavailable"');
    expect(mapHub).toContain('data-testid="slope-unavailable"');
    expect(mapHub).toContain('data-testid="soil-unavailable"');
  });

  it('renders slope + soil legends from the server tilejson legend', () => {
    expect(mapHub).toContain('data-testid="slope-legend"');
    expect(mapHub).toContain('data-testid="soil-legend"');
  });

  it('always shows the mandatory SoilGrids disclaimer when the layer is active', () => {
    // صدق صارم: SoilGrids تقدير ~250م لإرشاد أخذ العيّنات لا بديل عن مختبر.
    expect(mapHub).toContain('data-testid="soil-disclaimer"');
    expect(mapHub).toContain('soilTj?.disclaimer &&');
    expect(mapHub).toContain('ليست بديلاً عن تحليل مختبر');
  });

  it('gates soil sample points on the toggle + a selected field geometry', () => {
    expect(mapHub).toContain('testid="btn-soil-samples"');
    // العيّنات تُجلَب فقط عند التفعيل؛ وتُمسح عند إيقافه (لا نقاط مُلفَّقة بلا مصدر).
    expect(mapHub).toContain('if (!showSoilSamples) { setSoilSamplePoints([]);');
  });

  it('passes terrain/soil layers to BOTH map engines (Leaflet HubMap + MapLibre HubMapGL)', () => {
    // P0: كانت الطبقات تصل Leaflet فقط؛ الآن تُمرَّر لـHubMapGL أيضاً (تكافؤ المحرّكين).
    for (const engine of ['HubMap', 'HubMapGL']) {
      const idx = mapHub.indexOf(`<${engine}`);
      expect(idx, `${engine} غير موجود`).toBeGreaterThan(-1);
      const block = mapHub.slice(idx, idx + 1600);
      expect(block, `${engine} لا يستقبل hillshadeTilesUrl`).toContain('hillshadeTilesUrl=');
      expect(block, `${engine} لا يستقبل soilTilesUrl`).toContain('soilTilesUrl=');
      expect(block, `${engine} لا يستقبل contours`).toContain('contours=');
    }
  });

  it('HubMapGL actually adds terrain/soil raster + contour layers to the GL map', () => {
    expect(hubMapGL).toContain('LYR_HILLSHADE');
    expect(hubMapGL).toContain('LYR_SLOPE');
    expect(hubMapGL).toContain('LYR_SOIL');
    expect(hubMapGL).toContain('LYR_CONTOURS');
    // fail-closed: بلا رابط ⇒ تُزال الطبقة (لا بلاطة معلّقة).
    expect(hubMapGL).toContain('if (!url) return;');
  });
});
