// حارس ساكن: يقفل سلوك «صورة الحقل الخام TrueColor هي الافتراضيّ» + الأسطورة العموديّة
// (قرار المستخدم المؤكَّد). يمنع الانحدار إلى افتراضيّ weather أو NDVI.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const here = dirname(fileURLToPath(import.meta.url));
const mapHub = readFileSync(join(here, 'MapHub.tsx'), 'utf8');
const myFields = readFileSync(join(here, 'MyFieldsPage.tsx'), 'utf8');
const layerRegistry = readFileSync(join(here, '../lib/layerRegistry.ts'), 'utf8');

describe('MapHub: صورة الحقل الخام TrueColor كافتراضي محمي', () => {
  it('لا يفتح الطقس افتراضياً ولا يستعيد showWeather من workspace', () => {
    expect(mapHub).toContain('const [showWeather, setShowWeather] = useState(requestedWeatherOpen)');
    expect(mapHub).not.toContain('useState(savedWorkspace?.showWeather ?? false)');
    expect(myFields).not.toContain('weather=1');
    expect(myFields).not.toContain('showWeather: true');
  });

  it('يفتح الحقل من حقولي على truecolor وليس NDVI أو null', () => {
    expect(mapHub).toContain("const RAW_IMAGERY_INDEX_ID = 'truecolor'");
    expect(mapHub).toContain('requestedCdseOpen ? (routeIndicator ?? RAW_IMAGERY_INDEX_ID)');
    expect(myFields).toContain('indicator=truecolor');
    expect(myFields).toContain("indicator: 'truecolor'");
    expect(mapHub).not.toContain("requestedCdseOpen ? (routeIndicator ?? null)");
    expect(mapHub).not.toContain("requestedCdseOpen ? (routeIndicator || 'ndvi')");
    expect(myFields).not.toContain('index=ndvi');
  });

  it('truecolor مسجل كطبقة raster ولا يعرض scale legend رقمي', () => {
    expect(layerRegistry).toContain("id: 'truecolor'");
    expect(layerRegistry).toContain("source: 'truecolor'");
    expect(mapHub).toContain('indicatorActive !== RAW_IMAGERY_INDEX_ID');
    expect(mapHub).toContain('MapIndicatorLegend');
  });
});
