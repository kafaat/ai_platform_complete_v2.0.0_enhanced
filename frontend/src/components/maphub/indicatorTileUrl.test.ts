import { describe, it, expect, vi } from 'vitest';

// نُثبّت تبعيّات الوحدة (rasterBaseUrl/getAccessToken) كي يكون الاختبار نقيّاً ومُحدَّداً.
vi.mock('../../services/api', () => ({ rasterBaseUrl: () => 'http://raster' }));
vi.mock('../../lib/authStorage', () => ({ getAccessToken: () => 'jwt-abc' }));

import { indicatorTileUrl } from './indicatorTileUrl';
import type { FieldOption } from '../../lib/fields';

const field = {
  id: 'f1',
  geometry: { type: 'Polygon', coordinates: [[[44, 15], [45, 15], [45, 16], [44, 16], [44, 15]]] },
} as unknown as FieldOption;

// import.meta.env.PROD = false في vitest ⇒ فرع التطوير (يُبقي tenant_id + access_token).
describe('indicatorTileUrl (extracted shared module)', () => {
  it('يبني رابط cdse-tiles الحيّ مع القصّ (poly/bbox) افتراضيّاً', () => {
    const url = indicatorTileUrl(field, 'ndvi', 't1', 0, 'latest');
    expect(url).toContain('http://raster/v1/fields/f1/cdse-tiles/{z}/{x}/{y}.png?');
    expect(url).toContain('index=ndvi');
    expect(url).toContain('poly=');
    expect(url).toContain('bbox_w=44');
    // 'latest' لا يُمرَّر كـdate.
    expect(url).not.toContain('date=latest');
  });

  it('preferPersistedCog=true ⇒ مسار /tiles المحفوظ بلا قصّ', () => {
    const url = indicatorTileUrl(field, 'ndvi', 't1', 0, '2026-07-01', true);
    expect(url).toContain('/v1/fields/f1/tiles/{z}/{x}/{y}.png?');
    expect(url).toContain('date=2026-07-01');
    expect(url).not.toContain('poly=');
  });

  it('في التطوير يُمرَّر tenant_id + access_token (fallback مباشر بلا بوّابة)', () => {
    const url = indicatorTileUrl(field, 'ndvi', 't1');
    expect(url).toContain('tenant_id=t1');
    expect(url).toContain('access_token=jwt-abc');
  });

  it('يُمرَّر v (طابع الوقت) عند توفّره', () => {
    expect(indicatorTileUrl(field, 'ndvi', 't1', 1234)).toContain('v=1234');
  });
});
