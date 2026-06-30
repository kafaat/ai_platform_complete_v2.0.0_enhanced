import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { MapIndicatorLegend } from './MapIndicatorLegend';

describe('MapIndicatorLegend', () => {
  it('renders indicator name + semantic high/low labels for a known indicator', () => {
    const { container } = render(<MapIndicatorLegend index="ndvi" vmin={-0.2} vmax={0.9} />);
    expect(container.textContent).toContain('NDVI');
    expect(container.textContent).toContain('غطاء صحّي');
    expect(container.textContent).toContain('تربة عارية');
    expect(container.textContent).toContain('0.9');
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

  it('supports salinity-style indicators (high value = problem) via invert', () => {
    const { container } = render(<MapIndicatorLegend index="salinity" vmin={0} vmax={1} invert />);
    expect(container.textContent).toContain('ملوحة مرتفعة');
    expect(container.textContent).toContain('ملوحة منخفضة');
  });
});
