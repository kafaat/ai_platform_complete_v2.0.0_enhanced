import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { GradientScale, SegmentedScale, bandIndexForValue } from './ScaleLegend';
import { NDVI_BANDS, IRRIGATION_URGENCY_BANDS } from './scalePresets';

describe('ScaleLegend — bandIndexForValue', () => {
  it('selects the band containing the value (half-open [from,to))', () => {
    expect(bandIndexForValue(NDVI_BANDS, 0.05)).toBe(0); // حرج
    expect(bandIndexForValue(NDVI_BANDS, 0.35)).toBe(2); // متوسّط
    expect(bandIndexForValue(NDVI_BANDS, 0.9)).toBe(4); // ممتاز
  });

  it('returns -1 for null/NaN', () => {
    expect(bandIndexForValue(NDVI_BANDS, null)).toBe(-1);
    expect(bandIndexForValue(NDVI_BANDS, Number.NaN)).toBe(-1);
  });
});

describe('GradientScale', () => {
  it('renders a value marker when value is within range', () => {
    const { getByTestId } = render(
      <GradientScale colors={['#a50026', '#1a9850']} min={0} max={1} value={0.5} title="NDVI" unit="" />,
    );
    expect(getByTestId('scale-value-marker')).toBeTruthy();
  });

  it('omits the marker when value is null', () => {
    const { queryByTestId } = render(
      <GradientScale colors={['#a50026', '#1a9850']} min={0} max={1} value={null} />,
    );
    expect(queryByTestId('scale-value-marker')).toBeNull();
  });
});

describe('SegmentedScale', () => {
  it('highlights exactly one active band for a value', () => {
    const { getAllByTestId } = render(
      <SegmentedScale bands={IRRIGATION_URGENCY_BANDS} value={0.8} title="إلحاح الريّ" />,
    );
    expect(getAllByTestId('scale-band-active').length).toBe(1);
  });

  it('shows the active band hint', () => {
    const { container } = render(
      <SegmentedScale bands={IRRIGATION_URGENCY_BANDS} value={0.8} />,
    );
    expect(container.textContent).toContain('ريّ فوريّ');
  });
});
