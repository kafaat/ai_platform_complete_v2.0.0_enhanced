// P2-FE-2 — مفتاح ذاكرة React Query لشبكة المؤشّر يجب أن يحمل **كلّ** معاملات الطلب.
// كان QK.indicatorGrid(fid, index, date) يُغفِل `grid`، فطلبان بدقّتين مختلفتين لنفس
// (الحقل، المؤشّر، التاريخ) يتشاركان مُدخَلاً واحداً: الثاني يقرأ شبكة الأوّل بأبعاد أخرى.
// كذلك SatellitePage كانت تطلب الشبكة لـ'latest' بينما البلاطات/الشارة للتاريخ المختار.
import type { ReactNode } from 'react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const raster = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>();
  return { ...real, rasterApi: { ...real.rasterApi, get: raster.get } };
});

import { QK, useIndicatorGrid } from './useApi';

function Probe({ grid }: { grid: number }) {
  const q = useIndicatorGrid('fld_1', 'ndvi', 'latest', grid);
  return <span data-testid={`g${grid}`}>{q.data ? String(q.data.rows) : '-'}</span>;
}

describe('useIndicatorGrid cache key includes grid size', () => {
  it('QK.indicatorGrid differs by grid and keeps the field prefix for invalidation', () => {
    expect(QK.indicatorGrid('f', 'ndvi', 'latest', 16)).not.toEqual(QK.indicatorGrid('f', 'ndvi', 'latest', 32));
    expect(QK.indicatorGrid('f', 'ndvi', 'latest', 32).slice(0, 2)).toEqual(['indicator-grid', 'f']);
  });

  it('two grid sizes for the same field/index/date fetch and return their own grids', async () => {
    raster.get.mockImplementation((_url: string, cfg: { params: { grid: number } }) =>
      Promise.resolve({ data: { rows: cfg.params.grid } }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrap = (children: ReactNode) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    render(wrap(<><Probe grid={16} /><Probe grid={32} /></>));
    await waitFor(() => {
      expect(screen.getByTestId('g16').textContent).toBe('16');
      expect(screen.getByTestId('g32').textContent).toBe('32');
    });
    const grids = raster.get.mock.calls.map((c) => (c[1] as { params: { grid: number } }).params.grid).sort();
    expect(grids).toEqual([16, 32]);
  });
});

describe('SatellitePage grid/badge describe the same date as the tiles', () => {
  const src = readFileSync(join(process.cwd(), 'src/sections/SatellitePage.tsx'), 'utf8');
  it('requests the indicator grid for mapDate, not a hard-coded latest', () => {
    expect(src).not.toContain("useIndicatorGrid(fieldId, gridIndex, 'latest')");
    expect(src).toMatch(/useIndicatorGrid\(fieldId, gridIndex, mapDate\)/);
    // الاستدعاء بعد تعريف mapDate (لا إشارة لمتغيّر قبل تعريفه).
    expect(src.indexOf('useIndicatorGrid(fieldId, gridIndex, mapDate)')).toBeGreaterThan(
      src.indexOf("const mapDate = selectedDate || 'latest'"),
    );
  });
});
