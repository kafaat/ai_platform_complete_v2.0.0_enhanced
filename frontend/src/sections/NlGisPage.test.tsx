// اختبارات استعلام GIS باللغة الطبيعيّة — سلوك المكوّن: شريط التفسير (النيّة +
// شرائح الشقوق) + جدول النتائج بالعدد، حالة عدم الدعم (reason_ar)، حالة الحاجة
// للبيانات (note_ar دون جدول مُضلِّل)، مسار 404 (الميزة غير مُفعَّلة)، وبانر القراءة
// فقط الدائم. المحاكاة في الاختبار فقط — نُحاكي queryNlGis مباشرةً (الصفحة تستدعيه
// دون react-query). لا شبكة فعليّة (deterministic).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { NlGisResult } from '../services/api';

// نُحاكي وحدة الـapi: queryNlGis قابل للتحكّم، وasApiError حقيقيّ الدلالة.
const { mockQuery } = vi.hoisted(() => ({ mockQuery: vi.fn() }));
vi.mock('../services/api', () => ({
  queryNlGis: mockQuery,
  asApiError: (e: unknown) => (e ?? {}) as { response?: { status?: number } },
}));

import NlGisPage from './NlGisPage';

const SUPPORTED: NlGisResult = {
  read_only: true,
  intent: 'alert_filter',
  supported: true,
  status: 'ok',
  slots: { crop: 'قمح', region: 'الجوف', alert_type: 'heat_stress' },
  confidence: 0.84,
  api_called: 'alerts⋈fields',
  items: [
    { field_id: 'field_01', name: 'حقل وادي سبأ', crop: 'قمح صلب', gov: 'البيضاء', alert_type: 'heat_stress', severity: 'critical', title_ar: 'إجهاد حراريّ' },
  ],
  count: 1,
  note_ar: null,
  tenant_id: 't1',
};

const UNSUPPORTED: NlGisResult = {
  read_only: true,
  intent: 'unsupported',
  supported: false,
  status: 'unsupported',
  reason_ar: 'لم أتعرّف على طلب مدعوم في هذه الصياغة.',
  items: [],
  count: 0,
  tenant_id: 't1',
};

const NEEDS_DATA: NlGisResult = {
  read_only: true,
  intent: 'ndvi_drop',
  supported: true,
  status: 'needs_data',
  slots: { threshold: 15 },
  confidence: 0.71,
  items: [],
  count: 0,
  note_ar: 'المصدر غير متاح حاليّاً — تعذّر جلب سلاسل NDVI.',
  tenant_id: 't1',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('NlGisPage — البانر الدائم والأمثلة', () => {
  it('بانر القراءة فقط حاضر دائماً (قبل أيّ استعلام)', () => {
    render(<NlGisPage />);
    expect(screen.getByText('قراءة فقط — مبنيّ على بياناتك، لا تنفيذ ولا تعديل.')).toBeInTheDocument();
    expect(screen.getByText('استعلام GIS باللغة الطبيعيّة')).toBeInTheDocument();
    // شرائح المثال الثلاث.
    expect(screen.getByText('اعرض الحقول التي انخفض NDVI فيها أكثر من 15%')).toBeInTheDocument();
  });
});

describe('NlGisPage — نتيجة مدعومة', () => {
  it('يعرض شريط التفسير (النيّة + الثقة + شرائح الشقوق) وجدول النتائج بالعدد', async () => {
    mockQuery.mockResolvedValueOnce(SUPPORTED);
    render(<NlGisPage />);
    fireEvent.change(screen.getByLabelText('استعلام GIS باللغة الطبيعيّة'), {
      target: { value: 'اعرض حقول القمح في الجوف التي لديها تنبيه حرارة' },
    });
    fireEvent.click(screen.getByText('ابحث'));

    // شريط التفسير: نيّة + ثقة.
    await waitFor(() => expect(screen.getByText('تفسير الاستعلام')).toBeInTheDocument());
    expect(screen.getByText('تصفية التنبيهات')).toBeInTheDocument();
    expect(screen.getByText('84٪')).toBeInTheDocument();
    // شرائح الشقوق (slots).
    expect(screen.getByText(/المحصول: قمح/)).toBeInTheDocument();
    expect(screen.getByText(/المنطقة: الجوف/)).toBeInTheDocument();
    // جدول النتائج + العدد + خليّة من العنصر.
    expect(screen.getByText('(1 حقل)')).toBeInTheDocument();
    expect(screen.getByText('حقل وادي سبأ')).toBeInTheDocument();
  });
});

describe('NlGisPage — عدم الدعم', () => {
  it('status=unsupported ⇒ يعرض reason_ar في تنبيه ولا جدول', async () => {
    mockQuery.mockResolvedValueOnce(UNSUPPORTED);
    render(<NlGisPage />);
    fireEvent.change(screen.getByLabelText('استعلام GIS باللغة الطبيعيّة'), {
      target: { value: 'افعل شيئاً غامضاً' },
    });
    fireEvent.click(screen.getByText('ابحث'));

    expect(await screen.findByText('لم أتعرّف على طلب مدعوم في هذه الصياغة.')).toBeInTheDocument();
    // لا جدول نتائج (لا عدّاد حقول).
    expect(screen.queryByText(/حقل\)/)).not.toBeInTheDocument();
  });
});

describe('NlGisPage — الحاجة للبيانات', () => {
  it('status=needs_data ⇒ يعرض note_ar ولا جدول فارغ مُضلِّل', async () => {
    mockQuery.mockResolvedValueOnce(NEEDS_DATA);
    render(<NlGisPage />);
    fireEvent.change(screen.getByLabelText('استعلام GIS باللغة الطبيعيّة'), {
      target: { value: 'اعرض الحقول التي انخفض NDVI فيها أكثر من 15%' },
    });
    fireEvent.click(screen.getByText('ابحث'));

    expect(await screen.findByText('المصدر غير متاح حاليّاً — تعذّر جلب سلاسل NDVI.')).toBeInTheDocument();
    // لا جدول نتائج (لا عدّاد حقول) رغم count=0.
    expect(screen.queryByText(/حقل\)/)).not.toBeInTheDocument();
  });
});

describe('NlGisPage — الميزة غير مُفعَّلة (404)', () => {
  it('404 ⇒ رسالة «الميزة غير مُفعَّلة» لا انهيار ولا حالة خطأ', async () => {
    mockQuery.mockRejectedValueOnce({ response: { status: 404 } });
    render(<NlGisPage />);
    fireEvent.change(screen.getByLabelText('استعلام GIS باللغة الطبيعيّة'), {
      target: { value: 'اعرض الحقول التي لم تُروَ منذ 5 أيّام' },
    });
    fireEvent.click(screen.getByText('ابحث'));

    expect(await screen.findByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    // لا حالة خطأ عامّة.
    expect(screen.queryByText('تعذّر تنفيذ الاستعلام')).not.toBeInTheDocument();
  });

  it('خطأ غير 404 (503) ⇒ حالة خطأ صادقة', async () => {
    mockQuery.mockRejectedValueOnce({ response: { status: 503 } });
    render(<NlGisPage />);
    fireEvent.change(screen.getByLabelText('استعلام GIS باللغة الطبيعيّة'), {
      target: { value: 'اعرض الحقول التي لم تُروَ منذ 5 أيّام' },
    });
    fireEvent.click(screen.getByText('ابحث'));

    expect(await screen.findByText('تعذّر تنفيذ الاستعلام')).toBeInTheDocument();
    expect(screen.queryByText(/الميزة غير مُفعَّلة/)).not.toBeInTheDocument();
  });
});
