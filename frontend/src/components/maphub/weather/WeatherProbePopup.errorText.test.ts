// نقلُ طلبَي الإجراء إلى kongApi (FRONTEND-FETCH-OUTSIDE-API-LAYER-01) غيّر شكلَ الفشل:
// كان `Response` بـ`res.ok=false`، وصار خطأَ axios يحمل `response`. فالرسالةُ العربيّة
// الصادقة (401/403/5xx/detail) يجب أن تبقى كما هي — وغيابُ `response` يعني أنّ الطلب
// لم يبلغ الخادم، فيعود المُستدعي إلى «تعذّر الاتصال» كما كان في فرع `catch`.
import { describe, expect, it } from 'vitest';
import { weatherActionErrorText } from './WeatherProbePopup';

const axiosError = (status: number, data?: unknown) => ({ response: { status, data } });

describe('weatherActionErrorText (axios error ⇒ Arabic reason)', () => {
  it('401 ⇒ session expired', () => {
    expect(weatherActionErrorText(axiosError(401), 'x')).toBe('انتهت الجلسة — سجّل الدخول من جديد.');
  });
  it('403 ⇒ server detail when given, else the role hint', () => {
    expect(weatherActionErrorText(axiosError(403, { detail: 'لا صلاحية field:edit' }), 'x')).toBe('لا صلاحية field:edit');
    expect(weatherActionErrorText(axiosError(403), 'x')).toContain('دور مالك/مدير الحقل');
  });
  it('5xx ⇒ server unreachable wording', () => {
    expect(weatherActionErrorText(axiosError(502), 'x')).toBe('تعذّر الاتصال بالخادم — حاول لاحقاً.');
  });
  it('4xx ⇒ structured detail (message_ar / msg) or the fallback', () => {
    expect(weatherActionErrorText(axiosError(422, { detail: { message_ar: 'حقل ناقص' } }), 'x')).toBe('حقل ناقص');
    expect(weatherActionErrorText(axiosError(409, { message_ar: 'مكرّر' }), 'x')).toBe('مكرّر');
    expect(weatherActionErrorText(axiosError(400), 'تعذّر إنشاء المهمة')).toBe('تعذّر إنشاء المهمة');
  });
  it('no response (network / timeout / locally-expired token) ⇒ null so the caller says «تعذّر الاتصال»', () => {
    expect(weatherActionErrorText(new Error('Network Error'), 'x')).toBeNull();
    expect(weatherActionErrorText(null, 'x')).toBeNull();
  });
});
