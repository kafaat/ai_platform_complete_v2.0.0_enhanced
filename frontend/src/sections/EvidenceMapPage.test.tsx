// اختبارات خريطة الدليل — سلوك المكوّن عبر مُسرَحة hook useEvidenceMap (عزل تامّ):
// (أ) الأسطورة بالتسميات + العدّ من totals_by_tier؛ (ب) قائمة الحقول بشارات ملوّنة
// وحقل needs_data يُعرَض بوضوح (رماديّ، لا أخضر)؛ (ج) بانر provenance.note_ar؛
// (د) 404 ⇒ «الميزة غير مُفعَّلة»؛ (هـ) 503 ⇒ ErrorState صادقة. react-leaflet
// مُمثَّل بظِلّ خفيف (jsdom لا يصيّر خرائط). المحاكاة في الاختبار فقط.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

// react-leaflet ظِلّ خفيف — نختبر القائمة/الأسطورة/البانر لا الخريطة الفعليّة.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Popup: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
// تفادي side-effect تحميل Leaflet CSS/الأيقونات في jsdom.
vi.mock('../lib/leafletSetup', () => ({}));

import * as useApiModule from '../hooks/useApi';
import type { EvidenceMapResult } from '../services/api';
import EvidenceMapPage from './EvidenceMapPage';

// نتيجة كاملة نموذجيّة مطابقة لعقد GET /api/v1/evidence/map.
const SAMPLE: EvidenceMapResult = {
  generated_at: '2026-06-20T12:00:00+00:00',
  legend: [
    { tier: 'field_verified',    tier_ar: 'مؤكَّد ميدانيّاً', color: 'green' },
    { tier: 'field_preliminary', tier_ar: 'مدعوم (أوّليّ)',   color: 'amber' },
    { tier: 'indicative',        tier_ar: 'إرشاديّ',          color: 'blue'  },
    { tier: 'needs_data',        tier_ar: 'يحتاج بيانات',     color: 'gray'  },
  ],
  fields: [
    {
      field_id: 'field_01', name: 'حقل وادي سبأ', crop: 'قمح صلب', gov: 'البيضاء',
      lat: 15.05, lon: 45.55, has_coords: true,
      decisions: 4, outcomes: 2, successes: 1, success_rate: 0.5,
      samples_to_verified: 28, last_outcome_at: '2026-06-10T00:00:00+00:00',
      tier: 'field_preliminary', tier_ar: 'مدعوم (أوّليّ)', color: 'amber',
    },
    {
      field_id: 'field_02', name: 'حقل بلا موقع', crop: 'ذرة', gov: 'مأرب',
      lat: null, lon: null, has_coords: false,
      decisions: 0, outcomes: 0, successes: 0, success_rate: null,
      samples_to_verified: 30, last_outcome_at: null,
      tier: 'needs_data', tier_ar: 'يحتاج بيانات', color: 'gray',
    },
  ],
  totals_by_tier: { field_verified: 0, field_preliminary: 1, indicative: 0, needs_data: 1 },
  field_count: 2,
  plottable_count: 1,
  verified_threshold: 30,
  provenance: {
    calibrated: 'not_applicable',
    note_ar: 'مستوى الدليل من القرارات/القياسات المُدامة فقط؛ عتبة التحقّق الميدانيّ (30) تقديريّة.',
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
  vi.spyOn(useApiModule, 'useEvidenceMap').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('EvidenceMapPage', () => {
  it('(أ) يعرض الأسطورة بتسميات الفئات والعدّ من totals_by_tier', () => {
    stub(qData(SAMPLE));
    render(<EvidenceMapPage />);
    expect(screen.getByText('مفتاح مستوى الدليل')).toBeInTheDocument();
    expect(screen.getByText('مؤكَّد ميدانيّاً')).toBeInTheDocument();
    expect(screen.getByText('إرشاديّ')).toBeInTheDocument();
    // العدّ: field_preliminary=1، needs_data=1 (من totals_by_tier).
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(2);
  });

  it('(ب) يعرض قائمة الحقول بشارات ملوّنة وحقل needs_data بوضوح (رماديّ لا أخضر)', () => {
    stub(qData(SAMPLE));
    render(<EvidenceMapPage />);
    // اسما الحقلين معروضان (وادي سبأ يظهر في القائمة + نافذة الخريطة المنبثقة).
    expect(screen.getAllByText('حقل وادي سبأ').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('حقل بلا موقع')).toBeInTheDocument();
    // الحقل بلا إحداثيّات موسوم «بلا إحداثيّات» في صفّه (لا يُرسَم على الخريطة).
    // النصّ يظهر في الفقرة التعريفيّة + وسم الصفّ ⇒ نتحقّق من وجود الوسم (title).
    const noCoordsBadge = screen.getAllByText('بلا إحداثيّات').find(
      (el) => el.getAttribute('title')?.includes('بلا إحداثيّات'),
    );
    expect(noCoordsBadge).toBeTruthy();
    // شارة needs_data بلونها الرماديّ (#9ca3af) لا الأخضر (#16a34a) — صدق «لا دليل بعد».
    const needsBadge = screen.getAllByText('يحتاج بيانات').find(
      (el) => el.tagName.toLowerCase() === 'span',
    ) as HTMLElement;
    expect(needsBadge).toBeTruthy();
    expect(needsBadge.style.color).not.toBe('rgb(22, 163, 74)'); // ليس أخضر
  });

  it('(ج) يعرض بانر الصدق provenance.note_ar', () => {
    stub(qData(SAMPLE));
    render(<EvidenceMapPage />);
    expect(screen.getByText(/عتبة التحقّق الميدانيّ \(30\) تقديريّة/)).toBeInTheDocument();
  });

  it('(د) 404 ⇒ إشعار «الميزة غير مُفعَّلة»', () => {
    stub(qError(404));
    render(<EvidenceMapPage />);
    expect(screen.getByText(/الميزة غير مُفعَّلة/)).toBeInTheDocument();
    expect(screen.getAllByText(/FEATURE_EVIDENCE_MAP/).length).toBeGreaterThanOrEqual(1);
  });

  it('(هـ) 503/خطأ آخر ⇒ حالة خطأ صادقة (لا تلفيق)', () => {
    stub(qError(503));
    render(<EvidenceMapPage />);
    expect(screen.getByText('تعذّر جلب خريطة الدليل')).toBeInTheDocument();
  });

  it('fields:[] ⇒ «لا حقول» صادقة', () => {
    stub(qData({ ...SAMPLE, fields: [], field_count: 0, plottable_count: 0 }));
    render(<EvidenceMapPage />);
    expect(screen.getByText(/لا حقول مُسجّلة/)).toBeInTheDocument();
  });
});
