import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { IndicatorGridResponse } from '../../hooks/useApi';
import GridSamplingDetails from './GridSamplingDetails';

const grid: IndicatorGridResponse = {
  field_id: 'f', index: 'ndre', date: '2026-10-12T10:03:00Z', bbox: [0, 0, 1, 1],
  rows: 1, cols: 1, grid: [[0.2]], stats: { min: 0.2, max: 0.2, mean: 0.2 },
  zones: [], source: 'cog', real_data: true, indicator_product: { provenance: { scene_id: 'scene-a' } },
  spatial_sampling: { native_band_resolution_m: { B08: 10, B05: 20 }, output_pixel_size_m: [20, 19], resampling_method: 'nearest' },
};
const props = { grid, fieldId: 'f', index: 'ndre', date: '2026-10-12', sceneId: 'scene-a' };

describe('sampling provenance of the saved indicator raster', () => {
  it('renders native bands, both output pixel dimensions and processing separately', () => {
    const { container } = render(<GridSamplingDetails {...props} />);
    expect(container.textContent).toContain('B08 10 م، B05 20 م');
    expect(container.textContent).toContain('20 × 19');
    expect(container.textContent).toContain('أقرب جار');
    expect(container.textContent).toContain('scene-a');
  });

  it.each([
    { fieldId: 'other' }, { index: 'ndvi' }, { date: '2026-10-13' },
    { date: '2026-10-12T11:30:00Z' }, { sceneId: 'scene-b' },
    { grid: { ...grid, real_data: false } }, { grid: { ...grid, indicator_product: null } },
    { grid: { ...grid, spatial_sampling: undefined } },
  ])('hides absent or unmatched provenance (%#)', (overrides) => {
    const { container } = render(<GridSamplingDetails {...props} {...overrides} />);
    expect(container.textContent).toBe('');
  });

  it('shows only measured values from the returned latest scene', () => {
    const partial: IndicatorGridResponse = { ...grid, spatial_sampling: {
      native_band_resolution_m: { B08: 0 }, output_pixel_size_m: [20, 19], resampling_method: null,
    } };
    const { container } = render(<GridSamplingDetails {...props} grid={partial} date="latest" sceneId={null} />);
    expect(container.textContent).toContain('scene-a');
    expect(container.textContent).toContain('20 × 19');
    expect(container.textContent).not.toMatch(/B08|النطاقات|طريقة/);
  });
});
