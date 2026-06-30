import {
  DEFAULT_LAYER,
  WEATHER_LAYERS,
  WEATHER_MODELS,
  WEATHER_TIMES,
  WIND_DENSITIES,
  WEATHER_PALETTES,
  type WeatherLayerKey,
  type WeatherTimeKey,
  type WindDensity,
  type WeatherPalette,
} from './weatherLayerDefinitions';

export type WeatherOverlayPreferences = {
  layer: WeatherLayerKey;
  time: WeatherTimeKey;
  model: string;
  opacity: number;
  showWind: boolean;
  windDensity: WindDensity;
  panelOpen: boolean;
  palette: WeatherPalette;
  graticule: boolean;
};

const STORAGE_KEY = 'sahool.weather.overlay.preferences.v1';
const DEFAULT_MODEL = 'best_match';

function hasWindow(): boolean {
  return typeof window !== 'undefined';
}

function safeMatchMedia(query: string): boolean {
  if (!hasWindow()) return false;
  return Boolean(window.matchMedia?.(query).matches);
}

function safeViewportWidth(): number {
  if (!hasWindow()) return 1024;
  return Number.isFinite(window.innerWidth) ? window.innerWidth : 1024;
}

function isWeatherLayer(value: unknown): value is WeatherLayerKey {
  return typeof value === 'string' && WEATHER_LAYERS.some((entry) => entry.key === value);
}

function isWeatherTime(value: unknown): value is WeatherTimeKey {
  return typeof value === 'string' && WEATHER_TIMES.some((entry) => entry.key === value);
}

function isWeatherModel(value: unknown): value is string {
  return typeof value === 'string' && WEATHER_MODELS.some((entry) => entry.key === value);
}

function isWindDensity(value: unknown): value is WindDensity {
  return typeof value === 'string' && WIND_DENSITIES.some((entry) => entry.key === value);
}

function isWeatherPalette(value: unknown): value is WeatherPalette {
  return typeof value === 'string' && WEATHER_PALETTES.some((entry) => entry.key === value);
}

function clampOpacity(value: unknown, fallback: number): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(0.25, Math.min(1, numeric));
}

function coerceBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

export function defaultWeatherPreferences(): WeatherOverlayPreferences {
  const isSmallScreen = safeViewportWidth() < 760;
  const isWidePanel = safeViewportWidth() >= 880;
  const reducedMotion = safeMatchMedia('(prefers-reduced-motion: reduce)');
  return {
    layer: DEFAULT_LAYER,
    time: 'now',
    model: DEFAULT_MODEL,
    opacity: 0.86,
    showWind: !reducedMotion,
    windDensity: isSmallScreen ? 'medium' : 'high',
    panelOpen: isWidePanel,
    palette: 'coldwarm',
    graticule: false,
  };
}

export function readWeatherPreferences(): WeatherOverlayPreferences {
  const defaults = defaultWeatherPreferences();
  if (!hasWindow()) return defaults;
  try {
    const raw = window.localStorage?.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<WeatherOverlayPreferences>;
    return {
      layer: isWeatherLayer(parsed.layer) ? parsed.layer : defaults.layer,
      time: isWeatherTime(parsed.time) ? parsed.time : defaults.time,
      model: isWeatherModel(parsed.model) ? parsed.model : defaults.model,
      opacity: clampOpacity(parsed.opacity, defaults.opacity),
      showWind: coerceBoolean(parsed.showWind, defaults.showWind),
      windDensity: isWindDensity(parsed.windDensity) ? parsed.windDensity : defaults.windDensity,
      panelOpen: coerceBoolean(parsed.panelOpen, defaults.panelOpen),
      palette: isWeatherPalette(parsed.palette) ? parsed.palette : defaults.palette,
      graticule: coerceBoolean(parsed.graticule, defaults.graticule),
    };
  } catch {
    return defaults;
  }
}

export function writeWeatherPreferences(preferences: WeatherOverlayPreferences): void {
  if (!hasWindow()) return;
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // Browsers can reject writes in private mode or strict storage settings.
  }
}

export function resetWeatherPreferences(): WeatherOverlayPreferences {
  const defaults = defaultWeatherPreferences();
  if (hasWindow()) {
    try {
      window.localStorage?.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage errors; callers still receive safe defaults.
    }
  }
  return defaults;
}

export const WEATHER_PREFERENCES_STORAGE_KEY = STORAGE_KEY;
