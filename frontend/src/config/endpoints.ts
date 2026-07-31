// SAHOOL — Runtime endpoint policy
// Centralizes URL resolution so production builds do not accidentally ship
// local loopback/emulator endpoints. Development may still use direct
// service ports by setting VITE_API_MODE=dev explicitly.

export type ApiMode = 'gateway' | 'dev';

export const API_MODE: ApiMode = import.meta.env.VITE_API_MODE === 'dev' ? 'dev' : 'gateway';
const isDevMode = API_MODE === 'dev';

const LOCAL_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '10.0.2.2'] as const;
const LOCAL_ENDPOINT_RE = new RegExp(`^(https?|wss?)://(${LOCAL_HOSTS.map((h) => h.replace(/\\./g, '\\\\.')).join('|')})(?::\\d+)?(?:/|$)`, 'i');
const localHttp = (port: number): string => `http://${LOCAL_HOSTS[0]}:${port}`;

function env(name: string): string | undefined {
  const value = import.meta.env[name] as string | undefined;
  return value === undefined || value === '' ? undefined : value;
}

export function assertSafeEndpoint(name: string, value: string): string {
  if (!isDevMode && LOCAL_ENDPOINT_RE.test(value)) {
    throw new Error(
      `${name} points to a local endpoint (${value}) while VITE_API_MODE=${API_MODE}. ` +
      'Use gateway-relative paths in production, or set VITE_API_MODE=dev for local direct ports.'
    );
  }
  return value;
}

export function resolveHttpBase(
  name: string,
  gatewayDefault: string,
  devDefault: string,
): string {
  const value = env(name) ?? (isDevMode ? devDefault : gatewayDefault);
  return assertSafeEndpoint(name, value);
}

export function resolveWsBase(): string {
  const raw = env('VITE_WS_BASE_URL') ?? '/ws';
  if (/^wss?:\/\//i.test(raw)) {
    return assertSafeEndpoint('VITE_WS_BASE_URL', raw).replace(/\/+$/, '');
  }
  const relative = raw.startsWith('/') ? raw : `/${raw}`;
  if (typeof window !== 'undefined') {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${window.location.host}${relative}`.replace(/\/+$/, '');
  }
  return relative.replace(/\/+$/, '');
}

export const ENDPOINTS = {
  kong: resolveHttpBase('VITE_API_BASE_URL', '', localHttp(8000)),
  // dev-direct default carries /v1: authApi calls bare /auth/* paths (e.g. '/auth/login');
  // in gateway mode nginx rewrites those to the service's /v1/auth/* routes
  // (API-VERSIONING-GUARD-IS-A-MIRROR-01), but dev-direct mode has no nginx in between, so
  // the base itself must supply the /v1 segment or every direct-port auth call 404s.
  auth: resolveHttpBase('VITE_AUTH_BASE_URL', '', `${localHttp(8120)}/v1`),
  raster: resolveHttpBase('VITE_RASTER_BASE_URL', '/api/raster', localHttp(8001)),
  vegetation: resolveHttpBase('VITE_VEGETATION_BASE_URL', '/api/vegetation', localHttp(8090)),
  indicators: resolveHttpBase('VITE_INDICATORS_BASE_URL', '/api/indicators', localHttp(8091)),
  weather: resolveHttpBase('VITE_WEATHER_BASE_URL', '/api/weather', localHttp(8092)),
  soil: resolveHttpBase('VITE_SOIL_BASE_URL', '/api/soil', localHttp(8094)),
  ws: resolveWsBase(),
} as const;
