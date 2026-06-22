// ═══════════════════════════════════════════════════════════════
// SAHOOL — تغطية أداة دمج/تقسيم الحقول (FieldSplitMergeTool) — F3
// ───────────────────────────────────────────────────────────────
// العمليّة الوحيدة المُتلِفة في الخريطة (تُنشئ حقولاً جديدة ثمّ تحذف الأصول).
// jsdom بلا خريطة فعليّة ⇒ نُظلّل react-leaflet / DrawControl / leaflet (نفس نهج
// PrescriptionBuilderPage.test + HubMapGL.test)، ونُظلّل kongApi/fetchSeasons
// (services/api) وtoastStore (services/websocket) لِنُثبت أسلاك/منطق العمليّة
// بصدق بلا شبكة. هذه تغطية منطق/أسلاك عبر التظليل — لا تُغني عن متصفّح حيّ
// (الرسم الفعليّ للقصّ عبر leaflet-draw مُؤجَّل، موثّق أدناه).
//
// نغطّي بصدق المسارات عالية الخطورة:
//   (أ) فحص الموسم النشط مسبقاً يحجب العمليّة قبل أيّ create/delete.
//   (ب) ترتيب create-before-delete + أمانة الفشل الجزئيّ (إنشاء نجح، حذف فشل).
//   (ج) حارس MultiPolygon (حقول غير متجاورة) يُحجَب برسالة صريحة.
//   (د) حارس التقاطع الفارغ في التقسيم (قصّ لا يتقاطع) يُحجَب برسالة صريحة.
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { FieldOption } from '../../lib/fields';

// ── ظِلّ react-leaflet / DrawControl / leaflet (jsdom بلا خريطة فعليّة) ──
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => <div data-testid="tile" />,
  Polygon: () => <div data-testid="polygon" />,
  FeatureGroup: ({ children }: { children?: ReactNode }) => <div data-testid="fg">{children}</div>,
}));
vi.mock('./DrawControl', () => ({ default: () => <div data-testid="draw" /> }));
vi.mock('../../lib/leafletSetup', () => ({}));
vi.mock('leaflet', () => ({
  default: {
    latLng: (a: number, b: number) => ({ lat: a, lng: b }),
    latLngBounds: (pts: unknown[]) => ({ pts }),
  },
}));

// ── ظِلّ خدمة الـAPI: kongApi (post/delete) + fetchSeasons + مساعِدات الأخطاء ──
// نُبقي asApiError/apiErrorMessage حقيقيّتين عبر التفويض، فالرسائل الجزئيّة تُختبَر
// كما يراها المستخدم. kongApi/fetchSeasons تظليلات قابلة للضبط لكلّ اختبار.
const mockApi = vi.hoisted(() => ({
  post: vi.fn(),
  del: vi.fn(),
  fetchSeasons: vi.fn(),
}));
vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../services/api')>('../../services/api');
  return {
    ...actual,
    kongApi: { post: mockApi.post, delete: mockApi.del },
    fetchSeasons: mockApi.fetchSeasons,
  };
});

// ── ظِلّ toastStore: نلتقط كلّ نداء add(type, title, message) لِنفحص الرسائل ──
const toasts = vi.hoisted(() => [] as Array<{ type: string; title: string; message: string }>);
vi.mock('../../services/websocket', () => ({
  toastStore: {
    add: (type: string, title: string, message: string) => {
      toasts.push({ type, title, message });
    },
  },
}));

import FieldSplitMergeTool from './FieldSplitMergeTool';

// ── حقول صادقة بمضلّعات GeoJSON صالحة ([lon,lat]، حلقة ≥3 رؤوس) ──────────
// مربّعان متجاوران (يشتركان في الحافّة عند lon=44.1) ⇒ دمجهما Polygon واحد.
function makeField(id: string, name: string, ring: number[][]): FieldOption {
  return {
    id, name, lat: ring[0][1], lon: ring[0][0],
    geometry: { type: 'Polygon', coordinates: [ring] },
    area: 10, crop: 'قمح',
  };
}
const SQUARE_A = makeField('a', 'حقل أ', [[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.1], [44.0, 15.0]]);
const SQUARE_B = makeField('b', 'حقل ب', [[44.1, 15.0], [44.2, 15.0], [44.2, 15.1], [44.1, 15.1], [44.1, 15.0]]);
// حقل بعيد (لا يتلامس مع أ/ب) ⇒ دمجه مع أ ينتج MultiPolygon (الخادم يرفضه).
const SQUARE_FAR = makeField('far', 'حقل بعيد', [[50.0, 20.0], [50.1, 20.0], [50.1, 20.1], [50.0, 20.1], [50.0, 20.0]]);

function renderTool(fields: FieldOption[], selectedId = '') {
  const refetch = vi.fn();
  const onClose = vi.fn();
  render(<FieldSplitMergeTool fields={fields} selectedId={selectedId} onClose={onClose} refetch={refetch} />);
  return { refetch, onClose };
}

// يضبط ردّ الموسم: closed (قابل للحذف) افتراضيّاً، أو active للحجب.
function seasonsResolving(status: 'active' | 'closed') {
  mockApi.fetchSeasons.mockResolvedValue([{ status }] as never);
}

beforeEach(() => {
  toasts.length = 0;
  mockApi.post.mockReset();
  mockApi.del.mockReset();
  mockApi.fetchSeasons.mockReset();
});

describe('FieldSplitMergeTool — دمج/تقسيم (عمليّة مُتلِفة) — F3', () => {
  // (أ) فحص الموسم النشط مسبقاً يحجب قبل أيّ create/delete.
  it('(أ) موسم نشط على حقل سيُحذَف ⇒ يُحجَب الدمج قبل أيّ POST/DELETE', async () => {
    seasonsResolving('active'); // كلا الحقلين «نشط» ⇒ الفحص المسبق يُرجِع أوّل اسم
    renderTool([SQUARE_A, SQUARE_B]);

    // اختَر الحقلين المتجاورين (مربّعا الاختيار) + اسم الناتج.
    const boxes = screen.getAllByRole('checkbox');
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.change(screen.getByPlaceholderText('اسم الحقل الناتج…'), { target: { value: 'المدموج' } });

    fireEvent.click(screen.getByRole('button', { name: /تأكيد الدمج/ }));

    // الفحص المسبق غير متزامن ⇒ ننتظر ظهور رسالة الحجب.
    await waitFor(() =>
      expect(toasts.some((t) => /موسم نشط يمنع الدمج/.test(t.title))).toBe(true));
    // الجوهر: لا إنشاء ولا حذف إطلاقاً (لا حالة نصف منجَزة).
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(mockApi.del).not.toHaveBeenCalled();
  });

  // (ب) ترتيب create-before-delete + أمانة الفشل الجزئيّ.
  it('(ب) الإنشاء نجح والحذف فشل ⇒ رسالة دمج جزئيّ صريحة (لا ادّعاء نجاح)', async () => {
    seasonsResolving('closed'); // لا موسم نشط ⇒ يمضي الفحص المسبق
    mockApi.post.mockResolvedValue({ data: { id: 'new_1' } } as never);
    // الحذف يفشل لكلا الأصلين (سباق ⇒ 409) — رسالة عربيّة من apiErrorMessage.
    mockApi.del.mockRejectedValue({
      response: { status: 409, data: { detail: 'لا يمكن الحذف لوجود ارتباطات' } },
    } as never);

    renderTool([SQUARE_A, SQUARE_B]);
    const boxes = screen.getAllByRole('checkbox');
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.change(screen.getByPlaceholderText('اسم الحقل الناتج…'), { target: { value: 'المدموج' } });
    fireEvent.click(screen.getByRole('button', { name: /تأكيد الدمج/ }));

    await waitFor(() =>
      expect(toasts.some((t) => /دمج جزئيّ — يلزم تدخّل/.test(t.title))).toBe(true));

    // ترتيب ذرّيّ: أُنشئ المدموج أوّلاً (post واحد) ثمّ حُذِفت الأصول (del لكلّ أصل).
    expect(mockApi.post).toHaveBeenCalledTimes(1);
    const postOrder = mockApi.post.mock.invocationCallOrder[0];
    const delOrder = Math.min(...mockApi.del.mock.invocationCallOrder);
    expect(postOrder).toBeLessThan(delOrder); // create-before-delete
    expect(mockApi.del).toHaveBeenCalledTimes(2);

    // الرسالة الجزئيّة تُسمّي ما أُنشئ وما تعذّر حذفه (لا ابتلاع صامت).
    const partial = toasts.find((t) => /دمج جزئيّ/.test(t.title))!;
    expect(partial.message).toMatch(/المدموج/); // ما أُنشئ
    expect(partial.message).toMatch(/«حقل أ»/); // أصل تعذّر حذفه
    expect(partial.message).toMatch(/لا يمكن الحذف لوجود ارتباطات/); // سبب الفشل الصريح
  });

  // (ج) حارس MultiPolygon (حقول غير متجاورة) يُحجَب — لا create/delete.
  it('(ج) دمج حقول غير متجاورة (MultiPolygon) ⇒ يُحجَب برسالة «غير متجاورة»', async () => {
    seasonsResolving('closed');
    renderTool([SQUARE_A, SQUARE_FAR]);
    const boxes = screen.getAllByRole('checkbox');
    fireEvent.click(boxes[0]); // أ
    fireEvent.click(boxes[1]); // البعيد ⇒ الاتّحاد MultiPolygon
    fireEvent.change(screen.getByPlaceholderText('اسم الحقل الناتج…'), { target: { value: 'المدموج' } });

    // التحذير المرئيّ في اللوحة (الناتج متعدّد الأجزاء) حاضر قبل التأكيد.
    expect(screen.getByText(/غير متجاورة/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /تأكيد الدمج/ }));

    // الحجب تزامنيّ (قبل الفحص المسبق) ⇒ رسالة صريحة ولا شبكة إطلاقاً.
    await waitFor(() =>
      expect(toasts.some((t) => /الحقول غير متجاورة/.test(t.title))).toBe(true));
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(mockApi.del).not.toHaveBeenCalled();
    expect(mockApi.fetchSeasons).not.toHaveBeenCalled();
  });

  // (د) حارس التقاطع الفارغ في التقسيم (قصّ لا يتقاطع) يُحجَب — لا create/delete.
  it('(د) تقسيم بلا مضلّع قصّ ⇒ يُطلَب الرسم ولا تُنفَّذ شبكة', async () => {
    seasonsResolving('closed');
    renderTool([SQUARE_A, SQUARE_B], 'a'); // selectedId يُهيّئ حقل التقسيم

    // بدّل إلى وضع التقسيم.
    fireEvent.click(screen.getByRole('button', { name: /^تقسيم$/ }));
    fireEvent.change(screen.getByPlaceholderText('اسم الجزء أ…'), { target: { value: 'جزء-أ' } });
    fireEvent.change(screen.getByPlaceholderText('اسم الجزء ب…'), { target: { value: 'جزء-ب' } });

    // لا قصّ مرسوم (cutGeom = null) ⇒ الحارس يطلب رسم المضلّع، لا شبكة.
    fireEvent.click(screen.getByRole('button', { name: /تأكيد التقسيم/ }));
    await waitFor(() =>
      expect(toasts.some((t) => /ارسم مضلّع القصّ/.test(t.title))).toBe(true));
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(mockApi.del).not.toHaveBeenCalled();
  });
});
