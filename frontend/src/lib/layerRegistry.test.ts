// اختبارات سجلّ طبقات الخريطة — تتحقّق من سلوك المساعِدات الفعليّ على البيانات
// المُعلَنة في LAYER_REGISTRY، بما في ذلك خرائط الأساس الاختيارية ذات الـtokens.
import { describe, it, expect } from 'vitest';
import {
  LAYER_REGISTRY,
  listLayers,
  getLayer,
  layersOfKind,
  defaultVisibleLayers,
  resolveLayerSource,
  availableBasemapLayers,
} from './layerRegistry';

describe('layerRegistry', () => {
  it('listLayers تُرجِع نسخة بكلّ المدخلات لا مرجع السجلّ نفسه', () => {
    const a = listLayers();
    expect(a).toHaveLength(LAYER_REGISTRY.length);
    expect(a).not.toBe(LAYER_REGISTRY as unknown as typeof a);
    a.pop();
    expect(listLayers()).toHaveLength(LAYER_REGISTRY.length);
  });

  it('getLayer تُرجِع الطبقة بمعرّفها وundefined لمعرّف مجهول', () => {
    expect(getLayer('ndvi')?.labelAr).toBe('مؤشّر الغطاء النباتيّ (NDVI)');
    expect(getLayer('ndvi')?.kind).toBe('index');
    expect(getLayer('not-a-layer')).toBeUndefined();
  });

  it('layersOfKind ترشّح حسب النوع فقط', () => {
    const indices = layersOfKind('index');
    expect(indices.map((l) => l.id)).toEqual(expect.arrayContaining([
      'truecolor', 'ndvi', 'ndmi', 'salinity', 'evi', 'savi', 'msavi', 'ndwi', 'gndvi', 'ndre', 'msi',
      'reci', 'gci', 'arvi', 'sipi', 'nbr', 'ccci', 'vari', 'gli', 'bsi',
    ]));
    expect(indices.every((l) => l.kind === 'index')).toBe(true);

    const basemaps = layersOfKind('basemap');
    expect(basemaps.map((l) => l.id)).toEqual(expect.arrayContaining([
      'satellite', 'light', 'mapbox-satellite', 'google-satellite-official',
    ]));

    expect(layersOfKind('boundary').map((l) => l.id)).toEqual(['field-boundary']);
    expect(layersOfKind('radar').map((l) => l.id)).toEqual(['radar']);
  });

  it('defaultVisibleLayers تطابق العلَم defaultVisible على المصدر', () => {
    const visibleIds = defaultVisibleLayers().map((l) => l.id).sort();
    expect(visibleIds).toEqual(['field-boundary', 'satellite', 'truecolor']);
    expect(defaultVisibleLayers().every((l) => l.defaultVisible === true)).toBe(true);
  });

  it('طبقات المؤشّرات تحمل colormap من CMAP والرادار مُعلَن غير متوفّر', () => {
    expect(getLayer('ndvi')?.colormap).toBe('ndvi');
    expect(getLayer('ndmi')?.colormap).toBe('moisture');
    expect(getLayer('salinity')?.colormap).toBe('ec');
    expect(getLayer('radar')?.source).toBe('unavailable');
    expect(getLayer('radar')?.defaultVisible).toBe(false);
  });

  it('Mapbox لا يظهر دون token ويظهر عند VITE_MAPBOX_TOKEN، وGoogle يبقى غير مفعّل', () => {
    const mapbox = getLayer('mapbox-satellite');
    expect(resolveLayerSource(mapbox)).toBeUndefined();
    expect(resolveLayerSource(mapbox, { VITE_MAPBOX_TOKEN: 'tok 1' })).toContain('access_token=tok%201');

    const withoutToken = availableBasemapLayers().map((l) => l.id);
    expect(withoutToken).toContain('satellite');
    expect(withoutToken).toContain('light');
    expect(withoutToken).not.toContain('mapbox-satellite');
    expect(withoutToken).not.toContain('google-satellite-official');

    const withToken = availableBasemapLayers({ VITE_MAPBOX_TOKEN: 'tok' }).map((l) => l.id);
    expect(withToken).toContain('mapbox-satellite');
    expect(withToken).not.toContain('google-satellite-official');
  });
});
