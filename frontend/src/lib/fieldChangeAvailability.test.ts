import { describe, expect, it } from 'vitest';
import { unavailableFieldChangeMessage } from './fieldChangeAvailability';

describe('field-change availability message (raster → UI truth)', () => {
  it('distinguishes true COG imagery from an unassessable comparison', () => {
    const message = unavailableFieldChangeMessage({
      available: false, real_data: true, status: 'not_assessable',
      reason_codes: ['no_common_valid_pixels'],
    });
    expect(message).toContain('لا توجد بكسلات صالحة مشتركة');
    expect(message).not.toContain('لا توجد بيانات COG');
  });

  it('does not invent COG imagery when either date is missing', () => {
    expect(unavailableFieldChangeMessage({ available: false, real_data: false }))
      .toContain('لا توجد بيانات COG');
  });

  it('preserves authoritative refusal notes from raster-service', () => {
    expect(unavailableFieldChangeMessage({
      available: false, real_data: false, note: 'change_grid_quality_gate_failed',
    })).toBe('change_grid_quality_gate_failed');
  });

  it('does not claim success when the refusal reason is not recognized', () => {
    const message = unavailableFieldChangeMessage({
      available: false, real_data: true, status: 'not_assessable',
      reason_codes: ['future_reason_code'],
    });
    expect(message).toContain('لم تتحقّق شروط تقييم التغيّر');
    expect(message).not.toContain('لا توجد بيانات COG');
  });
});
