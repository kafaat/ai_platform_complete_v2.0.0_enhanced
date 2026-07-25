// اختبارات صفحة منشئ الوصفات اليدويّة — سلوك المكوّن عبر مُسرَحة hooks
// (useSelectedField + useFieldPrescriptions + useCreatePrescription) وظِلّ خريطة
// Leaflet (jsdom لا يصيّر خريطة حقيقيّة). نغطّي بصدق:
//   (أ) الفراغ: لا وصفات محفوظة ⇒ note_ar/رسالة فراغ صريحة (لا اختراع وصفات).
//   (ب) المعمورة: وصفات محفوظة تظهر في منتقي التصدير + أزرار GeoJSON/CSV.
//   (ج) 503: قائمة الوصفات تُظهر حالة خطأ صادقة.
//   (د) النضج/اليدويّة: شارة alpha + إعلان «يدويّ» حاضران (صدق المنهج).
// المحاكاة في الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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

import * as useApiModule from '../hooks/useApi';
import type { PrescriptionListResponse } from '../services/api';
import PrescriptionBuilderPage from './PrescriptionBuilderPage';

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
const routerFuture = { v7_startTransition: true, v7_relativeSplatPath: true } as const;

function stubList(over: Partial<ReturnType<typeof useApiModule.useFieldPrescriptions>>) {
  vi.spyOn(useApiModule, 'useFieldPrescriptions').mockReturnValue(listResult(over));
  vi.spyOn(useApiModule, 'useCreatePrescription').mockReturnValue(mutResult());
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('PrescriptionBuilderPage', () => {
  it('(أ) يعرض شارة النضج alpha وإعلان أنّه يدويّ (صدق المنهج)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter future={routerFuture}><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText(/يدويّ/)).toBeInTheDocument();
  });

  it('(ب) فراغ صادق: لا وصفات محفوظة ⇒ تُعرَض note_ar (لا اختراع)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter future={routerFuture}><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/لا وصفات مُخزَّنة/)).toBeInTheDocument();
  });

  it('(ج) معمورة: الوصفة المحفوظة تظهر مع أزرار التصدير GeoJSON/CSV', () => {
    stubList({ data: FULL });
    render(<MemoryRouter future={routerFuture}><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/تصدير GeoJSON/)).toBeInTheDocument();
    expect(screen.getByText(/تصدير CSV/)).toBeInTheDocument();
    // TODO صريح لصيغ المُتحكِّمات (لا ندّعي إنتاجها).
    expect(screen.getByText(/ISOXML/)).toBeInTheDocument();
  });

  it('(د) 503: قائمة الوصفات تعرض حالة خطأ صادقة', () => {
    stubList({ isError: true, error: { response: { status: 503 } } as unknown as Error });
    render(<MemoryRouter future={routerFuture}><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByText(/غير متاحة \(503\)/)).toBeInTheDocument();
  });

  it('(هـ) يعرض أداة الرسم والخريطة (لرسم المناطق يدويّاً)', () => {
    stubList({ data: EMPTY });
    render(<MemoryRouter future={routerFuture}><PrescriptionBuilderPage /></MemoryRouter>);
    expect(screen.getByTestId('map')).toBeInTheDocument();
    expect(screen.getByTestId('draw')).toBeInTheDocument();
  });
});
