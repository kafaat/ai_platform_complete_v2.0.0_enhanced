import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MapIndicatorLegend } from './MapIndicatorLegend';

describe('MapIndicatorLegend', () => {
  it('renders indicator name + semantic high/low labels for a known indicator', () => {
    const { container } = render(<MapIndicatorLegend index="ndvi" vmin={-0.2} vmax={0.9} />);
    expect(container.textContent).toContain('NDVI');
    expect(container.textContent).toContain('إشارة غطاء نباتي أعلى');
    expect(container.textContent).toContain('إشارة غطاء نباتي أدنى');
    expect(container.textContent).toContain('0.9');
  });

  it('labels NDRE values without assigning a nitrogen diagnosis', () => {
    const { container } = render(<MapIndicatorLegend index="ndre" vmin={-0.1} vmax={0.6} />);
    expect(container.textContent).toContain('قيمة NDRE أعلى');
    expect(container.textContent).toContain('قيمة NDRE أدنى');
    expect(container.textContent).not.toContain('نيتروجين');
  });

  it('falls back to generic labels for an unknown indicator (no crash)', () => {
    const { container } = render(<MapIndicatorLegend index="xyz" vmin={0} vmax={1} />);
    expect(container.textContent).toContain('XYZ');
    expect(container.textContent).toContain('مرتفع');
    expect(container.textContent).toContain('منخفض');
  });

  it('shows a value marker only when a finite value is provided', () => {
    const withVal = render(<MapIndicatorLegend index="ndvi" vmin={0} vmax={1} value={0.6} />);
    expect(withVal.container.querySelector('[data-testid="indicator-legend-marker"]')).toBeTruthy();
    const noVal = render(<MapIndicatorLegend index="ndvi" vmin={0} vmax={1} value={null} />);
    expect(noVal.container.querySelector('[data-testid="indicator-legend-marker"]')).toBeNull();
  });

  it('labels the spectral salinity index without inferring measured soil salinity', () => {
    const { container } = render(<MapIndicatorLegend index="salinity" vmin={0} vmax={1} invert />);
    expect(container.textContent).toContain('مؤشّر الملوحة الطيفي');
    expect(container.textContent).toContain('قيمة المؤشّر أدنى');
  });
});
