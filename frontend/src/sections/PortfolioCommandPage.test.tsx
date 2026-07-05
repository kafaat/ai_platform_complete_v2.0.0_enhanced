// اختبارات مركز قيادة المحفظة — سلوك المكوّن: جدول مقارنة الربح×المخاطرة،
// شارة «موصى بها»، ألوان المخاطرة + نسبة التلبية، بانر «توصية فقط»، ومسار 404
// (الميزة غير مُفعَّلة). المحاكاة في الاختبار فقط (لا mock في كود الإنتاج) —
// نُحاكي computePortfolioCommand مباشرةً (الصفحة تستدعيه دون react-query).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import type { PortfolioCommandResult } from '../services/api';

// نُحاكي وحدة الـapi: computePortfolioCommand قابل للتحكّم، وasApiError حقيقيّ الدلالة.
const { mockCompute } = vi.hoisted(() => ({ mockCompute: vi.fn() }));
vi.mock('../services/api', () => ({
  computePortfolioCommand: mockCompute,
  asApiError: (e: unknown) => (e ?? {}) as { response?: { status?: number } },
}));

// الصفحة تقرأ قائمة الحقول الحيّة عبر useFieldOptions (تعدّد الحقول). نُحاكيه بخيار واحد
// ثابت كي لا يجرّ سلسلة react-query/authApi في اختبار سلوكيّ، ونختار الحقل قبل المقارنة
// (زرّ المقارنة صار مشروطاً باختيار حقل حقيقيّ بدل معرّفات تجريبيّة مفبركة).
vi.mock('../hooks/useFieldOptions', () => ({
  useFieldOptions: () => ({
    options: [{ id: 'f-1', name: 'حقل تجريبيّ', crop: 'قمح' }],
    isLoading: false,
    isError: false,
  }),
}));

import PortfolioCommandPage from './PortfolioCommandPage';

// يختار الحقل الأوّل في أوّل صفّ (المُبدِّل الذي يحوي خيار «اختر الحقل») ليُفعِّل زرّ المقارنة.
function selectFirstField() {
  const combos = screen.getAllByRole('combobox');
  const fieldSelect = combos.find((c) => within(c).queryByText('اختر الحقل'));
  if (!fieldSelect) throw new Error('field select not found');
  fireEvent.change(fieldSelect, { target: { value: 'f-1' } });
}

const RESULT: PortfolioCommandResult = {
  recommended_policy: 'أقصى ربح',
  risk_aversion: 1.0,
  calibrated: false,
  warnings_ar: ['مقارنة سياسات استرشاديّة — توصية فقط، لا تنفيذ.'],
  tenant_id: 't1',
  policies: [
    {
      policy: 'أقصى ربح',
      total_expected_margin: 4800,
      total_allocated_m3: 1800,
      total_demand_m3: 2100,
      served_fraction: 0.857,
      risk_score: 0.12, // أخضر (<0.2)
      fields_count: 2,
      protected_count: 1,
      stressed_count: 1,
      unmet_count: 0,
      constraints: [
        { source_id: 'مضخّة-1', kind: 'pump', capacity_m3: 2000, effective_capacity_m3: 1500, throughput_bound: true },
        { source_id: 'بئر-1', kind: 'well', capacity_m3: 1500, effective_capacity_m3: 1500, throughput_bound: false },
      ],
      constraints_bound: ['مضخّة-1'],
      objective_score: 104.4,
      allocation: {
        fields: [], sources: [], total_expected_margin: 4800, total_allocated_m3: 1800,
        protected_fields: [], stressed_fields: [], unmet_fields: [], calibrated: false, warnings_ar: [],
      },
    },
    {
      policy: 'توفير الماء',
      total_expected_margin: 3900,
      total_allocated_m3: 1400,
      total_demand_m3: 1400,
      served_fraction: 0.62,
      risk_score: 0.55, // أحمر (≥0.5)
      fields_count: 2,
      protected_count: 2,
      stressed_count: 0,
      unmet_count: 1,
      constraints: [],
      constraints_bound: [],
      objective_score: 88.2,
      allocation: {
        fields: [], sources: [], total_expected_margin: 3900, total_allocated_m3: 1400,
        protected_fields: [], stressed_fields: [], unmet_fields: [], calibrated: false, warnings_ar: [],
      },
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PortfolioCommandPage — النموذج المبدئيّ', () => {
  it('يعرض العنوان وأزرار الإدخال وبانر «توصية فقط» في الوصف', () => {
    render(<PortfolioCommandPage />);
    expect(screen.getByText('مركز قيادة المحفظة')).toBeInTheDocument();
    expect(screen.getByText('قارن السياسات')).toBeInTheDocument();
    expect(screen.getByText('أضف سياسة')).toBeInTheDocument();
    // السياستان المبدئيّتان مُزروعتان في حقول الإدخال.
    expect(screen.getByDisplayValue('أقصى ربح')).toBeInTheDocument();
    expect(screen.getByDisplayValue('توفير الماء')).toBeInTheDocument();
  });
});

describe('PortfolioCommandPage — النتائج', () => {
  it('يعرض جدول المقارنة بكلّ السياسات + شارة «موصى بها» على الموصى بها', async () => {
    mockCompute.mockResolvedValueOnce(RESULT);
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    await waitFor(() => expect(screen.getByText('موصى بها')).toBeInTheDocument());
    // صفّ لكلّ سياسة في الجدول (أسماء السياسات في الإدخال هي قيم input لا نصّ).
    expect(screen.getByText('أقصى ربح')).toBeInTheDocument();
    expect(screen.getByText('توفير الماء')).toBeInTheDocument();
    // الهامش الإجماليّ + درجة الهدف.
    expect(screen.getByText('4800')).toBeInTheDocument();
    expect(screen.getByText('104.4')).toBeInTheDocument();
  });

  it('يعرض درجة المخاطرة بألوانها ونسبة التلبية المئويّة', async () => {
    mockCompute.mockResolvedValueOnce(RESULT);
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    // درجة المخاطرة 0.12 (أخضر) و0.55 (أحمر).
    const green = await screen.findByText('0.12');
    expect(green).toHaveClass('text-emerald-300');
    const red = screen.getByText('0.55');
    expect(red).toHaveClass('text-red-300');
    // نسبة التلبية: 85.7٪ → 86٪ و62٪.
    expect(screen.getByText('86٪')).toBeInTheDocument();
    expect(screen.getByText('62٪')).toBeInTheDocument();
  });

  it('يعرض بانر «توصية فقط» وبانر «غير معايَر» + كلّ warnings_ar', async () => {
    mockCompute.mockResolvedValueOnce(RESULT);
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    expect(await screen.findByText('توصية فقط — لا تنفيذ ولا حجز ماء.')).toBeInTheDocument();
    // بانر عدم المعايرة (نصّ البانر المحدّد — يميّزه عن «غير معايَرة» في الوصف).
    expect(screen.getByText(/تقديريّ غير معايَر — قيم لا قاطعة/)).toBeInTheDocument();
    expect(screen.getByText(/مقارنة سياسات استرشاديّة/)).toBeInTheDocument();
  });

  it('لوحة القيود تُبرِز المصدر المُقيَّد بتدفّقه (الفعليّة مقابل الاسميّة)', async () => {
    mockCompute.mockResolvedValueOnce(RESULT);
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    // المضخّة المُقيَّدة بتدفّقها تظهر؛ السعة الفعليّة 1500 مقابل 2000.
    expect(await screen.findByText('مضخّة-1')).toBeInTheDocument();
    expect(screen.getByText('المضخّة قيَّدها تدفّقها')).toBeInTheDocument();
    expect(screen.getByText('1500')).toBeInTheDocument();
  });
});

describe('PortfolioCommandPage — الميزة غير مُفعَّلة (404)', () => {
  it('404 ⇒ رسالة «الميزة غير مُفعَّلة» لا انهيار ولا حالة خطأ', async () => {
    mockCompute.mockRejectedValueOnce({ response: { status: 404 } });
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    expect(await screen.findByText('الميزة غير مُفعَّلة')).toBeInTheDocument();
    // لا حالة خطأ عامّة.
    expect(screen.queryByText('تعذّرت مقارنة السياسات')).not.toBeInTheDocument();
  });

  it('خطأ غير 404 (503) ⇒ حالة خطأ صادقة', async () => {
    mockCompute.mockRejectedValueOnce({ response: { status: 503 } });
    render(<PortfolioCommandPage />);
    selectFirstField();
    fireEvent.click(screen.getByText('قارن السياسات'));

    expect(await screen.findByText('تعذّرت مقارنة السياسات')).toBeInTheDocument();
    expect(screen.queryByText('الميزة غير مُفعَّلة')).not.toBeInTheDocument();
  });
});
