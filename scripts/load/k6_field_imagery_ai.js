import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

export const errorRate = new Rate('sahool_runtime_errors');
export const tileLatency = new Trend('sahool_tile_latency_ms');
export const aiLatency = new Trend('sahool_ai_latency_ms');

const BASE_URL = __ENV.BASE_URL || 'http://localhost';
const JWT = __ENV.SAHOOL_JWT || '';
const TENANT_ID = __ENV.TENANT_ID || '00000000-0000-0000-0000-000000000001';
const FIELD_ID = __ENV.FIELD_ID || '00000000-0000-0000-0000-000000000101';
const IMAGERY_DATE = __ENV.IMAGERY_DATE || 'latest';
const INDEX = __ENV.INDEX || 'ndvi';

export const options = {
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<3000'],
    sahool_runtime_errors: ['rate<0.05'],
    sahool_tile_latency_ms: ['p(95)<2500'],
    sahool_ai_latency_ms: ['p(95)<5000'],
  },
  scenarios: {
    field_imagery_ai_smoke: {
      executor: 'ramping-vus',
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m', target: 15 },
        { duration: '30s', target: 0 },
      ],
    },
  },
};

function headers(extra = {}) {
  const base = {
    'Content-Type': 'application/json',
    'X-Tenant-ID': TENANT_ID,
    ...extra,
  };
  if (JWT) base.Authorization = `Bearer ${JWT}`;
  return base;
}

function assertOk(name, response, accepted = [200]) {
  const ok = check(response, {
    [`${name} status accepted`]: (r) => accepted.includes(r.status),
    [`${name} not gateway failure`]: (r) => ![502, 503, 504].includes(r.status),
  });
  errorRate.add(!ok);
  return ok;
}

export default function () {
  const availableDates = http.get(
    `${BASE_URL}/api/raster/v1/fields/${FIELD_ID}/available-dates`,
    { headers: headers() }
  );
  assertOk('available-dates', availableDates, [200, 204, 404]);

  const tileJsonStart = Date.now();
  const tileJson = http.get(
    `${BASE_URL}/api/raster/v1/fields/${FIELD_ID}/tilejson?index=${INDEX}&date=${encodeURIComponent(IMAGERY_DATE)}&v=loadtest`,
    { headers: headers() }
  );
  tileLatency.add(Date.now() - tileJsonStart);
  assertOk('tilejson', tileJson, [200, 202, 404]);

  const aiPayload = JSON.stringify({
    field_id: FIELD_ID,
    question: 'Give a cautious evidence-based crop condition summary for this field.',
    language: 'ar',
    require_field_context: true,
  });
  const aiStart = Date.now();
  const ai = http.post(`${BASE_URL}/api/ai-agronomist/chat`, aiPayload, { headers: headers() });
  aiLatency.add(Date.now() - aiStart);
  assertOk('ai-agronomist', ai, [200, 409, 422, 503]);
  check(ai, {
    'ai does not silently succeed without context': (r) => r.status !== 200 || /evidence|field|confidence|guardrail|context|دليل|حقل/.test(r.body || ''),
  });

  sleep(1);
}
