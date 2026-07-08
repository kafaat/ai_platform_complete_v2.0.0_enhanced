// تحقّق V79-UI — اشتقاق مناطق حسّاسة للحقول المجاورة (منطق نقيّ، بلا React).

import { describe, it, expect } from 'vitest';
import { centroidOf, haversineKm, neighborZones, type FieldLike } from './driftZones';

describe('driftZones helpers', () => {
  it('centroidOf prefers lat/lon then falls back to geometry ring average', () => {
    expect(centroidOf({ id: 'a', lat: 15, lon: 45 })).toEqual({ lat: 15, lon: 45 });
    const poly: FieldLike = {
      id: 'b',
      geometry: { type: 'Polygon', coordinates: [[[44, 15], [46, 15], [46, 17], [44, 17], [44, 15]]] },
    };
    const c = centroidOf(poly);
    expect(c && Math.round(c.lon)).toBe(45);
    expect(c && Math.round(c.lat)).toBe(16);
    expect(centroidOf({ id: 'x' })).toBeNull();
    expect(centroidOf(null)).toBeNull();
  });

  it('haversineKm ~111km per degree of latitude', () => {
    expect(haversineKm(15, 45, 16, 45)).toBeGreaterThan(110);
    expect(haversineKm(15, 45, 16, 45)).toBeLessThan(113);
  });

  it('neighborZones includes only other fields within radius, honestly skips no-centroid', () => {
    const fields: FieldLike[] = [
      { id: 'self', lat: 15.0, lon: 45.0 },
      { id: 'near', lat: 15.005, lon: 45.0 }, // ~0.55km
      { id: 'far', lat: 16.0, lon: 45.0 }, // ~111km
      { id: 'nogeo' }, // بلا مركز ⇒ يُتخطّى
    ];
    const zones = neighborZones(fields, 'self', 2);
    expect(zones.map((z) => z.id)).toEqual(['near']);
    expect(zones[0].type).toBe('neighboring_field');
    // بلا حقل حاليّ صالح ⇒ فارغ.
    expect(neighborZones(fields, 'missing', 2)).toEqual([]);
    expect(neighborZones(undefined, 'self', 2)).toEqual([]);
  });
});
