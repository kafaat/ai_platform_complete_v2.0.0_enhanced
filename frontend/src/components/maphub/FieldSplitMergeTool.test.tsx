// ═══════════════════════════════════════════════════════════════
// SAHOOL — تغطية أداة دمج/تقسيم الحقول (FieldSplitMergeTool) — F3
// ───────────────────────────────────────────────────────────────
// العمليّة الوحيدة المُتلِفة في الخريطة (تُنشئ حقولاً جديدة ثمّ تحذف الأصول).
// الذرّيّة الآن خادميّة: نقطتا POST /fields/merge و/split تُنفّذان الإنشاء+الحذف في
// معاملة قاعدة واحدة (الكلّ أو لا شيء) — لا «دمج/تقسيم جزئيّ» بعد الآن. لذا تختبر هذه
// التغطية أنّ الواجهة تنادي النقطة الذرّيّة مرّة واحدة بالحمولة الصحيحة، وتُظهر رسالة
// خطأ صادقة من ردّ النقطة عند الفشل (تراجع كامل خادميّ، لا تنظيف يدويّ).
//
// jsdom بلا خريطة فعليّة ⇒ نُظلّل react-leaflet / DrawControl / leaflet (نفس نهج
// PrescriptionBuilderPage.test + HubMapGL.test)، ونُظلّل mergeFields/splitField/
// fetchSeasons (services/api) وtoastStore (services/websocket). تغطية منطق/أسلاك عبر
// التظليل — لا تُغني عن متصفّح حيّ (الرسم الفعليّ للقصّ عبر leaflet-draw مُؤجَّل).
//
// نغطّي بصدق المسارات عالية الخطورة:
//   (أ) فحص الموسم النشط مسبقاً يحجب العمليّة قبل أيّ نداء.
//   (ب) دمج ناجح ⇒ نداء واحد لـ/fields/merge بـsource_field_ids+geometry + invalidate.
//   (ج) خطأ النقطة ⇒ toast صادق (لا ادّعاء نجاح، لا «جزئيّ»).
//   (د) حارس MultiPolygon (حقول غير متجاورة) يُحجَب برسالة صريحة قبل أيّ نداء.
//   (هـ) حارس القصّ المفقود في التقسيم يُحجَب برسالة صريحة قبل أيّ نداء.
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

// ── ظِلّ خدمة الـAPI: نقطتا الدمج/التقسيم الذرّيّتان + fetchSeasons + مساعِدات الأخطاء ──
// نُبقي asApiError/apiErrorMessage حقيقيّتين عبر التفويض، فرسالة الخطأ تُختبَر كما يراها
// المستخدم. mergeFields/splitField/fetchSeasons تظليلات قابلة للضبط لكلّ اختبار.
const mockApi = vi.hoisted(() => ({
  merge: vi.fn(),
  split: vi.fn(),
  fetchSeasons: vi.fn(),
}));
vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../services/api')>('../../services/api');
  return {
    ...actual,
    mergeFields: mockApi.merge,
    splitField: mockApi.split,
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
  mockApi.merge.mockReset();
  mockApi.split.mockReset();
  mockApi.fetchSeasons.mockReset();
});

describe('FieldSplitMergeTool — دمج/تقسيم ذرّيّ (نقطتا backend) — F3', () => {
  // (أ) فحص الموسم النشط مسبقاً يحجب قبل أيّ نداء دمج/تقسيم.
  it('(أ) موسم نشط على حقل سيُحذَف ⇒ يُحجَب الدمج قبل أيّ نداء', async () => {
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
    // الجوهر: لا نداء دمج إطلاقاً (الحجب قبل النقطة).
    expect(mockApi.merge).not.toHaveBeenCalled();
  });

  // (ب) دمج ناجح ⇒ نداء واحد لـ/fields/merge بالحمولة الصحيحة + refetch (invalidate).
  it('(ب) دمج ناجح ⇒ نداء /fields/merge واحد بـsource_field_ids+geometry ثمّ refetch', async () => {
    seasonsResolving('closed'); // لا موسم نشط ⇒ يمضي الفحص المسبق
    mockApi.merge.mockResolvedValue({ field_id: 'fld_new' } as never);

    const { refetch, onClose } = renderTool([SQUARE_A, SQUARE_B]);
    const boxes = screen.getAllByRole('checkbox');
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.change(screen.getByPlaceholderText('اسم الحقل الناتج…'), { target: { value: 'المدموج' } });
    fireEvent.click(screen.getByRole('button', { name: /تأكيد الدمج/ }));

    await waitFor(() => expect(mockApi.merge).toHaveBeenCalledTimes(1));
    // نداء واحد ذرّيّ بالحمولة: المصادر + الاسم + الهندسة المدموجة (Polygon واحد).
    const payload = mockApi.merge.mock.calls[0][0];
    expect(payload.source_field_ids).toEqual(['a', 'b']);
    expect(payload.name).toBe('المدموج');
    expect(payload.geometry?.type).toBe('Polygon'); // اتّحاد @turf لحقلين متجاورين
    // نجاح ⇒ رسالة نجاح + إغلاق + refetch (إبطال قائمة الحقول).
    await waitFor(() => expect(toasts.some((t) => /تمّ دمج الحقول/.test(t.title))).toBe(true));
    expect(onClose).toHaveBeenCalled();
    expect(refetch).toHaveBeenCalled();
  });

  // (ج) خطأ النقطة ⇒ toast صادق من ردّ الخادم (لا ادّعاء نجاح، لا «جزئيّ»).
  it('(ج) فشل /fields/merge (مثلاً 409) ⇒ toast خطأ صادق (تراجع خادميّ كامل)', async () => {
    seasonsResolving('closed');
    // الخادم يرفض ذرّيّاً (مثلاً موسم نشط/تداخل) — رسالة عربيّة من apiErrorMessage.
    mockApi.merge.mockRejectedValue({
      response: { status: 409, data: { detail: 'لا يمكن الدمج: موسم نشط على حقل مصدر' } },
    } as never);

    const { refetch } = renderTool([SQUARE_A, SQUARE_B]);
    const boxes = screen.getAllByRole('checkbox');
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    fireEvent.change(screen.getByPlaceholderText('اسم الحقل الناتج…'), { target: { value: 'المدموج' } });
    fireEvent.click(screen.getByRole('button', { name: /تأكيد الدمج/ }));

    await waitFor(() => expect(toasts.some((t) => /فشل الدمج/.test(t.title))).toBe(true));
    // نداء واحد فقط (لا حلقة حذف، لا حالة جزئيّة) — والرسالة تحمل سبب الخادم الصريح.
    expect(mockApi.merge).toHaveBeenCalledTimes(1);
    const err = toasts.find((t) => /فشل الدمج/.test(t.title))!;
    expect(err.message).toMatch(/لا يمكن الدمج: موسم نشط على حقل مصدر/);
    // لا رسالة «جزئيّ» إطلاقاً (الذرّيّة الخادميّة ألغتها).
    expect(toasts.some((t) => /جزئيّ/.test(t.title))).toBe(false);
    expect(refetch).toHaveBeenCalled();
  });

  // (د) حارس MultiPolygon (حقول غير متجاورة) يُحجَب — لا نداء دمج.
  it('(د) دمج حقول غير متجاورة (MultiPolygon) ⇒ يُحجَب برسالة «غير متجاورة»', async () => {
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
    expect(mockApi.merge).not.toHaveBeenCalled();
    expect(mockApi.fetchSeasons).not.toHaveBeenCalled();
  });

  // (هـ) حارس القصّ المفقود في التقسيم يُحجَب — لا نداء تقسيم.
  it('(هـ) تقسيم بلا مضلّع قصّ ⇒ يُطلَب الرسم ولا تُنفَّذ شبكة', async () => {
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
    expect(mockApi.split).not.toHaveBeenCalled();
  });
});
