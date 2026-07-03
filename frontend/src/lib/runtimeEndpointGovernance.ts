export type RuntimeEndpointKind = 'api' | 'ws' | 'raster' | 'tiles' | 'dev-proxy';
export type RuntimeEndpointSeverity = 'ok' | 'info' | 'warn' | 'critical';

export interface RuntimeEndpointInput {
  apiUrl?: string | null;
  wsUrl?: string | null;
  rasterUrl?: string | null;
  tileUrl?: string | null;
  devProxyTarget?: string | null;
  apiMode?: string | null;
  mockMode?: string | null;
}

export interface RuntimeEndpointCheck {
  id: RuntimeEndpointKind;
  label: string;
  severity: RuntimeEndpointSeverity;
  evidence: string;
  action?: string;
}

export interface RuntimeEndpointGovernanceResult {
  score: number;
  severity: RuntimeEndpointSeverity;
  summary: string;
  checks: RuntimeEndpointCheck[];
  portHints: string[];
}

function clean(value?: string | null): string {
  return String(value ?? '').trim();
}

function isLocalhost(url: string): boolean {
  return /(^|\/\/)(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|\/|$)/i.test(url);
}

function protocol(url: string): string | null {
  const match = url.match(/^([a-z]+):\/\//i);
  return match?.[1]?.toLowerCase() ?? null;
}

function hostPort(url: string): string | null {
  try {
    const parsed = new URL(url, 'http://placeholder.local');
    if (!parsed.hostname || parsed.hostname === 'placeholder.local') return null;
    return `${parsed.hostname}:${parsed.port || (parsed.protocol === 'https:' ? '443' : parsed.protocol === 'http:' ? '80' : '')}`;
  } catch {
    return null;
  }
}

function scoreFor(severity: RuntimeEndpointSeverity): number {
  if (severity === 'critical') return 0;
  if (severity === 'warn') return 55;
  if (severity === 'info') return 82;
  return 100;
}

function overall(score: number): RuntimeEndpointSeverity {
  if (score < 45) return 'critical';
  if (score < 70) return 'warn';
  if (score < 90) return 'info';
  return 'ok';
}

export function evaluateRuntimeEndpointGovernance(input: RuntimeEndpointInput): RuntimeEndpointGovernanceResult {
  const apiUrl = clean(input.apiUrl);
  const wsUrl = clean(input.wsUrl);
  const rasterUrl = clean(input.rasterUrl);
  const tileUrl = clean(input.tileUrl);
  const devProxyTarget = clean(input.devProxyTarget);
  const apiMode = clean(input.apiMode || '');
  const mockMode = clean(input.mockMode || '');

  const checks: RuntimeEndpointCheck[] = [];
  checks.push({
    id: 'api', label: 'واجهة API',
    severity: apiUrl ? 'ok' : apiMode === 'mock' ? 'info' : 'warn',
    evidence: apiUrl || `apiMode=${apiMode || 'default'}`,
    action: apiUrl ? undefined : 'عرّف VITE_API_URL أو تأكد من proxy /api',
  });
  checks.push({
    id: 'ws', label: 'WebSocket',
    severity: wsUrl && protocol(wsUrl)?.startsWith('ws') ? 'ok' : wsUrl ? 'warn' : 'info',
    evidence: wsUrl || 'ws=not-configured',
    action: wsUrl && !protocol(wsUrl)?.startsWith('ws') ? 'استخدم ws:// أو wss://' : undefined,
  });
  checks.push({
    id: 'raster', label: 'Raster/Imagery',
    severity: rasterUrl || tileUrl ? 'ok' : 'warn',
    evidence: rasterUrl || tileUrl || 'raster=proxy-only',
    action: rasterUrl || tileUrl ? undefined : 'وثّق مسار /api/raster أو VITE_RASTER_URL',
  });
  checks.push({
    id: 'dev-proxy', label: 'Dev Proxy',
    severity: devProxyTarget ? 'ok' : apiMode === 'mock' ? 'info' : 'warn',
    evidence: devProxyTarget || 'devProxyTarget=empty',
    action: devProxyTarget ? undefined : 'عرّف VITE_DEV_PROXY_TARGET في بيئة التطوير',
  });

  const localUrls = [apiUrl, wsUrl, rasterUrl, tileUrl, devProxyTarget].filter(Boolean).filter(isLocalhost);
  if (localUrls.length >= 3) {
    checks.push({
      id: 'tiles', label: 'ازدحام منافذ محلية', severity: 'info',
      evidence: `localhost endpoints=${localUrls.length}`,
      action: 'استخدم Runtime Doctor قبل تشغيل compose لمنع تضارب 3000/5173/8000/8001',
    });
  }

  const score = Math.round(checks.reduce((sum, c) => sum + scoreFor(c.severity), 0) / checks.length);
  const severity = overall(score);
  const ports = Array.from(new Set([apiUrl, wsUrl, rasterUrl, tileUrl, devProxyTarget].map(hostPort).filter((v): v is string => !!v)));
  const portHints = ports.length ? ports.map((port) => `افحص ${port}`) : ['لا توجد منافذ صريحة في إعدادات Vite الحالية'];
  const weak = checks.filter((c) => c.severity === 'critical' || c.severity === 'warn');
  const summary = weak.length
    ? `Runtime endpoints تحتاج ضبط: ${weak.map((c) => c.label).join('، ')}`
    : `Runtime endpoints متناسقة بدرجة ${score}%`;
  return { score, severity, summary, checks, portHints };
}

export function readRuntimeEndpointEnv(env: ImportMetaEnv): RuntimeEndpointInput {
  return {
    apiUrl: env.VITE_API_URL,
    wsUrl: env.VITE_WS_URL,
    rasterUrl: env.VITE_RASTER_URL,
    tileUrl: env.VITE_TILE_URL,
    devProxyTarget: env.VITE_DEV_PROXY_TARGET,
    apiMode: env.VITE_API_MODE,
    mockMode: env.VITE_MOCK_MODE,
  };
}
