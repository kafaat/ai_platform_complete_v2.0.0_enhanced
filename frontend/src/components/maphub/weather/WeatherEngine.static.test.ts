import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const weatherDir = join(process.cwd(), 'src/components/maphub/weather');
const overlay = readFileSync(join(weatherDir, 'WeatherRasterOverlay.tsx'), 'utf8');
const defs = readFileSync(join(weatherDir, 'weatherLayerDefinitions.ts'), 'utf8');
const tile = readFileSync(join(weatherDir, 'WeatherTileLayer.ts'), 'utf8');
const panel = readFileSync(join(weatherDir, 'WeatherLayerPanel.ts'), 'utf8');
const probe = readFileSync(join(weatherDir, 'WeatherProbePopup.ts'), 'utf8');

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
  });

  it('supports probe, operation window, and operation plan popups', () => {
    expect(probe).toContain('/api/v1/weather/probe');
    expect(probe).toContain('/api/v1/weather/operation-window');
    expect(probe).toContain('/api/v1/weather/operation-plan');
  });

  it('attaches auth headers to weather fetches (production auth_request gate)', () => {
    // حارس انحدار: نقاط /api/v1/weather/* خلف auth_request في الإنتاج، فطلبات
    // البلاطات والمسبار يجب أن تُرفِق Bearer عبر weatherFetchHeaders — وإلّا 401.
    expect(defs).toContain('weatherFetchHeaders');
    expect(defs).toContain('getAccessToken');
    expect(tile).toContain('weatherFetchHeaders()');
    expect(probe).toContain('weatherFetchHeaders()');
  });
});
