// اختبارات توأم شبكة الريّ — سلوك المكوّن: النموذج المبدئيّ المزروع + زرّ «افحص
// الجدوى»، بانر الجدوى الكلّيّة (أخضر/أحمر)، حالات المناطق (مُجدية/غير مُجدية/
// غير متحقَّق منها)، عرض reasons_ar + اختناقات + «غير مفحوص» صراحةً، بانر «توصية
// فقط»، ومسار 404 (الميزة غير مُفعَّلة). المحاكاة في الاختبار فقط (لا mock في
// كود الإنتاج) — نُحاكي checkIrrigationNetworkFeasibility مباشرةً (الصفحة تستدعيه
// دون react-query).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { IrrigationNetworkResult } from '../services/api';

// نُحاكي وحدة الـapi: checkIrrigationNetworkFeasibility قابل للتحكّم، وasApiError حقيقيّ الدلالة.
const { mockCheck } = vi.hoisted(() => ({ mockCheck: vi.fn() }));
vi.mock('../services/api', () => ({
  checkIrrigationNetworkFeasibility: mockCheck,
  asApiError: (e: unknown) => (e ?? {}) as { response?: { status?: number } },
}));

import IrrigationNetworkPage from './IrrigationNetworkPage';

const FEASIBLE: IrrigationNetworkResult = {
  zones: [
    {
      zone_id: 'z1', demand_m3: 300, status: 'feasible',
      path: ['z1', 'v1', 'p1', 'w1'], bottlenecks: [], unchecked: [],
    },
  ],
  wells: [{ well_id: 'w1', capacity_m3: 1000, load_m3: 300, over_capacity: false }],
  overall_feasible: true,
  zone_count: 1,
  feasible_count: 1,
  calibrated: 'not_applicable',
  warnings_ar: ['فحص جدوى شبكة الريّ — توصية فقط، لا تنفيذ ولا فتح صمّامات.'],
  tenant_id: 't1',
};

const INFEASIBLE: IrrigationNetworkResult = {
  zones: [
    {
      zone_id: 'z1', demand_m3: 1200, status: 'infeasible',
      path: ['z1', 'v1', 'p1', 'w1'],
      reasons_ar: ['عجز ماء عند البئر w1: الطلب 1200 يتجاوز السعة 1000.'],
      bottlenecks: ['w1'], unchecked: [],
    },
  ],
  wells: [{ well_id: 'w1', capacity_m3: 1000, load_m3: 1200, over_capacity: true }],
  overall_feasible: false,
  zone_count: 1,
  feasible_count: 0,
  calibrated: 'not_applicable',
  warnings_ar: ['فحص جدوى شبكة الريّ — توصية فقط، لا تنفيذ ولا فتح صمّامات.'],
  tenant_id: 't1',
};

const UNVERIFIED: IrrigationNetworkResult = {
  zones: [
    {
      zone_id: 'z1', demand_m3: 300, status: 'feasible_unverified',
      path: ['z1', 'v1', 'p1', 'w1'],
      bottlenecks: [], unchecked: ['throughput:v1', 'pressure:p1'],
    },
  ],
  wells: [{ well_id: 'w1', capacity_m3: 1000, load_m3: 300, over_capacity: false }],
  overall_feasible: true,
  zone_count: 1,
  feasible_count: 1,
  calibrated: 'not_applicable',
  warnings_ar: ['فحص جدوى شبكة الريّ — توصية فقط، لا تنفيذ ولا فتح صمّامات.'],
  tenant_id: 't1',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('IrrigationNetworkPage — النموذج المبدئيّ', () => {
  it('يعرض العنوان والشبكة المزروعة وزرّ «افحص الجدوى»', () => {
    render(<IrrigationNetworkPage />);
    expect(screen.getByText('توأم شبكة الريّ')).toBeInTheDocument();
    expect(screen.getByText('افحص الجدوى')).toBeInTheDocument();
    // العُقد المبدئيّة مزروعة (المعرّفات في حقول الإدخال؛ تظهر أيضاً في محدِّدات الحوافّ).
    expect(screen.getAllByDisplayValue('w1').length).toBeGreaterThan(0);
    expect(screen.getAllByDisplayValue('z1').length).toBeGreaterThan(0);
    expect(screen.getByText('أضف عُقدة')).toBeInTheDocument();
    expect(screen.getByText('أضف حافّة')).toBeInTheDocument();
  });
});

describe('IrrigationNetworkPage — نتيجة مُجدية', () => {
  it('نتيجة مُجدية ⇒ بانر كلّيّ أخضر + حالة المنطقة مُجدية + بانر «توصية فقط»', async () => {
    mockCheck.mockResolvedValueOnce(FEASIBLE);
    render(<IrrigationNetworkPage />);
    fireEvent.click(screen.getByText('افحص الجدوى'));

    expect(await screen.findByText('الشبكة مُجدية للتنفيذ')).toBeInTheDocument();
    expect(screen.getByText('1 من 1 منطقة مُجدية')).toBeInTheDocument();
    expect(screen.getByText('مُجدية')).toBeInTheDocument();
    // بانر «توصية فقط» حاضر دائماً مع النتائج (يظهر النصّ في الوصف والبانر معاً).
    expect(screen.getAllByText('توصية فقط — لا تنفيذ ولا فتح صمّامات.').length).toBeGreaterThan(0);
  });
});

describe('IrrigationNetworkPage — نتيجة غير مُجدية', () => {
  it('نتيجة غير مُجدية ⇒ بانر كلّيّ أحمر + reasons_ar + شريحة اختناق', async () => {
    mockCheck.mockResolvedValueOnce(INFEASIBLE);
    render(<IrrigationNetworkPage />);
    fireEvent.click(screen.getByText('افحص الجدوى'));

    expect(await screen.findByText('الشبكة غير مُجدية للتنفيذ')).toBeInTheDocument();
    expect(screen.getByText('غير مُجدية')).toBeInTheDocument();
    // سبب العجز يُعرَض حرفيّاً.
    expect(screen.getByText(/عجز ماء عند البئر w1/)).toBeInTheDocument();
    // شريحة الاختناق + علامة تجاوز السعة في لوحة الآبار.
    expect(screen.getByText('اختناقات:')).toBeInTheDocument();
    expect(screen.getByText('تجاوز السعة')).toBeInTheDocument();
  });
});

describe('IrrigationNetworkPage — مُجدية غير متحقَّق منها (صدق)', () => {
  it('feasible_unverified ⇒ حالة كهرمانيّة + شرائح «غير مفحوص» (ليست مرور نظيف)', async () => {
    mockCheck.mockResolvedValueOnce(UNVERIFIED);
    render(<IrrigationNetworkPage />);
    fireEvent.click(screen.getByText('افحص الجدوى'));

    expect(await screen.findByText('مُجدية (غير متحقَّق منها)')).toBeInTheDocument();
    // القيود غير المفحوصة معروضة صراحةً — لا تُفترَض ناجحة.
    expect(screen.getByText('غير مفحوص:')).toBeInTheDocument();
    expect(screen.getByText('throughput:v1')).toBeInTheDocument();
    expect(screen.getByText('pressure:p1')).toBeInTheDocument();
    // لا تُعرَض كـ«مُجدية» نظيفة (تلك الحالة لها وسمها المميّز).
    expect(screen.queryByText('مُجدية')).not.toBeInTheDocument();
  });
});

describe('IrrigationNetworkPage — الميزة غير مُفعَّلة (404)', () => {
  it('404 ⇒ رسالة «الميزة غير مُفعَّلة» لا انهيار ولا حالة خطأ', async () => {
    mockCheck.mockRejectedValueOnce({ response: { status: 404 } });
    render(<IrrigationNetworkPage />);
    fireEvent.click(screen.getByText('افحص الجدوى'));

    expect(await screen.findByText('الميزة غير مُفعَّلة')).toBeInTheDocument();
    expect(screen.queryByText('تعذّر فحص جدوى الشبكة')).not.toBeInTheDocument();
  });

  it('خطأ غير 404 (503) ⇒ حالة خطأ صادقة', async () => {
    mockCheck.mockRejectedValueOnce({ response: { status: 503 } });
    render(<IrrigationNetworkPage />);
    fireEvent.click(screen.getByText('افحص الجدوى'));

    expect(await screen.findByText('تعذّر فحص جدوى الشبكة')).toBeInTheDocument();
    expect(screen.queryByText('الميزة غير مُفعَّلة')).not.toBeInTheDocument();
  });
});
