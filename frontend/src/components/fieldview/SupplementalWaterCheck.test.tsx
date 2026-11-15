import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { SupplementalWaterCheck } from './IrrigationDecisionCard';
import { kongApi } from '../../services/api';

vi.mock('../../services/api', () => ({kongApi: {post: vi.fn()}}));
it.each([
  [{field_id:'east',season_id:'winter',execution_allowed:false,status:'verified'}, 'توافر جدول'],
  [{field_id:'east',season_id:'old',execution_allowed:false,status:'verified'}, 'لم يكتمل'],
  [{field_id:'east',execution_allowed:false,status:'blocked',reason:'missing_capability'}, 'missing_capability'],
  [{field_id:'other',execution_allowed:false,status:'verified'}, 'تعذّر التحقق'],
])('reads the field capability assessment on demand', async (data, expected) => {
  vi.mocked(kongApi.post).mockResolvedValueOnce({data});
  render(<SupplementalWaterCheck fieldId="east" seasonId="winter"/>);
  fireEvent.click(screen.getByRole('button',{name:'فحص إمكانية الري التكميلي'}));
  expect(await screen.findByText(new RegExp(expected))).toBeTruthy();
  expect(kongApi.post).toHaveBeenLastCalledWith('/api/v1/fields/east/irrigation/mpc/hourly-recommendation',{persist:false});
});
