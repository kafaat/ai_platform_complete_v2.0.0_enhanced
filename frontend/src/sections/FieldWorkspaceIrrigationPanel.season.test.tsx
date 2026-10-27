// UI-I1 — نصيحة الري تُحسَب في الخادم للموسم النشط الحاليّ للحقل وطقس اليوم
// (field_workspace_weather.field_irrigation_advice_facade → _field_weather_context
// يختار أحدث موسم status='active'). الطلب لا يحمل season_id، فلا يجوز أن يُوحي
// مفتاح الاستعلام أو العرض بأنّها محسوبة للموسم المختار في الرابط (قد يكون تاريخيّاً).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const api = vi.hoisted(() => ({
  getFieldIrrigationAdvice: vi.fn(),
  getFieldIrrigationSchedules: vi.fn(),
}));
vi.mock('../services/api/fieldIrrigation', () => api);
vi.mock('./IrrigationManualOperationsPanel', () => ({ default: () => null }));
vi.mock('./IrrigationEngineeringCalculator', () => ({ default: () => null }));
vi.mock('./ReservoirBoosterNetworkCalculator', () => ({ default: () => null }));
vi.mock('../components/OpenMeteoAttribution', () => ({ OpenMeteoAttribution: () => null }));

import FieldWorkspaceIrrigationPanel from './FieldWorkspaceIrrigationPanel';

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: ReactNode) => <QueryClientProvider client={client}>{node}</QueryClientProvider>;
  return { client, wrap };
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('UI-I1: نصيحة الري لا تُنسَب إلى موسم الرابط', () => {
  it('يطلب النصيحة بالحقل وحده، ولا يحمل season_id في مفتاح الاستعلام، ويُفصح أنّها للموسم النشط', async () => {
    api.getFieldIrrigationAdvice.mockResolvedValue({ field_id: 'f1', recommended_mm: 12, stage: 'mid' });
    api.getFieldIrrigationSchedules.mockResolvedValue([]);
    const { client, wrap } = setup();
    render(wrap(<FieldWorkspaceIrrigationPanel fieldId="f1" seasonId="season-2023-historical" />));

    await screen.findByText('12');
    expect(api.getFieldIrrigationAdvice).toHaveBeenCalledWith('f1');
    const adviceKeys = client.getQueryCache().findAll()
      .map(q => q.queryKey)
      .filter(k => k.includes('irrigation-advice'));
    expect(adviceKeys).toHaveLength(1);
    expect(adviceKeys[0]).not.toContain('season-2023-historical');
    expect(screen.getByText(/محسوبة للموسم النشط/)).toBeInTheDocument();
  });

  it('تبديل موسم الرابط لا يُعيد جلب نصيحة مطابقة كأنّها لموسم آخر', async () => {
    api.getFieldIrrigationAdvice.mockResolvedValue({ field_id: 'f1', recommended_mm: 7 });
    api.getFieldIrrigationSchedules.mockResolvedValue([]);
    const { wrap } = setup();
    const { rerender } = render(wrap(<FieldWorkspaceIrrigationPanel fieldId="f1" seasonId="season-a" />));
    await screen.findByText('7');
    rerender(wrap(<FieldWorkspaceIrrigationPanel fieldId="f1" seasonId="season-b" />));
    await waitFor(() => expect(screen.getByText('7')).toBeInTheDocument());
    expect(api.getFieldIrrigationAdvice).toHaveBeenCalledTimes(1);
  });
});
