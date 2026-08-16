// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · نغمة الثيم (Theme Tone)
// ───────────────────────────────────────────────────────────────
// سياق اختياريّ يبدّل رموز الأسطح/النصوص بين الفاتح (T، افتراضيّ — شاشات
// تطبيق الحقل الموبايل) والداكن (T_DARK — صفحات لوحة الويب). الافتراضيّ
// فاتح دائماً: لا يتغيّر أيّ سلوك قائم. يُفعَّل عبر tone="dark" على
// FieldCabin (يوفّر السياق لأحفاده) أو DsThemeProvider مباشرةً.
// ═══════════════════════════════════════════════════════════════
import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { T, T_DARK, type Tokens } from './tokens';

export type DsTone = 'light' | 'dark';

const TokensContext = createContext<Tokens>(T);

/** يوفّر رموز النغمة للأحفاد. الدلالة: `undefined` **يرث** نغمة الأصل (لا
 * إعادة قسريّة للفاتح داخل شجرة داكنة)، والقيمة الصريحة (`light`/`dark`)
 * **تفرض** نغمتها — نفس دلالة `resolveTokens` للمكوّنات. */
export function DsThemeProvider({ tone, children }: { tone?: DsTone; children: ReactNode }) {
  const inherited = useContext(TokensContext);
  const value = tone === undefined ? inherited : tone === 'dark' ? T_DARK : T;
  return <TokensContext.Provider value={value}>{children}</TokensContext.Provider>;
}

/** هل النغمة الفعّالة داكنة؟ (لتفريعات تخطيطٍ تتبع النغمة الموروثة لا الـprop). */
export function useIsDark(): boolean {
  return useContext(TokensContext) === T_DARK;
}

/** رموز النغمة الفعّالة في هذا الموضع من الشجرة (افتراضيّاً T الفاتح). */
export function useT(): Tokens {
  return useContext(TokensContext);
}

/** حلّ النغمة: prop صريح يتغلّب على السياق (لمكوّنات تقبل tone مباشرةً). */
export function resolveTokens(tone: DsTone | undefined, ctx: Tokens): Tokens {
  if (tone === 'dark') return T_DARK;
  if (tone === 'light') return T;
  return ctx;
}
