import { describe, expect, it } from 'vitest';
import {
  cachePlanSummary,
  collectionRows,
  conformanceBadge,
  dash,
  itemsQualitySummary,
  ogcItemTypeLabel,
  temporalExtentLabel,
  type StacCollectionsResponse,
  type StacItem,
  type TileCachePlan,
} from './gisCatalog';

describe('dash — الغائب «—» لا صفراً', () => {
  it('renders null/undefined/empty as dash, values as-is', () => {
    expect(dash(null)).toBe('—');
    expect(dash(undefined)).toBe('—');
    expect(dash('')).toBe('—');
    expect(dash(0)).toBe('0'); // الصفر الحقيقيّ من الخادم يُعرَض، لا يُخفى
    expect(dash('ndvi')).toBe('ndvi');
  });
});

describe('conformanceBadge — short badge, unknown passes through', () => {
  it('shortens STAC conformance URIs with version', () => {
    expect(conformanceBadge('https://api.stacspec.org/v1.0.0/item-search')).toBe(
      'STAC item-search v1.0.0',
    );
  });
  it('shortens OGC conformance URIs to api/part', () => {
    expect(
      conformanceBadge('http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core'),
    ).toBe('ogcapi-features-1/core');
  });
  it('passes unknown URIs through unchanged (server value as-is)', () => {
    expect(conformanceBadge('urn:custom:profile')).toBe('urn:custom:profile');
  });
});

describe('temporalExtentLabel — null bounds are honest dashes', () => {
  it('formats a real interval and dashes the null-only one', () => {
    expect(temporalExtentLabel([['2025-01-04', '2025-06-30']])).toBe('2025-01-04 → 2025-06-30');
    expect(temporalExtentLabel([[null, null]])).toBe('—'); // شكل الخادم عند غياب التواريخ
    expect(temporalExtentLabel(undefined)).toBe('—');
  });
});

describe('collectionRows — passthrough of server description, license dropped when absent', () => {
  const resp: StacCollectionsResponse = {
    collections: [
      {
        type: 'Collection', stac_version: '1.0.0', id: 'sahool-ndvi',
        title: 'SAHOOL NDVI products',
        description: 'Tenant-scoped ndvi field raster products.',
        license: 'proprietary',
        extent: { spatial: { bbox: [[44.1, 15.2, 44.4, 15.5]] }, temporal: { interval: [['2025-03-01', '2025-05-01']] } },
        links: [],
      },
    ],
    links: [],
  };
  it('maps id/title/description/temporal without inventing fields', () => {
    expect(collectionRows(resp)).toEqual([{
      id: 'sahool-ndvi',
      title: 'SAHOOL NDVI products',
      description: 'Tenant-scoped ndvi field raster products.',
      temporal: '2025-03-01 → 2025-05-01',
      license: 'proprietary',
    }]);
  });
  it('is empty for missing response', () => {
    expect(collectionRows(null)).toEqual([]);
  });
});

describe('itemsQualitySummary — missing values dropped, not zeroed', () => {
  const item = (over: Partial<StacItem['properties']>): StacItem => ({
    type: 'Feature', stac_version: '1.0.0', id: 'S2A_X', collection: 'sahool-ndvi',
    bbox: null, geometry: null, assets: {}, links: [],
    properties: {
      datetime: '2025-05-01', 'sahool:tenant_id': 't1', 'sahool:field_id': 'f1',
      'sahool:raster_id': 'r1', 'sahool:index_type': 'ndvi',
      'eo:cloud_cover': 10, 'sahool:quality_score': 80, gsd: 10,
      ...over,
    },
  });
  it('averages cloud only over numeric values and collects index types', () => {
    const items = [
      item({}),
      item({ 'eo:cloud_cover': 25, 'sahool:quality_score': 60, 'sahool:index_type': 'ndmi' }),
      item({ 'eo:cloud_cover': undefined as unknown as number, 'sahool:quality_score': null }),
    ];
    expect(itemsQualitySummary(items)).toEqual({
      count: 3,
      avgCloudPct: 17.5, // (10+25)/2 — العنصر بلا غيوم أُسقِط من الحساب
      minQuality: 60,
      maxQuality: 80,
      indexTypes: ['ndmi', 'ndvi'],
    });
  });
  it('reports null (not 0) when no numeric values exist', () => {
    const s = itemsQualitySummary([]);
    expect(s.count).toBe(0);
    expect(s.avgCloudPct).toBeNull();
    expect(s.minQuality).toBeNull();
  });
});

describe('cachePlanSummary — server ttl threshold (86400s) as-is', () => {
  const plan: TileCachePlan = {
    strategy: 'cdn+nginx+redis',
    entries: [
      { raster_id: 'a', index_type: 'ndvi', cache_key: 'k1', minzoom: 8, maxzoom: 14, ttl_seconds: 86400 },
      { raster_id: 'b', index_type: 'ndmi', cache_key: 'k2', minzoom: 8, maxzoom: 14, ttl_seconds: 21600 },
      { raster_id: 'c', index_type: 'ndvi', cache_key: 'k3', minzoom: 8, maxzoom: 14, ttl_seconds: 21600 },
    ],
    purge_on: ['raster_registry_update', 'geometry_revision_rollback'],
  };
  it('splits entries by ttl bucket and preserves strategy/purge_on', () => {
    expect(cachePlanSummary(plan)).toEqual({
      strategy: 'cdn+nginx+redis',
      totalEntries: 3,
      longTtl: 1,
      shortTtl: 2,
      purgeOn: ['raster_registry_update', 'geometry_revision_rollback'],
    });
  });
  it('is null (unknown) for missing plan — not an invented empty plan', () => {
    expect(cachePlanSummary(undefined)).toBeNull();
  });
});

describe('ogcItemTypeLabel — Arabic labels, unknown passthrough', () => {
  it('labels feature/coverage and passes unknown through', () => {
    expect(ogcItemTypeLabel('feature')).toBe('معالم (feature)');
    expect(ogcItemTypeLabel('coverage')).toBe('تغطية (coverage)');
    expect(ogcItemTypeLabel('tile-matrix')).toBe('tile-matrix');
  });
});
