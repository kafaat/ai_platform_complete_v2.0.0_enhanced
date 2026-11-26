import { describe, expect, it } from 'vitest';
import { scopedP3Evidence } from './SoilP3Evidence';

describe('stored P3 evidence scope', () => {
  const assessment = { product_id: 'synthetic-p3', tenant_id: 'a', field_id: 'f' };
  it('returns only a product scoped to the selected tenant and field', () => {
    expect(scopedP3Evidence(assessment, 'a', 'f')).toEqual(assessment);
    expect(scopedP3Evidence(assessment, 'b', 'f')).toBeNull();
    expect(scopedP3Evidence(assessment, 'a', 'g')).toBeNull();
  });
  it('rejects incomplete and malformed responses', () => {
    for (const input of [null, [], {}, { ...assessment, product_id: '' }]) {
      expect(scopedP3Evidence(input, 'a', 'f')).toBeNull();
    }
  });
});
