import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { IndicatorGridResponse } from '../../hooks/useApi';
import GridSamplingDetails, { GridCoverageDetails } from './GridSamplingDetails';

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

describe('source raster field coverage', () => {
  const counts = {geometry_revision:1, denominator: 'field_pixel_centres' as const, valid_pixels: 3, field_pixels: 5, valid_pixel_ratio: 0.6};
  const known = {...grid, field_coverage: counts, valid_pixel_ratio: 0.375};
  it('shows field and rectangular coverage separately without needing sampling metadata', () => {
    const {container} = render(<GridCoverageDetails {...props} grid={{...known, spatial_sampling:null}} />);
    expect(container.textContent).toContain('داخل حدود الحقل · 60% (3 من 5 بكسل)');
    expect(container.textContent).toContain('مستطيل الراستر · 37.5%');
  });
  it('keeps a measured zero distinct from absent historical counts', () => {
    const {container, rerender} = render(<GridCoverageDetails {...props} grid={{...known,field_coverage:{...counts,valid_pixels:0,valid_pixel_ratio:0},valid_pixel_ratio:0}} />);
    expect(container.textContent).toContain('0% (0 من 5 بكسل)');
    expect(container.textContent).toContain('مستطيل الراستر · 0%');
    rerender(<GridCoverageDetails {...props} grid={{...known, field_coverage:null}} />);
    expect(container.textContent).toContain('داخل حدود الحقل · غير متاحة');
    expect(container.textContent).toContain('مستطيل الراستر · 37.5%');
  });
  it.each([
    {geometry_revision:-1}, {field_pixels:0}, {valid_pixels:7}, {valid_pixels:-1}, {valid_pixels:1.5}, {valid_pixel_ratio:1},
  ])('rejects inconsistent counts (%#)', override => {
    const {container} = render(<GridCoverageDetails {...props} grid={{...known, field_coverage:{...counts,...override}}} />);
    expect(container.textContent).toContain('داخل حدود الحقل · غير متاحة');
  });
  it.each([{fieldId:'other'}, {index:'ndmi'}, {date:'2026-10-13'}, {sceneId:'b'}])('never reuses a different observation (%#)', override=>{
    const {container}=render(<GridCoverageDetails {...props} {...override} grid={known} />);
    expect(container.textContent).not.toContain('%');
  });
  it.each([[1, '<0.01%'],[99999, '>99.99%']] as const)('does not round partial coverage into an endpoint', (valid, label)=>{
    const {container}=render(<GridCoverageDetails {...props} grid={{...known,field_coverage:{...counts,field_pixels:100000,valid_pixels:valid,valid_pixel_ratio:valid/100000}}} />);
    expect(container.textContent).toContain(label);
  });
  it('does not apply coverage counts from another boundary revision',()=>{
    const {container}=render(<GridCoverageDetails {...props} grid={{...known,grid_identity:{crs:'EPSG:4326',transform:[1,0,0,0,-1,1],geometry_revision:2}}} />);
    expect(container.textContent).toContain('داخل حدود الحقل · غير متاحة');
    expect(container.textContent).toContain('مستطيل الراستر · 37.5%');
  });
  it('compares the requested day in UTC at a timezone boundary',()=>{
    const {container}=render(<GridCoverageDetails {...props} grid={{...known,date:'2026-10-13T00:15:00+03:00'}} />);
    expect(container.textContent).toContain('60%');
  });
});
