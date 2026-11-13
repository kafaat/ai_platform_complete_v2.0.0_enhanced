// أداة تخطيط بذار القمح: المرجع ⇒ المعدل، الاحتياج والشراء، ونقل الخطة إلى نموذج الموسم المخطَّط.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import WheatSeasonPlanner from './WheatSeasonPlanner';
import SeasonStep from './fieldsetup/SeasonStep';
import type { WheatReference } from '../lib/wheatRegister';

const post = vi.fn();
vi.mock('../services/api', () => ({
  kongApi: { post: (...args: unknown[]) => post(...args) },
  apiErrorMessage: () => 'error',
}));

const refs: WheatReference[] = [
  { sheet: 'حميري - تجارب الري المطري', variety: 'حميري', hectares: 0.022, seedKg: 2.5, rainfed: true, day: '2026-09-16' },
  { sheet: 'م1ق3', variety: 'حميري', hectares: 12.5, seedKg: 1932, rainfed: false, day: '2026-10-21' },
];

function plan() {
  fireEvent.change(screen.getByLabelText('صنف القمح'), { target: { value: 'حميري' } });
  fireEvent.change(screen.getByLabelText('مرجع البذار'), { target: { value: 'م1ق3' } });
  fireEvent.change(screen.getByLabelText('ري الموسم الجديد'), { target: { value: 'pivot' } });
  fireEvent.change(screen.getByLabelText('المساحة المخططة بالهكتار'), { target: { value: '50' } });
  fireEvent.change(screen.getByLabelText('المخزون الصالح من الصنف بالكيلوغرام'), { target: { value: '728' } });
  fireEvent.change(screen.getByLabelText('سعر شراء الكيلو بالريال اليمني'), { target: { value: '100' } });
}

describe('WheatSeasonPlanner', () => {
  beforeEach(() => post.mockReset());

  it('derives the rate from the chosen reference and computes need, purchase and cost', () => {
    const onApply = vi.fn();
    render(<WheatSeasonPlanner onApply={onApply} initialRefs={refs} initialSource="سجل.xlsx" />);
    fireEvent.change(screen.getByLabelText('صنف القمح'), { target: { value: 'بوني' } });
    expect(screen.getByLabelText('معدل البذار المخطط كغ/هكتار')).toHaveValue(null);
    fireEvent.change(screen.getByLabelText('صنف القمح'), { target: { value: 'حميري' } });
    fireEvent.change(screen.getByLabelText('مرجع البذار'), { target: { value: 'حميري - تجارب الري المطري' } });
    expect(screen.getByLabelText('معدل البذار المخطط كغ/هكتار')).toHaveValue(113.64);
    plan();
    expect(screen.getByLabelText('معدل البذار المخطط كغ/هكتار')).toHaveValue(154.56);
    fireEvent.click(screen.getByRole('button', { name: 'استخدام الخطة في الموسم' }));
    expect(onApply).toHaveBeenCalledTimes(1);
    const sent = onApply.mock.calls[0][0];
    expect(sent).toMatchObject({ variety: 'حميري', rate: '154.56', irrigation: 'pivot' });
    expect(sent.note).toContain('المرجع سجل.xlsx / م1ق3');
    expect(sent.note).toContain('الاحتياج ' + (7728).toLocaleString('ar', { maximumFractionDigits: 2 }) + ' كغ');
    expect(sent.note).toContain('شراء ' + (7000).toLocaleString('ar', { maximumFractionDigits: 2 }) + ' كغ');
    expect(sent.note).toContain((700000).toLocaleString('ar', { maximumFractionDigits: 2 }) + ' ريال يمني');
  });

  it('keeps the apply button disabled without variety, area or irrigation', () => {
    render(<WheatSeasonPlanner onApply={vi.fn()} initialRefs={refs} />);
    expect(screen.getByRole('button', { name: 'استخدام الخطة في الموسم' })).toBeDisabled();
  });

  it('SeasonStep saves the applied plan as a planned wheat season', async () => {
    post.mockResolvedValue({ data: { season_id: 'ssn_1', status: 'planned' } });
    const onNext = vi.fn();
    render(<SeasonStep ctx={{ fieldId: 'wheat-field', fieldName: 'محور', areaHa: 50, crop: '' }}
      stepTotal={4} stepIndex={1} canGoBack={false} onBack={() => {}} onSkip={() => {}} onNext={onNext} />);
    fireEvent.click(screen.getByText('تخطيط بذار القمح من سجل الزراعة'));
    fireEvent.change(screen.getByLabelText('صنف القمح'), { target: { value: 'حميري' } });
    fireEvent.change(screen.getByLabelText('ري الموسم الجديد'), { target: { value: 'pivot' } });
    fireEvent.change(screen.getByLabelText('المساحة المخططة بالهكتار'), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText('معدل البذار المخطط كغ/هكتار'), { target: { value: '150' } });
    fireEvent.click(screen.getByRole('button', { name: 'استخدام الخطة في الموسم' }));
    fireEvent.click(screen.getByRole('button', { name: /حفظ الموسم المخطط/ }));
    await waitFor(() => expect(onNext).toHaveBeenCalled());
    const [url, body] = post.mock.calls[0];
    expect(url).toBe('/api/v1/fields/wheat-field/seasons');
    expect(body).toMatchObject({ crops: ['قمح'], initial_status: 'planned', cultivar: 'حميري', irrigation_type: 'pivot', seed_rate_kg_ha: 150 });
    expect(body.notes_ar).toMatch(/^خطة بذار القمح · المرجع إدخال يدوي · المساحة المخططة 50 هكتار/);
  });
});
