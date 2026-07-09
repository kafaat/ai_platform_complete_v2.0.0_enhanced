// اختبارات ثقة القرار الموحَّدة — سلوك المكوّن عبر مُسرَحة hook useDecisionConfidence
// + تثبيت «الحقل النشط» المشترك (عزل تامّ): (أ) نسبة الثقة + شارة المستوى + تفصيل
// المكوّنات؛ (ب) مكوّن available:false يُعرَض رماديّاً «needs_data» لا 0/مساهم؛
// (ج) confidence:null/level:'insufficient' ⇒ «غير كافية» رماديّاً لا 0%؛
// (د) بانر provenance + ملاحظة عرض فقط؛ (هـ) 404 ⇒ «الميزة غير مُفعَّلة»؛
// (و) 503 ⇒ خطأ صادق. المحاكاة في الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// نُثبّت «الحقل النشط» المشترك — حقلٌ مُختار دائماً (كي يُفعَّل الاستعلام).
const selectedField = {
  options: [{ id: 'field_01', name: 'حقل القمح' }],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  fieldId: 'field_01',
  field: { id: 'field_01', name: 'حقل القمح' },
  setFieldId: vi.fn(),
};
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => selectedField,
}));

import * as useApiModule from '../hooks/useApi';
import type { DecisionConfidenceResult } from '../services/api';
import DecisionConfidencePage from './DecisionConfidencePage';

// نتيجة كاملة نموذجيّة مطابقة لعقد GET /api/v1/fields/{id}/decision-confidence.
const SAMPLE: DecisionConfidenceResult = {
  generated_at: '2026-06-21T00:00:00+00:00',
  confidence: 0.62,
  level: 'medium',
  level_ar: 'متوسّطة',
  components: [
    { source: 'sensor',    label_ar: 'ثقة الحسّاس',     weight: 0.30, value: 0.8,  available: true,  detail_ar: 'ثقة أسطول 2/3 جهاز' },
    { source: 'evidence',  label_ar: 'الدليل الميدانيّ', weight: 0.25, value: 0.6,  available: true,  detail_ar: 'مدعوم أوّليّاً (3/30 قياس)' },
    { source: 'satellite', label_ar: 'نضارة الاستشعار',  weight: 0.25, value: null, available: false, detail_ar: 'لا قياس NDVI مُدام لهذا الحقل (needs_data)' },
    { source: 'weather',   label_ar: 'ثقة الطقس',       weight: 0.20, value: null, available: false, detail_ar: 'ثقة طقس per-field غير مُدامة هنا (needs_data)' },
  ],
  present_count: 2,
  missing: ['satellite', 'weather'],
  provenance: {
    calibrated: 'not_applicable',
    note_ar: 'ثقة القرار تركيبة موزونة شفّافة على المصادر المتوفّرة فقط — عرض فقط لا يُعدّل القرار.',
  },
  field_id: 'field_01',
  tenant_id: 'tenant_demo',
};

type Q = Record<string, unknown>;
const qData = (data: unknown): Q => ({ isLoading: false, isError: false, data, refetch: vi.fn() });
const qError = (status: number): Q => ({
  isLoading: false, isError: true, data: undefined,
  error: { response: { status } }, refetch: vi.fn(),
});

function stub(q: Q) {
  vi.spyOn(useApiModule, 'useDecisionConfidence').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('DecisionConfidencePage', () => {
  it('(أ) يعرض نسبة الثقة المدموجة + شارة المستوى + تفصيل المكوّنات', () => {
    stub(qData(SAMPLE));
    render(<DecisionConfidencePage />);
    // النسبة المدموجة 62% (كبيرة في الرأس).
    expect(screen.getByText('62%')).toBeInTheDocument();
    // شارة المستوى العربيّة «متوسّطة».
    expect(screen.getByText('متوسّطة')).toBeInTheDocument();
    // تفصيل المكوّنات: التسميات العربيّة + نسب المتوفّر.
    expect(screen.getByText('ثقة الحسّاس')).toBeInTheDocument();
    expect(screen.getByText('الدليل الميدانيّ')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('60%')).toBeInTheDocument();
    // الأوزان معروضة («وزن ٣٠٪»).
    expect(screen.getByText('وزن 30٪')).toBeInTheDocument();
    // عدد المصادر المُستخدَمة 2/4.
    expect(screen.getByText('2/4')).toBeInTheDocument();
  });

  it('(ب) مكوّن available:false يُعرَض رماديّاً «needs_data» لا 0/مساهم', () => {
    stub(qData(SAMPLE));
    render(<DecisionConfidencePage />);
    // المصدر غير المتوفّر يُعرَض بتفصيله needs_data، لا 0%.
    expect(screen.getByText('نضارة الاستشعار')).toBeInTheDocument();
    expect(screen.getByText(/لا قياس NDVI مُدام لهذا الحقل \(needs_data\)/)).toBeInTheDocument();
    // وسم «غير متوفّر (needs_data)» حاضر للمكوّنات الغائبة.
    expect(screen.getAllByText(/غير متوفّر \(needs_data\)/).length).toBeGreaterThanOrEqual(1);
    // لا تُعرَض «0%» لأيّ مكوّن غائب (لا مساهم بصفر).
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('(ج) confidence:null/level:insufficient ⇒ «غير كافية» رماديّاً لا 0%', () => {
    stub(qData({
      ...SAMPLE,
      confidence: null,
      level: 'insufficient',
      level_ar: 'غير كافية',
      present_count: 0,
      components: SAMPLE.components.map((c) => ({ ...c, value: null, available: false })),
      missing: ['sensor', 'evidence', 'satellite', 'weather'],
    }));
    render(<DecisionConfidencePage />);
    // «غير كافية» معروضة (الرأس + الشارة) لا «0%».
    expect(screen.getAllByText('غير كافية').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    // 0/4 مصادر مُستخدَمة.
    expect(screen.getByText('0/4')).toBeInTheDocument();
  });

  it('(د) يعرض بانر provenance + ملاحظة عرض فقط', () => {
    stub(qData(SAMPLE));
    render(<DecisionConfidencePage />);
    // بانر provenance.note_ar (نصّ المصدر الكامل من العقد).
    expect(screen.getByText(SAMPLE.provenance.note_ar)).toBeInTheDocument();
    // ملاحظة «عرض فقط — لا يُعدّل القرار.» المنفصلة (بالشرطة).
    expect(screen.getByText('عرض فقط — لا يُعدّل القرار.')).toBeInTheDocument();
  });

  it('(هـ) 404 ⇒ إشعار «الميزة غير مُفعَّلة»', () => {
    stub(qError(404));
    render(<DecisionConfidencePage />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    expect(screen.getAllByText(/FEATURE_DECISION_CONFIDENCE/).length).toBeGreaterThanOrEqual(1);
  });

  it('(و) 503/خطأ آخر ⇒ حالة خطأ صادقة (لا تلفيق)', () => {
    stub(qError(503));
    render(<DecisionConfidencePage />);
    // UI2: تعطل التوفّر (503) ⇒ حالة متدهورة صادقة
    expect(screen.getByText('تعمل ثقة القرار الموحَّدة في وضع متدهور')).toBeInTheDocument();
  });
});
