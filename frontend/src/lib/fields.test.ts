// اختبارات تطبيع خيار الحقل — أولويّة المفاتيح، تحويل id لنصّ، احتياط الاسم/المساحة.
import { describe, it, expect } from 'vitest';
import { toFieldOption } from './fields';

describe('toFieldOption', () => {
  it('يفضّل field_id ويحوّل id إلى نصّ', () => {
    expect(toFieldOption({ field_id: 42 }).id).toBe('42');
    expect(toFieldOption({ id: 7 }).id).toBe('7'); // احتياط على id
    // field_id يفوز على id حين توفّرهما
    expect(toFieldOption({ field_id: 1, id: 2 }).id).toBe('1');
  });

  it('أولويّة الاسم: name_ar ← name ← field_code ← field_id ← الافتراضيّ', () => {
    expect(toFieldOption({ name_ar: 'الحقل أ', name: 'A' }).name).toBe('الحقل أ');
    expect(toFieldOption({ name: 'A', field_code: 'F1' }).name).toBe('A');
    expect(toFieldOption({ field_code: 'F1' }).name).toBe('F1');
    expect(toFieldOption({ field_id: 9 }).name).toBe('9');
    expect(toFieldOption({ field_id: 1, id: 1 }).name).toBe('1');
  });

  it('يستخدم احتياط الإحداثيّات (centroid) وnull عند الغياب', () => {
    expect(toFieldOption({ field_id: 1, lat: 15, lon: 44 })).toMatchObject({ lat: 15, lon: 44 });
    expect(toFieldOption({ field_id: 1, centroid_lat: 16, centroid_lon: 45 })).toMatchObject({
      lat: 16,
      lon: 45,
    });
    const noCoords = toFieldOption({ field_id: 1 });
    expect(noCoords.lat).toBeNull();
    expect(noCoords.lon).toBeNull();
  });

  it('المساحة تُحوَّل لرقم (area_ha ← area ← 0) والمحصول نصّ افتراضيّه «—»', () => {
    expect(toFieldOption({ field_id: 1, area_ha: 2.5 }).area).toBe(2.5);
    expect(toFieldOption({ field_id: 1, area: '3' }).area).toBe(3);
    expect(toFieldOption({ field_id: 1 }).area).toBe(0);
    expect(toFieldOption({ field_id: 1, crop: 'قمح' }).crop).toBe('قمح');
    expect(toFieldOption({ field_id: 1 }).crop).toBe('—');
  });

  it('يمرّر الهندسة كما هي', () => {
    const geometry = { type: 'Polygon', coordinates: [] };
    expect(toFieldOption({ field_id: 1, geometry }).geometry).toBe(geometry);
  });
});
