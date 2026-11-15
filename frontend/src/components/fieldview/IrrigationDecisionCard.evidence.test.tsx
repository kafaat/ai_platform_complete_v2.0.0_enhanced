import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import IrrigationDecisionCard from './IrrigationDecisionCard';

vi.mock('../../hooks/useFieldIrrigationRecommendation', async importOriginal => ({
  ...await importOriginal<typeof import('../../hooks/useFieldIrrigationRecommendation')>(),
  useFieldIrrigationRecommendation: () => ({data: {
    status: 'dependency_unavailable', recommendation: null, limitations: [],
    inputs: {taw_source: 'modelled_from_lab_texture', taw_mm: 83, stage: 'mid'},
    evidence_ids: ['soil-lab-texture:soil_lab_results:test-reference'],
  }}),
}));

it('shows automatic-weather diagnostics and identifies the supplied laboratory reference', () => {
  render(<IrrigationDecisionCard fieldId="pivot" />);
  expect(screen.getByText('تعذّر الحصول على بيانات خدمة لازمة للتوصية')).toBeTruthy();
  expect(screen.getByText('تقدير من قوام عينة المختبر')).toBeTruthy();
  expect(screen.getByText('soil-lab-texture:soil_lab_results:test-reference')).toBeTruthy();
  expect(screen.queryByText(/Dr>TAW/)).toBeNull();
});
