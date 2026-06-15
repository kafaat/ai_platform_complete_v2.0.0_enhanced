// jwt.ts — فحص انتهاء صلاحيّة توكن الوصول في الواجهة (مصدر واحد للحقيقة).
//
// يحاكي سلوك تطبيق الموبايل (mobile/.../utils/jwt.dart): fail-closed لأيّ توكن
// JWT مشوّه/غير قابل للتحليل/بلا exp صالح. لكنّ الواجهة تدعم أيضاً «وضع التجريب»
// بتوكن وهميّ ليس JWT (demo_token_not_real)، فلو طبّقنا fail-closed مباشرةً
// لاعتُبر منتهياً وكُسِر وضع التجريب فوراً. لذا نفصل القرار:
//   isAccessTokenExpired = isDemoToken(token) ? false : isJwtExpired(token)
// أي أنّ السلوك لا يعتمد على تحليل محتوى توكن التجريب، بل يُستثنى صراحةً.

// توكنات التجريب الوهميّة (ليست JWT): loginDemo يكتب 'demo_token_not_real'،
// وwebsocket يسقط على 'demo' حين غياب توكن حقيقيّ.
const DEMO_TOKENS = new Set(['demo', 'demo_token_not_real']);

/** هل [token] توكن تجريبيّ وهميّ (لا يخضع لفحص انتهاء JWT)؟ */
export function isDemoToken(token: string | null | undefined): boolean {
  return token != null && DEMO_TOKENS.has(token);
}

// فكّ base64url آمن في المتصفّح (atob) أو Node (Buffer)، مع تطبيع الحشو.
function decodeBase64Url(segment: string): string | null {
  try {
    let s = segment.replace(/-/g, '+').replace(/_/g, '/');
    const pad = s.length % 4;
    if (pad === 2) s += '==';
    else if (pad === 3) s += '=';
    else     if (pad === 1) return null; // طول غير صالح
    // atob متاح في المتصفّح وفي بيئة اختبار jsdom.
    if (typeof atob === 'function') return atob(s);
    return null;
  } catch {
    return null;
  }
}

/**
 * هل JWT [token] منتهي الصلاحيّة؟ (fail-closed)
 *
 * يعيد `true` (منتهٍ) لأيّ من: بنية ليست ثلاثة أجزاء، فشل فكّ/تحليل الـpayload،
 * غياب `exp` أو كونه بنوع غير عدديّ. [skewSeconds] هامش أمان (افتراضيّ 60ث)
 * يَعُدّ التوكن منتهياً قبل وقته الفعليّ لتفادي حالات الحدّ وفروق الساعة.
 */
export function isJwtExpired(token: string | null | undefined, skewSeconds = 60): boolean {
  if (!token) return true;
  const parts = token.split('.');
  if (parts.length !== 3) return true;
  const decoded = decodeBase64Url(parts[1]);
  if (decoded == null) return true;
  let payload: unknown;
  try {
    payload = JSON.parse(decoded);
  } catch {
    return true;
  }
  if (typeof payload !== 'object' || payload === null) return true;
  const exp = (payload as Record<string, unknown>).exp;
  // exp يجب أن يكون عدداً منتهياً (ثوانٍ منذ epoch). أيّ شيء آخر ⇒ fail-closed.
  if (typeof exp !== 'number' || !Number.isFinite(exp)) return true;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return nowSeconds > exp - skewSeconds;
}

/**
 * هل توكن الوصول الحاليّ منتهٍ؟ يدعم وضع التجريب: توكن التجريب الوهميّ لا يُعدّ
 * منتهياً أبداً (لا يُكسَر وضع التجريب)، وأيّ توكن آخر يخضع لفحص JWT fail-closed.
 */
export function isAccessTokenExpired(token: string | null | undefined, skewSeconds = 60): boolean {
  if (isDemoToken(token)) return false;
  return isJwtExpired(token, skewSeconds);
}
