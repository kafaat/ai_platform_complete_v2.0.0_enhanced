import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { LearningSummary } from '../services/api';
import type { PersistedEvidence } from '../services/api/calibration';
import LearningDashboardPage from './LearningDashboardPage';

const hooks = vi.hoisted(() => ({
  useDecisionRecords: vi.fn(),
  useLearningSummary: vi.fn(),
  usePersistedEvidence: vi.fn(),
}));
vi.mock('../hooks/useApi', () => hooks);

const query = (data: unknown) => ({ data, isLoading: false, isError: false, refetch: vi.fn() });

const collectionWarning = 'عتبة جمع العيّنات تقديريّة — بلوغها وحده لا يمنح اعتماداً زراعياً أو معايرة';
const pendingReviewWarning = 'العيّنة بلغت العتبة لكنّ الدليل غير مُعتمَد — يلزم مراجعة مختصّ قبل وصفه «مُتحقَّقاً ميدانيّاً»';

const evidence: PersistedEvidence = {
  region: 'jawf', sample_count: 30, persisted_rows: 30,
  field_verified_min_samples: 30, samples_to_verified: 0,
  sample_completeness: 'threshold_reached', evidence_level: 'field_sample_complete',
  review_status: 'unreviewed', success_rate: 0, success_flag_counts: {},
  last_evaluated_at: null, calibrated: false, source: 'persisted_outcomes',
  independence: { fields: 1, seasons: 1, farms: 1, tenants: 1, unknown_unit_samples: 0 },
  warnings_ar: [collectionWarning, pendingReviewWarning],
};

const linkedSummary: LearningSummary = {
  overall: { outcome_count: 2, success_rate: 0.5 },
  regions: [{ region: 'jawf', evidence_level: 'field_sample_complete' }],
  outcome_reconciliation: {
    enabled: true, total: 2, independent_case_count: 1, linked_group_count: 1,
    rows_by_source: { outcome_record: 1, recommendation_outcomes: 1 },
    sample_count_basis: 'rows',
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  hooks.useDecisionRecords.mockReturnValue(query({ decisions: [], count: 1 }));
  hooks.useLearningSummary.mockReturnValue(query(linkedSummary));
  hooks.usePersistedEvidence.mockImplementation((region: string) => query(region === 'jawf' ? evidence : undefined));
});

function expectCounter(label: string, value: string) {
  const panel = within(screen.getByRole('region', { name: 'الحالات ومصادر النتائج' }));
  expect(panel.getByText(label).nextElementSibling).toHaveTextContent(new RegExp(`^${value}$`));
}

describe('LearningDashboardPage evidence and outcome counts', () => {
  it('keeps thirty rows from one field unreviewed and describes collection, not approval', () => {
    render(<LearningDashboardPage />);
    const card = within(screen.getByRole('region', { name: 'دليل الجوف' }));
    expect(card.getByText('عيّنة مكتملة — بانتظار المراجعة')).toBeInTheDocument();
    expect(card.getByText('غير مراجَعة')).toBeInTheDocument();
    expect(card.getByText('30 / 30 عيّنة')).toBeInTheDocument();
    expect(card.getByText('اكتمال جمع العيّنات')).toBeInTheDocument();
    expect(card.getAllByText(/لا يمنح اعتماداً زراعياً أو معايرة/)).toHaveLength(1);
    expect(card.getAllByText(/مراجعة مختصّ/)).toHaveLength(1);
    expect(card.getByText('1 / 1 / 1 / 1')).toBeInTheDocument();
    expect(card.getByText(/معرّفات مميّزة/)).toBeInTheDocument();
    expect(card.getByText(`• ${evidence.warnings_ar[0]}`)).toBeInTheDocument();
    expect(card.queryByText('مُتحقَّق ميدانيّاً')).not.toBeInTheDocument();
    expect(screen.queryByText(/التقدّم نحو التحقّق الميدانيّ/)).not.toBeInTheDocument();
  });

  it('shows the remaining collection count without promising verification', () => {
    hooks.usePersistedEvidence.mockImplementation((region: string) => query(region === 'jawf' ? {
      ...evidence, sample_count: 29, samples_to_verified: 1,
      evidence_level: 'field_preliminary', sample_completeness: 'below_threshold',
    } : undefined));
    render(<LearningDashboardPage />);
    const card = within(screen.getByRole('region', { name: 'دليل الجوف' }));
    expect(card.getByText('تبقّى 1 عيّنة لبلوغ عتبة الجمع.')).toBeInTheDocument();
    expect(card.queryByText(/للوصول إلى «مُتحقَّق/)).not.toBeInTheDocument();
  });

  it('uses the reported review state and keeps calibration separate', () => {
    hooks.usePersistedEvidence.mockImplementation((region: string) => query(region === 'jawf' ? {
      ...evidence, review_status: 'reviewed', evidence_level: 'field_verified',
      warnings_ar: [collectionWarning],
    } : undefined));
    render(<LearningDashboardPage />);
    const card = within(screen.getByRole('region', { name: 'دليل الجوف' }));
    expect(card.getByText('مُتحقَّق ميدانيّاً')).toBeInTheDocument();
    expect(card.getByText('مراجَعة من مختصّ')).toBeInTheDocument();
    expect(card.getByText(/تقديريّ غير مُعايَر/)).toBeInTheDocument();
    expect(card.getAllByText(/لا يمنح اعتماداً زراعياً أو معايرة/)).toHaveLength(1);
    expect(card.queryByText(/مراجعة مختصّ/)).not.toBeInTheDocument();
  });

  it('shows one linked case alongside both source rows and their counting basis', () => {
    render(<LearningDashboardPage />);
    expectCounter('الحالات بحسب الربط المتاح', '1');
    expectCounter('صفوف النتائج', '2');
    expectCounter('صفوف أثر القرار', '1');
    expectCounter('صفوف تعلّم الغلة', '1');
    expect(screen.getByText('أساس عدّ العينات: صفوف النتائج')).toBeInTheDocument();
    expect(screen.getByText(/لا يثبت استقلال الحقول أو المزارع/)).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'سجلات النتائج' })).getByText('2')).toBeInTheDocument();
    expect(screen.queryByText('نتائج مقيسة')).not.toBeInTheDocument();
  });

  it('does not derive missing case or source counts from the total', () => {
    hooks.useLearningSummary.mockReturnValue(query({
      overall: { outcome_count: 12 }, outcome_reconciliation: { total: 12 },
    }));
    render(<LearningDashboardPage />);
    expectCounter('صفوف النتائج', '12');
    expectCounter('الحالات بحسب الربط المتاح', '—');
    expectCounter('صفوف أثر القرار', '—');
    expectCounter('صفوف تعلّم الغلة', '—');
    expect(screen.getByText('أساس عدّ العينات: غير متاح')).toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'مناطق متحقّقة ميدانياً' })).getByText('—')).toBeInTheDocument();
  });

  it('preserves measured zero counts, including a missing second source', () => {
    hooks.useLearningSummary.mockReturnValue(query({
      overall: { outcome_count: 0 }, regions: [],
      outcome_reconciliation: { total: 0, independent_case_count: 0, rows_by_source: { outcome_record: 0 } },
    }));
    render(<LearningDashboardPage />);
    expectCounter('الحالات بحسب الربط المتاح', '0');
    expectCounter('صفوف النتائج', '0');
    expectCounter('صفوف أثر القرار', '0');
    expectCounter('صفوف تعلّم الغلة', '—');
    expect(within(screen.getByRole('group', { name: 'مناطق متحقّقة ميدانياً' })).getByText('0')).toBeInTheDocument();
  });

  it.each([null, { enabled: false, total: 12, independent_case_count: 6 }, {
    total: -1, independent_case_count: 1.5,
    rows_by_source: { outcome_record: Number.NaN, recommendation_outcomes: Number.POSITIVE_INFINITY },
  }])('keeps absent, disabled or invalid reconciliation counters unavailable: %j', (reconciliation) => {
    hooks.useLearningSummary.mockReturnValue(query({
      ...linkedSummary, outcome_reconciliation: reconciliation,
    }));
    render(<LearningDashboardPage />);
    for (const label of ['الحالات بحسب الربط المتاح', 'صفوف النتائج', 'صفوف أثر القرار', 'صفوف تعلّم الغلة']) {
      expectCounter(label, '—');
    }
  });

  it('does not equate the all-identifiers-missing counter with missing field or season identity', () => {
    hooks.usePersistedEvidence.mockImplementation((region: string) => query(region === 'jawf' ? {
      ...evidence, review_status: undefined,
      independence: { fields: 0, seasons: 0, farms: 0, tenants: 1, unknown_unit_samples: 2 },
    } : undefined));
    render(<LearningDashboardPage />);
    const quality = within(screen.getByTestId('evidence-quality-jawf'));
    expect(quality.getByText('0 / 0 / 0 / 1')).toBeInTheDocument();
    expect(quality.getByText(/2 عيّنة بلا أيّ معرّف للحقل أو الموسم أو المزرعة أو المستأجر/)).toBeInTheDocument();
    expect(quality.getByText(/هذا العدّ لا يكشف النقص في كلّ معرّف على حدة/)).toBeInTheDocument();
    expect(quality.queryByText('مراجَعة من مختصّ')).not.toBeInTheDocument();
  });
});
