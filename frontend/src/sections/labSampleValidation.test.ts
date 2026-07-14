import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';
import { validateSampleNumerics } from './LabSamplingPage';

// continuation-3 P0: حدود الإحداثيّات/الأعماق قبل الإرسال.
describe('validateSampleNumerics', () => {
  const ok = { lat: 15, lon: 44, dFrom: 0, dTo: 30, gps: 5 };

  it('يقبل عيّنة ضمن المدى', () => {
    expect(validateSampleNumerics(ok)).toBeNull();
  });

  it('يرفض خط عرض/طول خارج المدى وNaN', () => {
    expect(validateSampleNumerics({ ...ok, lat: 91 })).toMatch(/العرض/);
    expect(validateSampleNumerics({ ...ok, lat: -91 })).toMatch(/العرض/);
    expect(validateSampleNumerics({ ...ok, lon: 181 })).toMatch(/الطول/);
    expect(validateSampleNumerics({ ...ok, lat: NaN })).toMatch(/العرض/);
  });

  it('يرفض العمق السالب وعمق النهاية ≤ البداية', () => {
    expect(validateSampleNumerics({ ...ok, dFrom: -1 })).toMatch(/البداية/);
    expect(validateSampleNumerics({ ...ok, dFrom: 30, dTo: 20 })).toMatch(/أكبر من/);
    expect(validateSampleNumerics({ ...ok, dFrom: 30, dTo: 30 })).toMatch(/أكبر من/);
  });

  it('يرفض دقّة GPS السالبة', () => {
    expect(validateSampleNumerics({ ...ok, gps: -2 })).toMatch(/GPS/);
  });

  it('يسمح بالأعماق الغائبة (null)', () => {
    expect(validateSampleNumerics({ lat: 15, lon: 44, dFrom: null, dTo: null, gps: null })).toBeNull();
  });
});

// continuation-1 P0: حدّ حجم ملفّ الاستيراد قبل التحليل.
describe('AddFieldWithMap — import file-size guard', () => {
  it('يفرض حدّاً أقصى لحجم الملفّ قبل FileReader', () => {
    const src = readFileSync(join(process.cwd(), 'src/components/AddFieldWithMap.tsx'), 'utf8');
    expect(src).toContain('MAX_IMPORT_BYTES');
    expect(src).toContain('f.size > MAX_IMPORT_BYTES');
    // الفحص يسبق قراءة الملفّ (return مبكّر قبل shp/readAsText).
    expect(src.indexOf('MAX_IMPORT_BYTES')).toBeLessThan(src.indexOf('reader.readAsArrayBuffer'));
  });
});
