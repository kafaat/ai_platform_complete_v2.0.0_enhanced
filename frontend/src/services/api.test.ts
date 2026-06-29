// اختبارات عميل الـAPI — الدوالّ النقيّة لقراءة الأخطاء (apiErrorMessage,
// isMfaRequiredError) وبناء طلب fetchTenantConfig (شكل الطلب + التسامح).
// نَستبدِل axios.create بعميل وهميّ كي لا يخرج أيّ طلب شبكيّ حقيقيّ.
import { describe, it, expect, vi, beforeEach } from 'vitest';

// عميل axios وهميّ: كلّ الأفعال vi.fn، والـinterceptors بلا أثر.
// نستخدم vi.hoisted كي يتوفّر الكائن لمصنع vi.mock المرفوع لأعلى الوحدة.
const { mockGet, mockPost, mockClient } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return {
    mockGet: get,
    mockPost: post,
    mockClient: {
      get,
      post,
      put: vi.fn(),
      patch: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    },
  };
});

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockClient),
  },
}));

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import {
  apiErrorMessage,
  isMfaRequiredError,
  fetchTenantConfig,
  classifySegmentationError,
  segmentField,
  fetchImageryBackfillPolicy,
  runHistoricalImageryBackfill,
} from './api';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('apiErrorMessage', () => {
  it('يستخرج detail النصّيّ من ردّ FastAPI', () => {
    const err = { response: { data: { detail: 'الحقل غير موجود' } } };
    expect(apiErrorMessage(err, 'احتياط')).toBe('الحقل غير موجود');
  });

  it('يجمع رسائل مصفوفة detail (أخطاء التحقّق) بفاصلة عربيّة', () => {
    const err = {
      response: {
        data: {
          detail: [{ msg: 'البريد مطلوب' }, { msg: 'كلمة المرور قصيرة' }],
        },
      },
    };
    expect(apiErrorMessage(err, 'احتياط')).toBe('البريد مطلوب، كلمة المرور قصيرة');
  });

  it('يُفضّل message_ar من كائن detail', () => {
    const err = { response: { data: { detail: { message_ar: 'خطأ عربيّ' } } } };
    expect(apiErrorMessage(err, 'احتياط')).toBe('خطأ عربيّ');
  });

  it('يسقط على message ثمّ على الاحتياط حين لا detail', () => {
    expect(apiErrorMessage({ message: 'network error' }, 'احتياط')).toBe('network error');
    expect(apiErrorMessage({}, 'احتياط')).toBe('احتياط');
    expect(apiErrorMessage({ response: { data: { detail: [] } } }, 'احتياط')).toBe('احتياط');
  });
});

describe('isMfaRequiredError', () => {
  it('صحيح فقط عند 401 + الرأس x-mfa-required', () => {
    expect(
      isMfaRequiredError({ response: { status: 401, headers: { 'x-mfa-required': 'true' } } }),
    ).toBe(true);
    expect(
      isMfaRequiredError({ response: { status: 401, headers: { 'x-mfa-required': true } } }),
    ).toBe(true);
  });

  it('خطأ لو غاب الرأس أو اختلفت الحالة', () => {
    expect(isMfaRequiredError({ response: { status: 401, headers: {} } })).toBe(false);
    expect(
      isMfaRequiredError({ response: { status: 403, headers: { 'x-mfa-required': 'true' } } }),
    ).toBe(false);
    expect(isMfaRequiredError({})).toBe(false);
    expect(isMfaRequiredError(undefined)).toBe(false);
  });
});

describe('fetchTenantConfig', () => {
  it('يطلب المسار الصحيح ويُرجِع البيانات حين تكون كائناً', async () => {
    const config = { branding: null, units: 'metric', language: 'ar', crops: ['قمح'] };
    mockGet.mockResolvedValueOnce({ data: config });
    const out = await fetchTenantConfig();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/tenant/config');
    expect(out).toEqual(config);
  });

  it('أفضل-جهد: استجابة غير كائن → null', async () => {
    mockGet.mockResolvedValueOnce({ data: '<html>not found</html>' });
    expect(await fetchTenantConfig()).toBeNull();
  });

  it('أفضل-جهد: أيّ خطأ → null (لا كسر، لا تلفيق)', async () => {
    mockGet.mockRejectedValueOnce(new Error('503'));
    expect(await fetchTenantConfig()).toBeNull();
  });
});

// ── H — التقطيع المُساعَد: تصنيف الخطأ الصادق + شكل الطلب ─────────────
describe('classifySegmentationError (تعامل صادق عند غياب النموذج/الخدمة)', () => {
  it('503 + detail=model_not_configured ⇒ model_not_configured (رسالة صريحة)', () => {
    expect(
      classifySegmentationError({ response: { status: 503, data: { detail: 'model_not_configured' } } }),
    ).toBe('model_not_configured');
    // الرمز قد يأتي في error أو code كذلك.
    expect(
      classifySegmentationError({ response: { status: 503, data: { error: 'model_not_configured' } } }),
    ).toBe('model_not_configured');
    expect(
      classifySegmentationError({ response: { status: 503, data: { code: 'model_not_configured' } } }),
    ).toBe('model_not_configured');
  });

  it('404 (الخدمة غير منشورة) ⇒ unavailable بلطف', () => {
    expect(classifySegmentationError({ response: { status: 404 } })).toBe('unavailable');
  });

  it('503 بلا رمز معروف ⇒ unavailable (غير متاح مؤقّتاً)', () => {
    expect(
      classifySegmentationError({ response: { status: 503, data: { detail: 'overloaded' } } }),
    ).toBe('unavailable');
  });

  it('أيّ خطأ آخر (شبكة/4xx/5xx) ⇒ error', () => {
    expect(classifySegmentationError({ response: { status: 422, data: { detail: 'bad bbox' } } })).toBe('error');
    expect(classifySegmentationError(new Error('network'))).toBe('error');
    expect(classifySegmentationError(undefined)).toBe('error');
  });
});

describe('segmentField (POST /api/segmentation/segment)', () => {
  it('يطلب المسار الصحيح بالحمولة (bbox/mode) ويُعيد الهندسة المُقترَحة', async () => {
    const result = {
      geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]] },
      mode: 'auto',
      confidence: 0.91,
    };
    mockPost.mockResolvedValueOnce({ data: result });
    const payload = { mode: 'auto' as const, bbox: [44, 15, 44.01, 15.01] as [number, number, number, number] };
    const out = await segmentField(payload);
    expect(mockPost).toHaveBeenCalledWith('/api/segmentation/segment', payload);
    expect(out).toEqual(result);
  });

  it('يرمي عند 503 model_not_configured (لا تلفيق) — يُصنَّف للواجهة', async () => {
    const err = { response: { status: 503, data: { detail: 'model_not_configured' } } };
    mockPost.mockRejectedValueOnce(err);
    const caught = await segmentField({ mode: 'auto', bbox: [44, 15, 44.01, 15.01] })
      .then(() => null)
      .catch(e => e);
    expect(caught).toBe(err);
    // الواجهة تصنّف الخطأ المرفوع إلى رسالة صريحة (لا مضلّع مُفبرَك):
    expect(classifySegmentationError(caught)).toBe('model_not_configured');
  });
});


describe('historical imagery backfill API', () => {
  it('fetches the switchable 12m/3y/5y/custom policy from raster service', async () => {
    const policy = { presets: { auto_12_months: { months: 12 }, extended_3_years: { months: 36 }, research_5_years: { months: 60 }, custom: {} } };
    mockGet.mockResolvedValueOnce({ data: policy });
    const out = await fetchImageryBackfillPolicy();
    expect(mockGet).toHaveBeenCalledWith('/v1/imagery/backfill/policy');
    expect(out).toEqual(policy);
  });

  it('runs a configurable field historical backfill request', async () => {
    const response = { field_id: 'F-1', preset: 'extended_3_years', jobs_scheduled: 4 };
    mockPost.mockResolvedValueOnce({ data: response });
    const payload = {
      preset: 'extended_3_years' as const,
      indices: ['ndvi', 'ndmi'],
      max_cloud_pct: 25,
      limit_per_month: 1,
      dry_run: true,
      clip_polygon_geojson: { type: 'Polygon', coordinates: [] },
    };
    const out = await runHistoricalImageryBackfill('F-1', payload);
    expect(mockPost).toHaveBeenCalledWith('/v1/fields/F-1/imagery/backfill', payload);
    expect(out).toEqual(response);
  });
});
