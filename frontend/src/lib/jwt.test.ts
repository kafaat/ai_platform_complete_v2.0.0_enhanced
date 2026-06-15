// اختبارات jwt — تثبّت fail-closed لفحص انتهاء JWT واستثناء وضع التجريب،
// تستورد الكود الفعليّ (lib/jwt) لكشف أيّ انحراف مستقبليّ.
import { describe, expect, it } from 'vitest';
import { isAccessTokenExpired, isDemoToken, isJwtExpired } from './jwt';

// أداة: تبني JWT بسيطاً (header.payload.signature) بـpayload معطى.
function makeJwt(payload: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(payload)}.sig`;
}

const NOW = Math.floor(Date.now() / 1000);

describe('isDemoToken', () => {
  it('يميّز توكنات التجريب الوهميّة', () => {
    expect(isDemoToken('demo')).toBe(true);
    expect(isDemoToken('demo_token_not_real')).toBe(true);
  });
  it('لا يَعُدّ توكناً حقيقياً أو فارغاً توكنَ تجريب', () => {
    expect(isDemoToken(makeJwt({ exp: NOW + 3600 }))).toBe(false);
    expect(isDemoToken(null)).toBe(false);
    expect(isDemoToken(undefined)).toBe(false);
  });
});

describe('isJwtExpired — fail-closed', () => {
  it('توكن صالح غير منتهٍ ⇒ false', () => {
    expect(isJwtExpired(makeJwt({ exp: NOW + 3600 }))).toBe(false);
  });

  it('توكن منتهٍ ⇒ true', () => {
    expect(isJwtExpired(makeJwt({ exp: NOW - 3600 }))).toBe(true);
  });

  it('ضمن هامش الأمان (skew) ⇒ يُعدّ منتهياً', () => {
    // ينتهي بعد 30ث لكنّ skew الافتراضيّ 60ث ⇒ منتهٍ.
    expect(isJwtExpired(makeJwt({ exp: NOW + 30 }))).toBe(true);
  });

  it('fail-closed: null/فارغ/مشوّه/بلا exp/exp غير عدديّ ⇒ true', () => {
    expect(isJwtExpired(null)).toBe(true);
    expect(isJwtExpired(undefined)).toBe(true);
    expect(isJwtExpired('')).toBe(true);
    expect(isJwtExpired('not-a-jwt')).toBe(true);
    expect(isJwtExpired('a.b')).toBe(true); // جزآن فقط
    expect(isJwtExpired('!!!.@@@.###')).toBe(true); // base64 غير صالح
    expect(isJwtExpired(makeJwt({ sub: 'x' }))).toBe(true); // بلا exp
    expect(isJwtExpired(makeJwt({ exp: 'soon' }))).toBe(true); // exp نصّيّ
  });
});

describe('isAccessTokenExpired — يدعم وضع التجريب', () => {
  it('توكن التجريب لا يُعدّ منتهياً أبداً (لا يُكسَر وضع التجريب)', () => {
    expect(isAccessTokenExpired('demo')).toBe(false);
    expect(isAccessTokenExpired('demo_token_not_real')).toBe(false);
  });

  it('توكن JWT حقيقيّ يخضع لفحص الانتهاء', () => {
    expect(isAccessTokenExpired(makeJwt({ exp: NOW + 3600 }))).toBe(false);
    expect(isAccessTokenExpired(makeJwt({ exp: NOW - 3600 }))).toBe(true);
  });

  it('fail-closed لغير-التجريب: توكن مشوّه ⇒ منتهٍ', () => {
    expect(isAccessTokenExpired('garbage')).toBe(true);
    expect(isAccessTokenExpired(null)).toBe(true);
  });
});
