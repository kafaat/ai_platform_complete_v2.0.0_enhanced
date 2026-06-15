// اختبارات سجلّ طبقات الخريطة — تتحقّق من سلوك المساعِدات الفعليّ على البيانات
// المُعلَنة في LAYER_REGISTRY (لا قيم مُختلَقة).
import { describe, it, expect } from 'vitest';
import {
  LAYER_REGISTRY,
  listLayers,
  getLayer,
  layersOfKind,
  defaultVisibleLayers,
} from './layerRegistry';

describe('layerRegistry', () => {
  it('listLayers تُرجِع نسخة بكلّ المدخلات لا مرجع السجلّ نفسه', () => {
    const a = listLayers();
    expect(a).toHaveLength(LAYER_REGISTRY.length);
    expect(a).not.toBe(LAYER_REGISTRY as unknown as typeof a);
    // تعديل النسخة لا يمسّ السجلّ المصدر
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
    expect(indices.map((l) => l.id).sort()).toEqual(['ndmi', 'ndvi', 'salinity']);
    expect(indices.every((l) => l.kind === 'index')).toBe(true);

    const basemaps = layersOfKind('basemap');
    expect(basemaps.map((l) => l.id).sort()).toEqual(['light', 'satellite']);

    expect(layersOfKind('boundary').map((l) => l.id)).toEqual(['field-boundary']);
    expect(layersOfKind('radar').map((l) => l.id)).toEqual(['radar']);
  });

  it('defaultVisibleLayers تطابق العلَم defaultVisible على المصدر', () => {
    const visibleIds = defaultVisibleLayers().map((l) => l.id).sort();
    // المُعلَن في السجلّ: satellite + field-boundary + ndvi فقط ظاهرة افتراضيّاً
    expect(visibleIds).toEqual(['field-boundary', 'ndvi', 'satellite']);
    expect(defaultVisibleLayers().every((l) => l.defaultVisible === true)).toBe(true);
  });

  it('طبقات المؤشّرات تحمل colormap من CMAP والرادار مُعلَن غير متوفّر', () => {
    expect(getLayer('ndvi')?.colormap).toBe('ndvi');
    expect(getLayer('ndmi')?.colormap).toBe('moisture');
    expect(getLayer('salinity')?.colormap).toBe('ec');
    // الرادار: نقطة تمديد بلا مصدر مُلفّق
    expect(getLayer('radar')?.source).toBe('unavailable');
    expect(getLayer('radar')?.defaultVisible).toBe(false);
  });
});
