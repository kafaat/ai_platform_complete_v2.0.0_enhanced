// اختبارات سلوكيّة لصفحة ترقيم المواسم (تُصيّر المكوّن، لا نصّ المصدر):
//   UI-W3: إنشاء الحقل من مسار الترقيم يُرسِل مفتاح التكرار الذي أنتجه AddFieldWithMap
//          ترويسةَ Idempotency-Key (لا يسقط عند إعادة بناء الحمولة).
//   UI-W4: الاستئناف بعد إعادة التحميل يعيد جلب تفاصيل الموسم المحفوظة خادميّاً
//          (حصاد/أحداث/تكاليف/دقّة البذار) بدل عرضها غائبةً.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';

const captured = vi.hoisted(() => ({ onSave: null as null | ((d: unknown) => Promise<void>) }));
const post = vi.hoisted(() => vi.fn());
const season = vi.hoisted(() => ({
  listSeasons: vi.fn(),
  getSeasonDetail: vi.fn(),
}));

vi.mock('../components/AddFieldWithMap', () => ({
  default: ({ onSave }: { onSave: (d: unknown) => Promise<void> }) => {
    captured.onSave = onSave;
    return <section aria-label="draw-field" />;
  },
}));
vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>();
  return { ...real, kongApi: { ...real.kongApi, post } };
});
vi.mock('../services/api/season', async (orig) => {
  const real = await orig<typeof import('../services/api/season')>();
  return { ...real, listSeasons: season.listSeasons, getSeasonDetail: season.getSeasonDetail };
});

import SeasonRecordEntryPage from './SeasonRecordEntryPage';

const DRAFT_KEY = 'sahool-season-draft-v1';

beforeEach(() => {
  cleanup();
  captured.onSave = null;
  post.mockReset();
  season.listSeasons.mockReset().mockResolvedValue({ seasons: [] });
  season.getSeasonDetail.mockReset();
  localStorage.clear();
});

describe('UI-W3: season-entry field creation keeps the idempotency key', () => {
  it('sends the AddFieldWithMap idempotency_key as the Idempotency-Key header', async () => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ draftKey: 'season-k', fieldId: '', fieldName: '', phase: 'draw' }));
    post.mockResolvedValue({ data: { field_id: 'f-new' } });
    render(<SeasonRecordEntryPage />);
    await screen.findByRole('region', { name: 'draw-field' });
    await act(async () => {
      await captured.onSave!({
        name: 'حقل الدفتر', manager: 'م', crop: 'wheat', soil_type: 'loam', area_ha: 1,
        geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.1, 15], [44.1, 15.1], [44, 15]]] },
        idempotency_key: 'field-create-key-7',
      });
    });
    expect(post).toHaveBeenCalledTimes(1);
    const [url, body, config] = post.mock.calls[0];
    expect(url).toBe('/api/v1/fields');
    expect(body).not.toHaveProperty('idempotency_key');
    expect(config).toEqual({ headers: { 'Idempotency-Key': 'field-create-key-7' } });
  });
});

describe('UI-W4: resume refetches the saved season details', () => {
  it('review after reload shows the server-saved harvest, events, costs and day-precision eligibility', async () => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      draftKey: 'season-k', fieldId: 'f-1', fieldName: 'حقل الدفتر', seasonId: 's-1', phase: 'review',
      observedFrom: '2022-10-01', observedTo: '2023-06-01', varietyName: 'قمح', sowingDate: '2022-11-01',
    }));
    season.getSeasonDetail.mockResolvedValue({
      season: { id: 's-1' },
      crop: { variety_name: 'قمح', sowing_date: '2022-11-01', sowing_precision: 'month', seed_rate_kg_ha: 120 },
      events: [
        { event_type: 'irrigation', event_date: '2022-12-01', low_confidence: false },
        { event_type: 'tillage', event_date: '2022-10-15', low_confidence: true },
      ],
      harvest: { harvest_date: '2023-05-20', harvest_precision: 'day', yield_kg_ha: 3200 },
      costs: [{ item_label: 'ديزل', amount: 5000, currency: 'YER' }],
      calibration_eligible: false,
    });
    render(<SeasonRecordEntryPage />);
    await waitFor(() => expect(season.getSeasonDetail).toHaveBeenCalledWith('s-1'));
    expect(await screen.findByText('2023-05-20 · 3200 kg/ha')).toBeInTheDocument();
    expect(screen.getByText('2 حدثاً')).toBeInTheDocument();
    expect(screen.getByText('1 بنداً')).toBeInTheDocument();
    expect(screen.getByText('120 kg/ha')).toBeInTheDocument();
    // دقّة البذار المحفوظة «شهر» لا الافتراضيّ «يوم» ⇒ لا ادّعاء أهليّة معايرة.
    expect(screen.getByText(/غير مؤهَّل للمعايرة/)).toBeInTheDocument();
  });

  it('a failed detail refetch is reported instead of silently showing the details as absent', async () => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      draftKey: 'season-k', fieldId: 'f-1', fieldName: 'حقل الدفتر', seasonId: 's-1', phase: 'review',
    }));
    season.getSeasonDetail.mockRejectedValue(Object.assign(new Error('x'), { response: { status: 503 } }));
    render(<SeasonRecordEntryPage />);
    expect(await screen.findByText(/تعذّر استعادة ما حُفِظ/)).toBeInTheDocument();
  });
});
