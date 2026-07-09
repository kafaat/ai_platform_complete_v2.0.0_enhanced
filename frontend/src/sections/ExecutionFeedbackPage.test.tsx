// اختبارات رصد حلقة التنفيذ — سلوك المكوّن عبر مُسرَحة hook useExecutionFeedback
// (عزل تامّ): (أ) ترويسة التلخيص + نسبة الإغلاق + رقائق by_status؛ (ب) صفوف القرارات
// بشارات حالة الحلقة الملوّنة؛ (ج) execution_unknown يُعرَض رماديّاً بـnote_ar لا
// «نُفِّذ»/أخضر؛ (د) executed_unmeasured كهرمانيّ لا نجاح؛ (هـ) closure_rate:null ⇒
// «غير محسوبة» لا 0%؛ (و) بانر القراءة فقط حاضر؛ (ز) 404 ⇒ «الميزة غير مُفعَّلة»؛
// (ح) 503 ⇒ خطأ صادق. المحاكاة في الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import * as useApiModule from '../hooks/useApi';
import type { ExecutionFeedbackResult } from '../services/api';
import ExecutionFeedbackPage from './ExecutionFeedbackPage';

// نتيجة كاملة نموذجيّة مطابقة لعقد GET /api/v1/execution/feedback.
const SAMPLE: ExecutionFeedbackResult = {
  generated_at: '2026-06-21T00:00:00+00:00',
  decisions: [
    {
      decision_id: 'dec_1', decision_type: 'irrigation_plan', field_id: 'field_01',
      created_at: '2026-06-10T08:00:00+00:00',
      execution_outcome: 'executed', executed_at: '2026-06-10T09:00:00+00:00',
      exec_note_ar: 'تشغيل ناجح', outcome_measured: true, outcome_success: true,
      loop_status: 'closed_ok', loop_status_ar: 'حلقة مغلقة (نُفِّذ ونجح)',
      color: 'green', note_ar: null,
    },
    {
      decision_id: 'dec_2', decision_type: 'fertilizer_plan', field_id: 'field_02',
      created_at: '2026-06-11T08:00:00+00:00',
      execution_outcome: 'executed', executed_at: '2026-06-11T10:00:00+00:00',
      exec_note_ar: null, outcome_measured: false, outcome_success: null,
      loop_status: 'executed_unmeasured', loop_status_ar: 'نُفِّذ بلا قياس',
      color: 'amber', note_ar: 'نُفِّذ لكن لم تُقَس النتيجة بعد — ليس نجاحاً.',
    },
    {
      decision_id: 'dec_3', decision_type: 'pest_plan', field_id: 'field_03',
      created_at: '2026-06-12T08:00:00+00:00',
      execution_outcome: null, executed_at: null,
      exec_note_ar: null, outcome_measured: false, outcome_success: null,
      loop_status: 'execution_unknown', loop_status_ar: 'يحتاج بيانات (غير مُسجَّل)',
      color: 'gray', note_ar: 'لا قيد في سجلّ التنفيذ — لا يُفترَض مُنفَّذاً.',
    },
  ],
  decision_count: 3,
  by_status: {
    closed_ok: 1, executed_off_plan: 0, executed_unmeasured: 1,
    execution_failed: 0, execution_unknown: 1,
  },
  totals: { executed: 2, failed: 0, measured: 1, closed_ok: 1 },
  closure_rate: 0.5,
  provenance: {
    calibrated: 'not_applicable',
    note_ar: 'حالات الحلقة من سجلّات مُدامة فقط، ولا تُفترَض حالة دون قيد.',
  },
  tenant_id: 'tenant_demo',
};

type Q = Record<string, unknown>;
const qData = (data: unknown): Q => ({ isLoading: false, isError: false, data, refetch: vi.fn() });
const qError = (status: number): Q => ({
  isLoading: false, isError: true, data: undefined,
  error: { response: { status } }, refetch: vi.fn(),
});

function stub(q: Q) {
  vi.spyOn(useApiModule, 'useExecutionFeedback').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('ExecutionFeedbackPage', () => {
  it('(أ) يعرض التلخيص: نسبة الإغلاق % + رقائق by_status', () => {
    stub(qData(SAMPLE));
    render(<ExecutionFeedbackPage />);
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText('نسبة إغلاق الحلقة')).toBeInTheDocument();
    expect(screen.getByText('إجماليّ القرارات')).toBeInTheDocument();
    // رقائق الحالات: حلقة مغلقة + نُفِّذ بلا قياس + يحتاج بيانات معروضة (شارات + رقائق).
    expect(screen.getAllByText('حلقة مغلقة (نُفِّذ ونجح)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('نُفِّذ بلا قياس').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('يحتاج بيانات (غير مُسجَّل)').length).toBeGreaterThanOrEqual(1);
  });

  it('(ب) يعرض صفوف القرارات بشارات حالة الحلقة الملوّنة', () => {
    stub(qData(SAMPLE));
    render(<ExecutionFeedbackPage />);
    expect(screen.getByText('irrigation_plan')).toBeInTheDocument();
    expect(screen.getByText('fertilizer_plan')).toBeInTheDocument();
    expect(screen.getByText('pest_plan')).toBeInTheDocument();
    // شارة closed_ok خضراء (#16a34a).
    const closedBadge = screen.getAllByText('حلقة مغلقة (نُفِّذ ونجح)').find(
      (el) => el.tagName.toLowerCase() === 'span' && el.className.includes('rounded-full'),
    ) as HTMLElement;
    expect(closedBadge).toBeTruthy();
    expect(closedBadge.style.color).toBe('rgb(22, 163, 74)');
  });

  it('(ج) execution_unknown يُعرَض رماديّاً بـnote_ar لا «نُفِّذ»/أخضر', () => {
    stub(qData(SAMPLE));
    render(<ExecutionFeedbackPage />);
    // الملاحظة الصادقة معروضة.
    expect(screen.getByText(/لا قيد في سجلّ التنفيذ — لا يُفترَض مُنفَّذاً/)).toBeInTheDocument();
    // execution_outcome=null ⇒ «غير مُسجَّل» (لا «نُفِّذ» مُختلَق).
    expect(screen.getByText('غير مُسجَّل')).toBeInTheDocument();
    // شارة الحالة رماديّة (#9ca3af) لا خضراء (#16a34a).
    const unknownBadge = screen.getAllByText('يحتاج بيانات (غير مُسجَّل)').find(
      (el) => el.tagName.toLowerCase() === 'span' && el.className.includes('rounded-full'),
    ) as HTMLElement;
    expect(unknownBadge).toBeTruthy();
    expect(unknownBadge.style.color).toBe('rgb(156, 163, 175)');
    expect(unknownBadge.style.color).not.toBe('rgb(22, 163, 74)');
  });

  it('(د) executed_unmeasured كهرمانيّ لا نجاح (outcome_success=null ⇒ «—»)', () => {
    stub(qData(SAMPLE));
    render(<ExecutionFeedbackPage />);
    // شارة executed_unmeasured كهرمانيّة (#d97706).
    const amberBadge = screen.getAllByText('نُفِّذ بلا قياس').find(
      (el) => el.tagName.toLowerCase() === 'span' && el.className.includes('rounded-full'),
    ) as HTMLElement;
    expect(amberBadge).toBeTruthy();
    expect(amberBadge.style.color).toBe('rgb(217, 119, 6)');
    expect(amberBadge.style.color).not.toBe('rgb(22, 163, 74)'); // ليس أخضر/نجاح
    // النتيجة غير المقيسة تُعرَض «—» (في خلايا outcome_success لقرارين بلا قياس).
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('(هـ) closure_rate:null ⇒ «غير محسوبة» لا 0%', () => {
    stub(qData({
      ...SAMPLE,
      closure_rate: null,
      totals: { executed: 0, failed: 0, measured: 0, closed_ok: 0 },
    }));
    render(<ExecutionFeedbackPage />);
    expect(screen.getByText('غير محسوبة')).toBeInTheDocument();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('(و) بانر القراءة فقط + بانر الصدق provenance.note_ar حاضران', () => {
    stub(qData(SAMPLE));
    render(<ExecutionFeedbackPage />);
    expect(screen.getByText(/رصد قراءة فقط — لا إصدار أوامر ولا إعادة تنفيذ/)).toBeInTheDocument();
    // عبارة «حالات الحلقة من سجلّات مُدامة فقط» تظهر في عنوان البانر ونصّ provenance.note_ar معاً.
    expect(screen.getAllByText(/حالات الحلقة من سجلّات مُدامة فقط/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/ولا تُفترَض حالة دون قيد/)).toBeInTheDocument();
  });

  it('(ز) 404 ⇒ إشعار «الميزة غير مُفعَّلة»', () => {
    stub(qError(404));
    render(<ExecutionFeedbackPage />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    expect(screen.getAllByText(/FEATURE_EXECUTION_FEEDBACK/).length).toBeGreaterThanOrEqual(1);
  });

  it('(ح) 503/خطأ آخر ⇒ حالة خطأ صادقة (لا تلفيق)', () => {
    stub(qError(503));
    render(<ExecutionFeedbackPage />);
    // UI2: تعطل التوفّر (503) ⇒ حالة متدهورة صادقة
    expect(screen.getByText('تعمل رصد حلقة التنفيذ في وضع متدهور')).toBeInTheDocument();
  });
});
