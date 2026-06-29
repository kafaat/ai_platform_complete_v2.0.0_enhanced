import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const weatherDir = join(process.cwd(), 'src/components/maphub/weather');
const overlay = readFileSync(join(weatherDir, 'WeatherRasterOverlay.tsx'), 'utf8');
const defs = readFileSync(join(weatherDir, 'weatherLayerDefinitions.ts'), 'utf8');
const tile = readFileSync(join(weatherDir, 'WeatherTileLayer.ts'), 'utf8');
const panel = readFileSync(join(weatherDir, 'WeatherLayerPanel.ts'), 'utf8');
const probe = readFileSync(join(weatherDir, 'WeatherProbePopup.ts'), 'utf8');
const preferences = readFileSync(join(weatherDir, 'weatherPreferences.ts'), 'utf8');

describe('SAHOOL weather engine static architecture', () => {
  it('keeps weather rendering delegated to dedicated modules', () => {
    expect(existsSync(join(weatherDir, 'WeatherTileLayer.ts'))).toBe(true);
    expect(existsSync(join(weatherDir, 'WeatherLayerPanel.ts'))).toBe(true);
    expect(existsSync(join(weatherDir, 'WeatherProbePopup.ts'))).toBe(true);
    expect(overlay).toContain('createWeatherWindGridLayer');
    expect(overlay).toContain('createWeatherControl');
    expect(overlay).toContain('registerWeatherProbePopup');
  });

  it('uses SAHOOL weather APIs instead of external weather tiles', () => {
    expect(tile).toContain('/api/v1/weather/tile-data/');
    expect(tile).toContain('/api/v1/weather/operation-tile-data/');
    expect(tile).toContain('interpolation=grid');
    expect(defs).toContain('WeatherInterpolationPayload');
    expect(tile).not.toContain('tile.openweathermap');
    expect(tile).not.toContain('meteoblue');
  });

  it('supports agricultural operation layers and controls', () => {
    expect(defs).toContain('operation_spraying');
    expect(defs).toContain('operation_irrigation');
    expect(defs).toContain('operation_harvesting');
    expect(defs).toContain('operation_sowing');
    expect(panel).toContain('data-opacity');
    expect(panel).toContain('data-wind-toggle');
    expect(panel).toContain('data-density');
    expect(panel).toContain('data-model');
    // شريط الزمن (time scrubber) + زر تشغيل/إيقاف العرض الزمني على نمط meteoblue.
    expect(panel).toContain('data-time-slider');
    expect(panel).toContain('data-play');
  });

  it('supports probe, operation window, and operation plan popups', () => {
    expect(probe).toContain('/api/v1/weather/probe');
    expect(probe).toContain('/api/v1/weather/operation-window');
    expect(probe).toContain('/api/v1/weather/operation-plan');
  });

  it('supports action bridge buttons from weather decisions', () => {
    expect(probe).toContain('/api/v1/weather/action-recommendation');
    expect(probe).toContain('/api/v1/weather/tasks/from-operation-plan');
    expect(probe).toContain('/api/v1/weather/recommendations/from-operation-plan');
    expect(probe).toContain('إنشاء مهمة من أفضل نافذة');
    expect(probe).toContain('حفظ كتوصية طقس');
  });

  it('attaches auth headers to every weather fetch (production auth_request + POST require_permission)', () => {
    // حارس انحدار: نقاط /api/v1/weather/* خلف auth_request؛ وبالأخصّ POST إنشاء
    // المهمّة/التوصية محميّان بـrequire_permission. فكلّ طلب يجب أن يُرفِق Bearer عبر
    // weatherFetchHeaders (GET) أو weatherJsonHeaders (POST) — وإلّا 401/403.
    expect(defs).toContain('weatherFetchHeaders');
    expect(defs).toContain('weatherJsonHeaders');
    expect(defs).toContain('getAccessToken');
    expect(tile).toContain('weatherFetchHeaders()');
    expect(probe).toContain('weatherFetchHeaders()');
    expect(probe).toContain('weatherJsonHeaders()');
    // لا يبقى أيّ طلب طقس بترويسة Accept فقط بلا مصادقة.
    expect(probe).not.toContain("{ 'Content-Type': 'application/json', Accept: 'application/json' }");
  });

  it('persists safe user weather overlay preferences (v27)', () => {
    expect(existsSync(join(weatherDir, 'weatherPreferences.ts'))).toBe(true);
    expect(overlay).toContain('readWeatherPreferences');
    expect(overlay).toContain('writeWeatherPreferences');
    expect(preferences).toContain('sahool.weather.overlay.preferences.v1');
    expect(preferences).toContain('localStorage');
    expect(preferences).toContain('typeof window'); // حارس SSR/الخصوصيّة
    expect(preferences).toContain('clampOpacity'); // تحقّق مدخلات آمن
    expect(preferences).toContain('resetWeatherPreferences');
  });

  it('supports a color-scheme (palette) toggle: rainbow ↔ cold/warm', () => {
    expect(defs).toContain('WEATHER_PALETTES');
    expect(defs).toContain('WeatherPalette');
    expect(panel).toContain('data-palette');
    expect(tile).toContain('palette');
  });
});
