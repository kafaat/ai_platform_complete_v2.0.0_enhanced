import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const satellite = readFileSync(resolve(__dirname, 'SatellitePage.tsx'), 'utf8');
const hooks = readFileSync(resolve(__dirname, '../hooks/useApi.ts'), 'utf8');
const api = readFileSync(resolve(__dirname, '../services/api.ts'), 'utf8');
const platformFields = readFileSync(resolve(__dirname, '../../../services/sahool-platform/api/routers/fields.py'), 'utf8');

describe('Satellite analyze field ownership bridge', () => {
  it('يمرّر هندسة الحقل المختار مع تحليل الآن حتى لا يفشل field_id عند platform DB mismatch', () => {
    expect(satellite).toContain('await analyze({ fieldId, geometry: field?.geometry })');
    expect(hooks).toContain('geometry?: unknown');
    expect(hooks).toContain('refreshFieldImagery(fieldId, dateFrom ?? null, geometry)');
    expect(api).toContain('if (geometry) body.geometry = geometry');
  });

  it('منصة imagery/refresh تستخدم geometry الصريحة فقط كجسر صادق عند غياب صف fields', () => {
    expect(platformFields).toContain('geometry: dict | None = None');
    expect(platformFields).toContain('if not (req and req.geometry)');
    expect(platformFields).toContain('geometry = req.geometry');
    expect(platformFields).toContain('guard_field_geometry(geometry)');
  });
});
