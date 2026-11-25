import { describe, expect, it } from 'vitest';
import { parseUniformitySurvey } from './irrigationUniformity';

const rows = 'a,4,125000\nb,8,125000\nc,12,125000\nd,16,125000';

describe('irrigation uniformity survey input', () => {
  it('omits an absent survey', () => expect(parseUniformitySurvey('', '')).toBeUndefined());
  it('preserves evidence and measured sample areas for a synthetic 50 ha pivot', () => {
    expect(parseUniformitySurvey(' synthetic:pivot-a ', rows)).toEqual({
      evidence_ref: 'synthetic:pivot-a',
      samples: [4, 8, 12, 16].map((depth_mm, i) => ({
        sample_id: 'abcd'[i], depth_mm, represented_area_m2: 125000,
      })),
    });
  });
  it('preserves a zero depth and decimal area', () => {
    expect(parseUniformitySurvey('ref', rows.replace('a,4,125000', 'a,0,.5'))?.samples[0]?.depth_mm).toBe(0);
  });
  it.each([
    { reason: 'a missing evidence reference', ref: '', data: rows },
    { reason: 'missing samples', ref: 'ref', data: '' },
    { reason: 'duplicate sample IDs', ref: 'ref', data: rows.replace('b,', 'a,') },
    { reason: 'zero represented area', ref: 'ref', data: rows.replace('125000', '0') },
    { reason: 'a missing depth', ref: 'ref', data: rows.replace('a,4,', 'a,,') },
    { reason: 'a negative depth', ref: 'ref', data: rows.replace('a,4,', 'a,-4,') },
    { reason: 'a non-finite depth', ref: 'ref', data: rows.replace('a,4,', 'a,NaN,') },
    { reason: 'a hexadecimal depth', ref: 'ref', data: rows.replace('a,4,', 'a,0x4,') },
  ])('rejects $reason', ({ ref, data }) => {
    expect(() => parseUniformitySurvey(ref, data)).toThrow(/مرجع|عينة|عينات/);
  });
});
