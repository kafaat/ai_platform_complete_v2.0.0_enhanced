import { describe, it, expect } from 'vitest';
import { apiFieldErrors } from './api/auth';

// continuation-3 P2: استخراج أخطاء الحقول من 422 (FastAPI) → {field, msg}.
const err422 = (detail: unknown) => ({ response: { data: { detail }, status: 422 } });

describe('apiFieldErrors', () => {
  it('يستخرج الحقل (آخر مقطع بعد body) والرسالة من كل عنصر', () => {
    const out = apiFieldErrors(err422([
      { loc: ['body', 'latitude'], msg: 'خارج المدى' },
      { loc: ['body', 'ph'], msg: 'قيمة غير صالحة' },
    ]));
    expect(out).toEqual([
      { field: 'latitude', msg: 'خارج المدى' },
      { field: 'ph', msg: 'قيمة غير صالحة' },
    ]);
  });

  it('حقل فارغ عند غياب loc قابل للاستخدام', () => {
    expect(apiFieldErrors(err422([{ msg: 'خطأ عامّ' }]))).toEqual([{ field: '', msg: 'خطأ عامّ' }]);
  });

  it('فارغ عند غياب 422 حقليّ', () => {
    expect(apiFieldErrors({ response: { data: { detail: 'نصّ' }, status: 400 } })).toEqual([]);
    expect(apiFieldErrors(new Error('network'))).toEqual([]);
    expect(apiFieldErrors(null)).toEqual([]);
  });
});
