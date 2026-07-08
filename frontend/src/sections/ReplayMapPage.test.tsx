// اختبارات إعادة تشغيل الموسم — سلوك المكوّن عبر مُسرَحة hook useAgronomicReplay
// وuseSelectedField (عزل تامّ، لا شبكة):
// (أ) أسطورة المسارات بالعدّ (ومسار فارغ «0 — لا أحداث»)؛ (ب) أحداث على الخطّ +
// قائمة الأحداث؛ (ج) المنزلق يُرشّح (تحريكه للبداية ⇒ أحداث أقلّ)؛ (د) span=null/
// event_count=0 ⇒ حالة فارغة صادقة (لا خطّ زمنيّ مخترَع)؛ (هـ) 404 ⇒ «الميزة غير
// مُفعَّلة»؛ (و) 503/خطأ آخر ⇒ ErrorState صادقة. حتميّ (بلا توقيت/عشوائيّة).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

import * as useApiModule from '../hooks/useApi';
import * as selectedFieldModule from '../hooks/useSelectedField';
import type { AgronomicReplayResult } from '../services/api';
import ReplayMapPage from './ReplayMapPage';

// نتيجة كاملة نموذجيّة مطابقة لعقد GET /api/v1/fields/{id}/agronomic-replay.
const SAMPLE: AgronomicReplayResult = {
  field_id: 'field_01',
  generated_at: '2026-06-20T12:00:00+00:00',
  tracks: [
    { track: 'ndvi', track_ar: 'مؤشّر NDVI' },
    { track: 'weather', track_ar: 'طقس' },
    { track: 'irrigation', track_ar: 'ريّ' },
    { track: 'decision', track_ar: 'قرار' },
    { track: 'outcome', track_ar: 'نتيجة ميدانيّة' },
  ],
  events: [
    { date: '2026-02-15T00:00:00', track: 'decision', track_ar: 'قرار', label_ar: 'خطّة ريّ', value: 0.8, ref_id: 'dec_1' },
    { date: '2026-03-01', track: 'ndvi', track_ar: 'مؤشّر NDVI', label_ar: 'NDVI 0.62', value: 0.62, ref_id: 'field_01' },
    { date: '2026-04-10', track: 'outcome', track_ar: 'نتيجة ميدانيّة', label_ar: 'حصاد ناجح', value: true, ref_id: 'out_1' },
  ],
  counts_by_track: { ndvi: 1, weather: 0, irrigation: 0, decision: 1, outcome: 1 },
  event_count: 3,
  span: { start: '2026-02-15', end: '2026-04-10' },
  provenance: {
    calibrated: 'not_applicable',
    note_ar: 'خطّ زمنيّ من سجلّات مُدامة فقط — لا تاريخ مخترَع.',
  },
  tenant_id: 'tenant_demo',
};

type Q = Record<string, unknown>;
const qData = (data: unknown): Q => ({ isLoading: false, isError: false, data, refetch: vi.fn() });
const qError = (status: number): Q => ({
  isLoading: false, isError: true, data: undefined,
  error: { response: { status } }, refetch: vi.fn(),
});

// مُسرَحة الحقل النشط: حقل مُختار ثابت (field_01) + خيار واحد.
function stubField(fieldId = 'field_01') {
  vi.spyOn(selectedFieldModule, 'useSelectedField').mockReturnValue({
    options: [{ id: 'field_01', name: 'حقل وادي سبأ' }],
    fieldId,
    field: { id: 'field_01', name: 'حقل وادي سبأ' },
    setFieldId: vi.fn(),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as never);
}

function stubReplay(q: Q) {
  vi.spyOn(useApiModule, 'useAgronomicReplay').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  stubField();
});

describe('ReplayMapPage', () => {
  it('(أ) يعرض أسطورة المسارات بالعدّ ومسارات فارغة «0 — لا أحداث»', () => {
    stubReplay(qData(SAMPLE));
    render(<ReplayMapPage />);
    expect(screen.getByText('المسارات')).toBeInTheDocument();
    // المسارات الخمسة معروضة بتسمياتها العربيّة (تظهر أيضاً في صفوف الخطّ الزمنيّ).
    expect(screen.getAllByText('مؤشّر NDVI').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('طقس').length).toBeGreaterThanOrEqual(1);
    // طقس وريّ بعدّ 0 ⇒ تُعرَض «0 — لا أحداث» (مسارات فارغة بصدق، عدّتان على الأقلّ).
    expect(screen.getAllByText('0 — لا أحداث').length).toBeGreaterThanOrEqual(2);
  });

  it('(ب) يعرض الأحداث على الخطّ الزمنيّ وفي قائمة الأحداث', async () => {
    stubReplay(qData(SAMPLE));
    render(<ReplayMapPage />);
    // عند فتح الصفحة المنزلق عند النهاية (1) ⇒ كلّ الأحداث الثلاثة معروضة.
    await waitFor(() => expect(screen.getByText('الأحداث المعروضة (3)')).toBeInTheDocument());
    expect(screen.getByText('خطّة ريّ')).toBeInTheDocument();
    expect(screen.getByText('NDVI 0.62')).toBeInTheDocument();
    expect(screen.getByText('حصاد ناجح')).toBeInTheDocument();
  });

  it('(ج) المنزلق يُرشّح الأحداث (تحريكه للبداية ⇒ أحداث أقلّ)', async () => {
    stubReplay(qData(SAMPLE));
    render(<ReplayMapPage />);
    // انتظار ظهور لوحة الأحداث الكاملة (يُشير لاكتمال عرض hasTimeline + shownEvents).
    await waitFor(() => expect(screen.getByText('الأحداث المعروضة (3)')).toBeInTheDocument());
    const slider = screen.getByLabelText('منزلق إعادة التشغيل الزمنيّ');
    // ابدأ بكلّ الأحداث (3)، ثمّ حرّك المنزلق للبداية (0) ⇒ أوّل حدث فقط (decision).
    fireEvent.change(slider, { target: { value: '0' } });
    expect(screen.getByText('الأحداث المعروضة (1)')).toBeInTheDocument();
    // الحدث المتأخّر (الحصاد) لم يَعُد في القائمة — نتحقّق ضمن قائمة الأحداث تحديداً.
    const list = screen.getByText('الأحداث المعروضة (1)').parentElement as HTMLElement;
    expect(within(list).queryByText('حصاد ناجح')).toBeNull();
    expect(within(list).getByText('خطّة ريّ')).toBeInTheDocument();
  });

  it('(د) span=null / event_count=0 ⇒ حالة فارغة صادقة لا خطّ زمنيّ مخترَع', () => {
    stubReplay(qData({
      ...SAMPLE,
      events: [],
      counts_by_track: { ndvi: 0, weather: 0, irrigation: 0, decision: 0, outcome: 0 },
      event_count: 0,
      span: null,
    }));
    render(<ReplayMapPage />);
    expect(screen.getByText('لا أحداث مُدامة لهذا الحقل بعد')).toBeInTheDocument();
    // لا منزلق ولا قائمة أحداث مفبركة.
    expect(screen.queryByLabelText('منزلق إعادة التشغيل الزمنيّ')).toBeNull();
  });

  it('(هـ) 404 ⇒ إشعار «الميزة غير مُفعَّلة (FEATURE_REPLAY_MAP)»', () => {
    stubReplay(qError(404));
    render(<ReplayMapPage />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    expect(screen.getAllByText(/FEATURE_REPLAY_MAP/).length).toBeGreaterThanOrEqual(1);
  });

  it('(و) 503/خطأ آخر ⇒ حالة خطأ صادقة (لا تلفيق)', () => {
    stubReplay(qError(503));
    render(<ReplayMapPage />);
    // UI2: تعطل التوفّر (503) يُعرَض حالةً متدهورة صادقة (AdvancedServiceState→DegradedState)
    expect(screen.getByText('تعمل إعادة تشغيل الموسم في وضع متدهور')).toBeInTheDocument();
  });
});
