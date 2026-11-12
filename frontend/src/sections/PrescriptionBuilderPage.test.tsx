// اختبارات صفحة منشئ الوصفات اليدويّة — سلوك المكوّن عبر مُسرَحة hooks
// (useSelectedField + useFieldPrescriptions + useCreatePrescription) وظِلّ خريطة
// Leaflet (jsdom لا يصيّر خريطة حقيقيّة). نغطّي بصدق:
//   (أ) الفراغ: لا وصفات محفوظة ⇒ note_ar/رسالة فراغ صريحة (لا اختراع وصفات).
//   (ب) المعمورة: وصفات محفوظة تظهر في منتقي التصدير + أزرار GeoJSON/CSV.
//   (ج) 503: قائمة الوصفات تُظهر حالة خطأ صادقة.
//   (د) النضج/اليدويّة: شارة alpha + إعلان «يدويّ» حاضران (صدق المنهج).
// المحاكاة في الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// ── ظِلّ react-leaflet / DrawControl / leaflet (jsdom بلا خريطة فعليّة) ──
// ملاحظة: استُبدِل EditControl (react-leaflet-draw — كاسر React 19) بأداة
// maphub/DrawControl المبنيّة على leaflet-draw الخام؛ نُمثّلها بظِلّ خفيف.
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div data-testid="tile" />,
  Polygon: () => <div data-testid="polygon" />,
  FeatureGroup: ({ children }: { children?: ReactNode }) => <div data-testid="fg">{children}</div>,
}));
vi.mock('../components/maphub/DrawControl', () => ({ default: () => <div data-testid="draw" /> }));
vi.mock('leaflet', () => ({ default: { stamp: () => 1 } }));
vi.mock('../lib/leafletSetup', () => ({}));

// ── «الحقل النشط» المشترك: حقل واحد ذو هندسة (فيظهر المُنشئ كاملاً) ──
const selectedField = {
  options: [{ id: 'fld_1', name: 'حقل القمح', geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]] }, lat: 15, lon: 44 }],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  fieldId: 'fld_1',
  field: { id: 'fld_1', name: 'حقل القمح', geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]] }, lat: 15, lon: 44 },
  setFieldId: vi.fn(),
};
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => selectedField,
}));

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import * as useApiModule from '../hooks/useApi';
import type { PrescriptionListResponse, SeasonSummary } from '../services/api';
import PrescriptionBuilderPage from './PrescriptionBuilderPage';

const SEASON: SeasonSummary = {
  season_id: 'season_2026', field_id: 'fld_1', crops: ['wheat'], cultivar: null,
  irrigation_type: null, seed_rate_kg_ha: null, land_leveling_date: null, plowing_date: null,
  sowing_date: '2026-01-01', season_end: null, stages: [], status: 'active', created_at: null,
  target_yield_kg_ha: null, plant_density: null, row_spacing_cm: null, seed_variety_source: null,
  maturity: null, tillage_type: null, actual_yield_kg_ha: null, notes_ar: null,
  sim_yield_kg_ha: null, sim_biomass_kg_ha: null, sim_gdd_total: null, sim_lai_max: null,
  sim_water_mm: null, sim_ran_at: null,
};

// Build the complete react-query result shape through its real observer.
function seasonsResult(data: SeasonSummary[] | undefined, error: Error | null = null): ReturnType<typeof useApiModule.useSeasons> {
  const client = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity, retry: false } } });
  const options = { queryKey: ['season-test'], queryFn: async () => data ?? [], enabled: false };
  const query = client.getQueryCache().build<SeasonSummary[], Error>(client, options);
  query.setState({ data, error, status: error ? 'error' : 'success', fetchStatus: 'idle' });
  return new QueryObserver<SeasonSummary[], Error>(client, options).getCurrentResult();
}

const EMPTY: PrescriptionListResponse = {
  field_id: 'fld_1',
  prescriptions: [],
  total: 0,
  note_ar: 'القاعدة غير مفعّلة (DATABASE_URL) — لا وصفات مُخزَّنة',
};

const FULL: PrescriptionListResponse = {
  field_id: 'fld_1',
  total: 1,
  prescriptions: [
    {
      prescription_id: 'rx_a',
      field_id: 'fld_1',
      name: 'بذار قمح ٢٠٢٦',
      product_type: 'seed',
      zones: [{ geometry: { type: 'Polygon', coordinates: [] }, rate: 450, unit: 'seeds/m2' }],
      created_by: 'u1',
      created_at: '2026-06-22T10:00:00+00:00',
    },
  ],
};

// مُنشئات نتائج الاستعلام/الطفرة (شكل react-query المُستخدَم في المكوّن).
const listResult = (over: Partial<ReturnType<typeof useApiModule.useFieldPrescriptions>>) =>
  ({ isLoading: false, isError: false, data: undefined, error: undefined, ...over }) as never;
const mutResult = () =>
  ({ mutate: vi.fn(), isPending: false, isSuccess: false, isError: false }) as never;

function stubList(over: Partial<ReturnType<typeof useApiModule.useFieldPrescriptions>>) {
  vi.spyOn(useApiModule, 'useFieldPrescriptions').mockReturnValue(listResult(over));
  vi.spyOn(useApiModule, 'useCreatePrescription').mockReturnValue(mutResult());
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.spyOn(useApiModule, 'useSeasons').mockReturnValue(seasonsResult([SEASON]));
});

describe('PrescriptionBuilderPage', () => {
  it('(أ) يعرض شارة النضج alpha وإعلان أنّه يدويّ (صدق المنهج)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText(/يدويّ/)).toBeInTheDocument();
  });

  it('(ب) فراغ صادق: لا وصفات محفوظة ⇒ تُعرَض note_ar (لا اختراع)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/لا وصفات مُخزَّنة/)).toBeInTheDocument();
  });

  it('(ج) معمورة: الوصفة المحفوظة تظهر مع أزرار التصدير GeoJSON/CSV', () => {
    stubList({ data: FULL });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/تصدير GeoJSON/)).toBeInTheDocument();
    expect(screen.getByText(/تصدير CSV/)).toBeInTheDocument();
    // TODO صريح لصيغ المُتحكِّمات (لا ندّعي إنتاجها).
    expect(screen.getByText(/ISOXML/)).toBeInTheDocument();
  });

  it('(د) 503: قائمة الوصفات تعرض حالة خطأ صادقة', () => {
    stubList({ isError: true, error: { response: { status: 503 } } as unknown as Error });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/غير متاحة \(503\)/)).toBeInTheDocument();
  });

  it('(هـ) يعرض أداة الرسم والخريطة (لرسم المناطق يدويّاً)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(screen.getByTestId('draw')).toBeInTheDocument();
  });
});


describe('PrescriptionBuilder season context', () => {
  it('يعرض موسم الحقل الحقيقي ولا يختار موسمًا ضمنيًا', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(useApiModule.useSeasons).toHaveBeenCalledWith('fld_1');
    const season = screen.getByLabelText('الموسم المرتبط بالوصفة');
    expect(season).toHaveValue('');
    fireEvent.change(season, { target: { value: 'season_2026' } });
    expect(season).toHaveValue('season_2026');
    // A season alone is insufficient: still require drawn zones and a name.
    expect(screen.getByRole('button', { name: 'حفظ الوصفة' })).toBeDisabled();
  });

  it('موسم حقل آخر لا يسمح بالحفظ ولا يخفي التصدير', () => {
    stubList({ data: FULL });
    vi.spyOn(useApiModule, 'useSeasons').mockReturnValue(seasonsResult([{ ...SEASON, season_id: 'foreign', field_id: 'other' }]));
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText('لا مواسم لهذا الحقل')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'حفظ الوصفة' })).toBeDisabled();
    expect(screen.getByText(/تصدير GeoJSON/)).toBeInTheDocument();
  });

  it('فشل تحميل المواسم صريح وتبقى الوصفات المحفوظة متاحة', () => {
    stubList({ data: FULL });
    vi.spyOn(useApiModule, 'useSeasons').mockReturnValue(seasonsResult(undefined, new Error('season unavailable')));
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText('تعذّر تحميل المواسم')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'حفظ الوصفة' })).toBeDisabled();
    expect(screen.getByText(/تصدير CSV/)).toBeInTheDocument();
  });

  it('الموسم اختياريّ: خيار «بلا موسم» صريح، والحفظ لا يشترطه، والحمولة تُسقِط season_id الفارغ', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByRole('option', { name: 'بلا موسم' })).toBeInTheDocument();
    const src = readFileSync(join(process.cwd(), 'src/sections/PrescriptionBuilderPage.tsx'), 'utf8');
    const canSave = src.match(/const canSave = ([^;]+);/)?.[1] ?? '';
    expect(canSave).not.toContain('seasonId');
    expect(src).toContain("...(seasonId ? { season_id: seasonId } : {})");
  });

  it('حقل بلا مواسم يقول إنّ الوصفة تُحفَظ بلا موسم', () => {
    stubList({ data: EMPTY });
    vi.spyOn(useApiModule, 'useSeasons').mockReturnValue(seasonsResult([]));
    render(<MemoryRouter><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/تُحفَظ الوصفة بلا موسم/)).toBeInTheDocument();
  });
});
