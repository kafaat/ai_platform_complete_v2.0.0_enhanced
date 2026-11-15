// v26 workstream 03: an unsupported crop returns estimated_yield_kg_ha=null; the wizard shows
// «—» and says it is not an observed zero, while a real estimate keeps its usual note.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

const post = vi.hoisted(() => vi.fn());
vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>();
  return { ...real, kongApi: { ...real.kongApi, post } };
});

import YieldStep from './YieldStep';

const CTX = { fieldId: 'fld_1', fieldName: 'حقل', crop: 'قمح', areaHa: 2 };

async function run(data: Record<string, unknown>) {
  post.mockResolvedValueOnce({ data });
  render(
    <YieldStep ctx={CTX} onNext={vi.fn()} onSkip={vi.fn()} onBack={vi.fn()}
      canGoBack stepIndex={3} stepTotal={4} />,
  );
  await act(async () => { fireEvent.click(screen.getByText('تشغيل التقدير')); });
}

beforeEach(() => { cleanup(); post.mockReset(); });

describe('YieldStep null estimate', () => {
  it('renders «—» and the not-a-zero note for an unsupported crop', async () => {
    await run({
      estimated_yield_kg_ha: null, yield_status: 'unavailable_unrecognized_crop', confidence: 0,
    });
    expect(screen.getByText(/ليست صفراً مرصوداً/)).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText('٠')).toBeNull();
  });

  it('keeps the estimate note when a number comes back', async () => {
    await run({ estimated_yield_kg_ha: 2800, yield_status: 'estimated', confidence: 0.4 });
    expect(screen.getByText(/تقدير نموذجيّ مبكّر/)).toBeInTheDocument();
    expect(screen.queryByText(/ليست صفراً مرصوداً/)).toBeNull();
  });
});
