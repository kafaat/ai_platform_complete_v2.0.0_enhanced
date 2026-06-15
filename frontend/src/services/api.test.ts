// اختبارات عميل الـAPI — الدوالّ النقيّة لقراءة الأخطاء (apiErrorMessage,
// isMfaRequiredError) وبناء طلب fetchTenantConfig (شكل الطلب + التسامح).
// نَستبدِل axios.create بعميل وهميّ كي لا يخرج أيّ طلب شبكيّ حقيقيّ.
import { describe, it, expect, vi, beforeEach } from 'vitest';

// عميل axios وهميّ: كلّ الأفعال vi.fn، والـinterceptors بلا أثر.
// نستخدم vi.hoisted كي يتوفّر الكائن لمصنع vi.mock المرفوع لأعلى الوحدة.
const { mockGet, mockClient } = vi.hoisted(() => {
  const get = vi.fn();
  return {
    mockGet: get,
    mockClient: {
      get,
      post: vi.fn(),
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
