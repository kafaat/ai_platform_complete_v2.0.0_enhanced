import { describe, it, expect, beforeEach } from 'vitest';
import { saveFieldMapView, readFieldMapView, markDefaultViewOnce, consumeDefaultViewOnce } from './fieldMapView';

describe('fieldMapView — per-field saved zoom + center (localStorage)', () => {
  beforeEach(() => { window.localStorage.clear(); });

  it('round-trips a saved view by field id', () => {
    saveFieldMapView('fld_1', { zoom: 16, lat: 24.5, lng: 46.7 });
    expect(readFieldMapView('fld_1')).toEqual({ zoom: 16, lat: 24.5, lng: 46.7 });
  });

  it('returns null for an unknown field', () => {
    expect(readFieldMapView('nope')).toBeNull();
  });

  it('ignores missing field id', () => {
    saveFieldMapView('', { zoom: 16, lat: 24.5, lng: 46.7 });
    saveFieldMapView(null, { zoom: 16, lat: 24.5, lng: 46.7 });
    expect(readFieldMapView(null)).toBeNull();
  });

  it('rejects non-finite or out-of-range coordinates (no corrupt write)', () => {
    saveFieldMapView('fld_2', { zoom: NaN, lat: 24, lng: 46 });
    saveFieldMapView('fld_3', { zoom: 16, lat: 200, lng: 46 });
    saveFieldMapView('fld_4', { zoom: 16, lat: 24, lng: 999 });
    expect(readFieldMapView('fld_2')).toBeNull();
    expect(readFieldMapView('fld_3')).toBeNull();
    expect(readFieldMapView('fld_4')).toBeNull();
  });

  it('keeps separate views per field', () => {
    saveFieldMapView('a', { zoom: 12, lat: 1, lng: 2 });
    saveFieldMapView('b', { zoom: 18, lat: 3, lng: 4 });
    expect(readFieldMapView('a')?.zoom).toBe(12);
    expect(readFieldMapView('b')?.zoom).toBe(18);
  });

  it('default-view-once flag fires exactly once for the marked field', () => {
    markDefaultViewOnce('new_field');
    // أوّل استهلاك للحقل المُعلَّم ⇒ true ثمّ يُمسَح؛ الثاني ⇒ false (الفتح اللاحق يطير للمحفوظ).
    expect(consumeDefaultViewOnce('new_field')).toBe(true);
    expect(consumeDefaultViewOnce('new_field')).toBe(false);
  });

  it('default-view-once does not affect other fields', () => {
    markDefaultViewOnce('new_field');
    expect(consumeDefaultViewOnce('other')).toBe(false);
    // يبقى العلم قائماً للحقل الصحيح فقط.
    expect(consumeDefaultViewOnce('new_field')).toBe(true);
  });
});
