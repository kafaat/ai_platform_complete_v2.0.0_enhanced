// اختبارات حارس النوع isCanonicalFieldGeometry — يضمن مطابقة العقد الكنسيّ
// (geometry Polygon + area_ha + bbox{min_lng..} + revision + source) 1:1.
import { describe, it, expect } from 'vitest';
import { isCanonicalFieldGeometry, type CanonicalFieldGeometry } from './canonicalGeometry';

const valid: CanonicalFieldGeometry = {
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [44.0, 15.0],
        [44.2, 15.0],
        [44.2, 15.2],
        [44.0, 15.2],
        [44.0, 15.0],
      ],
    ],
  },
  area_ha: 12.3456,
  bbox: { min_lng: 44.0, min_lat: 15.0, max_lng: 44.2, max_lat: 15.2 },
  revision: 3,
  source: 'gis-guard-v1',
};

describe('isCanonicalFieldGeometry', () => {
  it('يقبل شكلاً كنسيّاً صحيحاً', () => {
    expect(isCanonicalFieldGeometry(valid)).toBe(true);
  });

  it('يقبل revision = null', () => {
    expect(isCanonicalFieldGeometry({ ...valid, revision: null })).toBe(true);
  });

  it('يرفض نوع هندسة غير Polygon', () => {
    const bad = { ...valid, geometry: { type: 'Point', coordinates: [44, 15] } };
    expect(isCanonicalFieldGeometry(bad)).toBe(false);
  });

  it('يرفض bbox بمفاتيح lon بدل lng', () => {
    const bad = {
      ...valid,
      bbox: { min_lon: 44.0, min_lat: 15.0, max_lon: 44.2, max_lat: 15.2 },
    };
    expect(isCanonicalFieldGeometry(bad)).toBe(false);
  });

  it('يرفض area_ha غير الرقميّة', () => {
    expect(isCanonicalFieldGeometry({ ...valid, area_ha: '12' })).toBe(false);
  });

  it('يرفض source غير النصّيّ', () => {
    expect(isCanonicalFieldGeometry({ ...valid, source: 7 })).toBe(false);
  });

  it('يرفض القيم غير الكائنيّة', () => {
    expect(isCanonicalFieldGeometry(null)).toBe(false);
    expect(isCanonicalFieldGeometry(undefined)).toBe(false);
    expect(isCanonicalFieldGeometry('x')).toBe(false);
  });
});
