import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { TrialVerdictResult } from '../../lib/gisTemporalOps';
import GisTemporalOpsCard from './GisTemporalOpsCard';

const trialMutation = vi.hoisted(() => ({
  mutate: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  isError: false,
  data: undefined as TrialVerdictResult | undefined,
}));

vi.mock('../../hooks/useGisTemporalOps', () => {
  const idleMutation = () => ({ mutate: vi.fn(), reset: vi.fn(), isPending: false, isError: false });
  return {
    useGisBuffer: idleMutation,
    useGisSplit: idleMutation,
    useGisUnion: idleMutation,
    useGisValidate: idleMutation,
    useLineageLink: idleMutation,
    useReplayReconstruct: idleMutation,
    useSimulateWhatIf: idleMutation,
    useStageRiskCheck: idleMutation,
    useTemporalCheck: idleMutation,
    useTemporalCoherence: idleMutation,
    useTrialAnalyze: () => trialMutation,
  };
});

function openTrial() {
  render(<GisTemporalOpsCard />);
  fireEvent.click(screen.getByRole('button', { name: /تحليل تجربة مقترنة/ }));
}

function addBlock(number: number, treatment = 11, control = 10) {
  fireEvent.change(screen.getByLabelText(/رقم الكتلة/), { target: { value: String(number) } });
  fireEvent.change(screen.getByLabelText(/غلّة المعالجة/), { target: { value: String(treatment) } });
  fireEvent.change(screen.getByLabelText(/غلّة الشاهد/), { target: { value: String(control) } });
  fireEvent.click(screen.getByRole('button', { name: '+ أضِف كتلة' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  trialMutation.data = undefined;
});

describe('field trial replicate input', () => {
  it('rejects repeated block numbers and submits only four distinct pairs', () => {
    openTrial();
    addBlock(1);
    addBlock(1, 99);
    expect(screen.getByRole('alert')).toHaveTextContent('الكتلة رقم 1 موجودة بالفعل');
    expect(screen.queryByText('#1: 99 / 10')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'حلّل' })).toBeDisabled();

    addBlock(2);
    addBlock(3);
    expect(screen.getByRole('button', { name: 'حلّل' })).toBeDisabled();
    addBlock(4);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'حلّل' }));
    expect(trialMutation.mutate).toHaveBeenCalledWith({
      blocks: [1, 2, 3, 4].map((block_number) => ({ block_number, treatment_yield: 11, control_yield: 10 })),
      treatment_label_ar: undefined,
    });
    expect(trialMutation.reset).toHaveBeenCalledTimes(4);
  });

  it.each([0, -1, 1.5])('rejects block number %s before adding a replicate', (number) => {
    openTrial();
    addBlock(number);
    expect(screen.getByRole('alert')).toHaveTextContent('عددًا صحيحًا موجبًا');
    expect(screen.getByRole('button', { name: 'حلّل' })).toBeDisabled();
    expect(trialMutation.reset).not.toHaveBeenCalled();
  });

  it('shows a degenerate statistic as requiring review even if its limiting p-value is zero', () => {
    trialMutation.data = {
      n_blocks: 4,
      t_statistic: null,
      statistic_status: 'zero_variance_difference',
      p_value: 0,
      is_significant: true,
      recommendation_ar: 'تحقق من استقلال الكتل ودقة القياسات.',
    };
    openTrial();
    expect(screen.getByText('فروق متطابقة — راجع القياسات')).toBeInTheDocument();
    expect(screen.queryByText('فرق دالّ إحصائيّاً')).not.toBeInTheDocument();
    expect(screen.getByText('تحقق من استقلال الكتل ودقة القياسات.')).toBeInTheDocument();
  });
});
