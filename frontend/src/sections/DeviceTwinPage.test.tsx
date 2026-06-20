// اختبارات توائم الأجهزة وثقة الحسّاس — سلوك المكوّن عبر مُسرَحة hook useDeviceTwin
// (عزل تامّ): (أ) ترويسة تلخيص الأسطول + رقائق by_level؛ (ب) بطاقات الأجهزة بشارة
// المستوى + نسبة الصحّة + تفصيل العوامل + رقائق الإشارات الغائبة؛ (ج) جهاز
// level:'unknown'/health_score:null يُعرَض «غير محسوبة» رماديّاً لا 0/أخضر؛
// (د) بانر provenance.note_ar؛ (هـ) 404 ⇒ «الميزة غير مُفعَّلة»؛ (و) 503 ⇒ خطأ صادق؛
// (ز) devices:[] ⇒ «لا أجهزة». المحاكاة في الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import * as useApiModule from '../hooks/useApi';
import type { DeviceTwinResult } from '../services/api';
import DeviceTwinPage from './DeviceTwinPage';

// نتيجة كاملة نموذجيّة مطابقة لعقد GET /api/v1/devices/twin.
const SAMPLE: DeviceTwinResult = {
  generated_at: '2026-06-20T12:00:00+00:00',
  devices: [
    {
      device_id: 'dev_01', name: 'محطة طقس وادي سبأ', type: 'weather_station',
      field_id: 'field_01', status: 'online', firmware: '1.4.2',
      age_sec: 600, health_score: 0.86, level: 'healthy', level_ar: 'سليم',
      factors: { freshness: 1.0, battery: 0.6 },
      missing_signals: ['calibration', 'signal'],
      note_ar: 'درجة محسوبة على الإشارات المتوفّرة فقط؛ غائبة: المعايرة، الإشارة.',
    },
    {
      device_id: 'dev_02', name: 'مستشعر بلا بيانات', type: 'soil_probe',
      field_id: null, status: 'unknown', firmware: null,
      age_sec: null, health_score: null, level: 'unknown', level_ar: 'يحتاج بيانات',
      factors: {},
      missing_signals: ['freshness', 'battery', 'calibration', 'signal'],
      note_ar: null,
    },
  ],
  device_count: 2,
  scored_count: 1,
  by_level: { healthy: 1, degraded: 0, stale: 0, offline: 0, poor: 0, unknown: 1 },
  fleet_confidence: 0.86,
  provenance: {
    calibrated: 'not_applicable',
    note_ar: 'ثقة الحسّاس معادلة موزونة شفّافة على الإشارات المتوفّرة فقط.',
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
  vi.spyOn(useApiModule, 'useDeviceTwin').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('DeviceTwinPage', () => {
  it('(أ) يعرض ترويسة تلخيص الأسطول + رقائق by_level', () => {
    stub(qData(SAMPLE));
    render(<DeviceTwinPage />);
    // ثقة الأسطول كنسبة كبيرة (86%) + رقائق المستويات. (86% تظهر مرّتين: الأسطول والجهاز)
    expect(screen.getAllByText('86%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('ثقة الأسطول (متوسّط المُسجَّلين)')).toBeInTheDocument();
    expect(screen.getByText('إجماليّ الأجهزة')).toBeInTheDocument();
    // رقائق المستويات: «سليم» + «يحتاج بيانات» معروضة بعدّها.
    expect(screen.getAllByText('سليم').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('يحتاج بيانات').length).toBeGreaterThanOrEqual(1);
  });

  it('(ب) يعرض بطاقات الأجهزة: شارة المستوى + نسبة الصحّة + العوامل + الإشارات الغائبة', () => {
    stub(qData(SAMPLE));
    render(<DeviceTwinPage />);
    expect(screen.getByText('محطة طقس وادي سبأ')).toBeInTheDocument();
    // نسبة الصحّة 86% للجهاز الأوّل (تظهر أيضاً في ثقة الأسطول).
    expect(screen.getAllByText('86%').length).toBeGreaterThanOrEqual(1);
    // تفصيل العوامل (freshness/battery) معروض كأشرطة (يظهران أيضاً في غائب الجهاز الثاني).
    expect(screen.getAllByText('freshness').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('battery').length).toBeGreaterThanOrEqual(1);
    // رقائق الإشارات الغائبة المُعلَنة (calibration/signal).
    expect(screen.getAllByText('calibration').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('signal').length).toBeGreaterThanOrEqual(1);
    // وسم «غائب:» حاضر.
    expect(screen.getAllByText('غائب:').length).toBeGreaterThanOrEqual(1);
  });

  it('(ج) جهاز unknown/health_score:null يُعرَض «غير محسوبة» رماديّاً لا 0/أخضر', () => {
    stub(qData(SAMPLE));
    render(<DeviceTwinPage />);
    expect(screen.getByText('مستشعر بلا بيانات')).toBeInTheDocument();
    // الدرجة الغائبة تُعرَض «—» لا «0%».
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    // «غير محسوبة» حاضرة (بطاقة الجهاز unknown).
    expect(screen.getAllByText('غير محسوبة').length).toBeGreaterThanOrEqual(1);
    // شارة المستوى «يحتاج بيانات» بلونها الرماديّ (#9ca3af) لا الأخضر (#16a34a).
    const unknownBadge = screen.getAllByText('يحتاج بيانات').find(
      (el) => el.tagName.toLowerCase() === 'span' && el.className.includes('rounded-full'),
    ) as HTMLElement;
    expect(unknownBadge).toBeTruthy();
    expect(unknownBadge.style.color).not.toBe('rgb(22, 163, 74)'); // ليس أخضر
    // «لم يُرسِل بعد» للجهاز الذي age_sec=null.
    expect(screen.getByText(/لم يُرسِل بعد/)).toBeInTheDocument();
  });

  it('(د) يعرض بانر الصدق provenance.note_ar', () => {
    stub(qData(SAMPLE));
    render(<DeviceTwinPage />);
    expect(screen.getAllByText(/معادلة موزونة شفّافة على الإشارات المتوفّرة فقط/).length).toBeGreaterThanOrEqual(1);
    // ملاحظة قراءة فقط حاضرة.
    expect(screen.getByText(/قراءة فقط — لا أوامر تشغيل\/إيقاف/)).toBeInTheDocument();
  });

  it('(هـ) 404 ⇒ إشعار «الميزة غير مُفعَّلة»', () => {
    stub(qError(404));
    render(<DeviceTwinPage />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    expect(screen.getAllByText(/FEATURE_DEVICE_TWIN/).length).toBeGreaterThanOrEqual(1);
  });

  it('(و) 503/خطأ آخر ⇒ حالة خطأ صادقة (لا تلفيق)', () => {
    stub(qError(503));
    render(<DeviceTwinPage />);
    expect(screen.getByText('تعذّر جلب توائم الأجهزة')).toBeInTheDocument();
  });

  it('(ز) devices:[] ⇒ «لا أجهزة» صادقة', () => {
    stub(qData({ ...SAMPLE, devices: [], device_count: 0, scored_count: 0, fleet_confidence: null }));
    render(<DeviceTwinPage />);
    expect(screen.getByText(/لا أجهزة مُسجَّلة/)).toBeInTheDocument();
  });
});
