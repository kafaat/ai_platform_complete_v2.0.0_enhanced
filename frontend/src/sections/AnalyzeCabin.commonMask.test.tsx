// AnalyzeCabin asks for the common-mask trend and shows its field coverage and line-fit
// quality. A trend over too small a common area is declared, not drawn as a direction.
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const st = vi.hoisted(() => ({
  ts: undefined as unknown,
  calls: [] as unknown[][],
}));
const idle = { data: undefined, isLoading: false, isError: false };
vi.mock('../hooks/useApi', () => ({
  useFieldTimeseries: (...args: unknown[]) => {
    st.calls.push(args);
    return { data: st.ts, isLoading: false, isError: false };
  },
  useVegetationTimeseries: () => idle,
  useDiseaseRisk: () => idle,
  useSeasons: () => idle,
}));
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({
    options: [{ id: 'f1', name: 'حقل ١' }], fieldId: 'f1', setFieldId: vi.fn(), isLoading: false, isError: false,
  }),
}));

import AnalyzeCabin from './AnalyzeCabin';

const points = [
  { datetime: '2026-01-10', mean: 0.43 },
  { datetime: '2026-03-10', mean: 0.57 },
];

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterEach(() => { cleanup(); st.calls = []; });

describe('AnalyzeCabin common-mask trend', () => {
  it('requests the common mask and shows coverage and fit quality', () => {
    st.ts = {
      available: true, points,
      trend: { slope: 0, direction: 'stable', points: 2, fit_quality: 'undetermined' },
      common_mask: { status: 'ok', common_coverage_ratio: 0.5, scenes_used: 2, scenes_excluded: 1 },
    };
    render(<AnalyzeCabin />);
    expect(st.calls[0]).toEqual(['f1', 'ndvi', '', { commonMask: true }]);
    const q = screen.getByTestId('trend-quality').textContent ?? '';
    expect(q).toContain('50%');
    expect(q).toContain('2 مشهد');
    expect(q).toContain('استُبعد 1');
    expect(q).toContain('غير محدّدة');
    expect(screen.getByText(/مستقرّ/)).toBeInTheDocument();
  });

  it('declares insufficient common coverage instead of a direction', () => {
    st.ts = {
      available: true, points,
      trend: { slope: null, direction: 'insufficient_common_coverage', points: 2 },
      common_mask: { status: 'insufficient_common_coverage', common_coverage_ratio: 0.1, scenes_used: 2 },
    };
    render(<AnalyzeCabin />);
    expect(screen.getByTestId('trend-insufficient')).toBeInTheDocument();
    expect(screen.queryByText(/مستقرّ/)).not.toBeInTheDocument();
    expect(screen.getByTestId('trend-quality').textContent).toContain('10%');
  });

  it('reads the backend direction names (improving)', () => {
    st.ts = { available: true, points, trend: { slope: 0.07, direction: 'improving', points: 2, fit_quality: 'linear' } };
    render(<AnalyzeCabin />);
    expect(screen.getByText(/صاعد/)).toBeInTheDocument();
    expect(screen.getByTestId('trend-quality').textContent).toContain('خطّيّة');
  });
});
