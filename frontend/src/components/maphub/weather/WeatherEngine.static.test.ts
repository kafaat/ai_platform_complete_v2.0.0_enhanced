import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const weather = readFileSync(join(root, 'src/components/maphub/weather/WeatherRasterOverlay.tsx'), 'utf8');
const overlay = readFileSync(join(root, 'src/components/maphub/OverlayMarkers.tsx'), 'utf8');

describe('SAHOOL weather map engine', () => {
  it('keeps Open-Meteo as data source and SAHOOL as renderer', () => {
    expect(weather).toContain('/api/v1/weather/tile-data/');
    expect(weather).toContain('/api/v1/weather/operation-tile-data/');
    expect(weather).toContain('/api/v1/weather/probe');
    expect(weather).toContain('/api/v1/weather/operation-plan');
    expect(weather).toContain('createWeatherWindGridLayer');
  });

  it('exposes agronomic presets and UI controls', () => {
    expect(weather).toContain('operation_spraying');
    expect(weather).toContain('operation_irrigation');
    expect(weather).toContain('data-opacity');
    expect(weather).toContain('data-wind-toggle');
    expect(weather).toContain('WEATHER_MODELS');
  });

  it('keeps OverlayMarkers focused on markers and delegates weather raster rendering', () => {
    expect(overlay).toContain("./weather/WeatherRasterOverlay");
    expect(overlay).toContain('export function WeatherOverlay');
    expect(overlay).toContain('export function OperationalOverlay');
  });
});
