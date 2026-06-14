// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · رموز التصميم (Design Tokens)
// ───────────────────────────────────────────────────────────────
// مستخرَجة من نموذج الواجهة المهنيّ (طراز FieldView، تربة/ذهب/أخضر دافئ)
// الذي اعتمده المستخدم مرجعاً. هذه الطبقة *موازية* للثيم الداكن الحاليّ
// (index.css/tailwind sahool-*) — لا تستبدله؛ تُستخدم في «تطبيق الحقل»
// (شاشات الموبايل المُعاد كسوتها) كي يبني التحقّق دون كسر اللوحة القائمة.
//
// القيم المؤكّدة من النموذج: brown #2C1A0E · gold #E8A020 · green #3EB050.
// منحدر NDVI (ndvi1..6) أحمر→برتقاليّ→أصفر→أخضر فاتح→أخضر→أخضر داكن
// (لوحة NDVI الزراعيّة المعياريّة)؛ قد تُضبط درجات المنتصف بدقّة من لقطة
// المستخدم لاحقاً (التعليق يوثّق ذلك صراحةً — لا اختراع صامت).
// ═══════════════════════════════════════════════════════════════

export const T = {
  // — أساسيّة —
  brown:      '#2C1A0E', // تربة عميقة — نصّ رئيسيّ/عناوين
  brownSoft:  '#5B4636', // بنّيّ ناعم — نصّ ثانويّ داكن
  gold:       '#E8A020', // ذهبيّ — لون الإجراء/التمييز (CTA)
  goldSoft:   '#F6C760', // ذهبيّ فاتح — خلفيّات وسوم
  green:      '#3EB050', // أخضر المحصول السليم — نجاح
  greenDark:  '#2E7D32', // أخضر داكن
  greenSoft:  '#E7F4E9', // أخضر فاتح جدّاً — خلفيّة وسم نجاح

  // — أسطح ونصّ —
  cream:      '#FBF7F0', // خلفيّة الصفحة (فاتح دافئ)
  card:       '#FFFFFF', // سطح البطاقة
  card2:      '#F7F2EA', // سطح ثانويّ (صفّ داخل بطاقة)
  line:       '#E8DFD2', // خطّ فاصل شعريّ
  ink:        '#2C1A0E', // نصّ رئيسيّ
  muted:      '#8A7B6B', // نصّ ثانويّ
  faint:      '#B8AB9A', // نصّ خافت (تلميحات)

  // — حالات —
  ok:         '#3EB050',
  warn:       '#E8A020',
  danger:     '#C0392B',
  info:       '#2D9CDB',
  okBg:       '#E7F4E9',
  warnBg:     '#FBEFD6',
  dangerBg:   '#F8E3E0',
  infoBg:     '#E3F1FB',

  // — منحدر NDVI (منخفض → مرتفع) —
  ndvi1:      '#C0392B', // 0.0–0.2  إجهاد شديد / تربة عارية
  ndvi2:      '#E67E22', // 0.2–0.35
  ndvi3:      '#F1C40F', // 0.35–0.5
  ndvi4:      '#A3CB38', // 0.5–0.65
  ndvi5:      '#3EB050', // 0.65–0.8  صحّيّ
  ndvi6:      '#16794A', // 0.8–1.0  كثيف
} as const;

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

/** لون الحالة + خلفيّته الباهتة (للوسوم) حسب النغمة. */
export function toneColors(tone: Tone): { fg: string; bg: string } {
  switch (tone) {
    case 'ok':     return { fg: T.ok, bg: T.okBg };
    case 'warn':   return { fg: T.warn, bg: T.warnBg };
    case 'danger': return { fg: T.danger, bg: T.dangerBg };
    case 'info':   return { fg: T.info, bg: T.infoBg };
    default:       return { fg: T.brownSoft, bg: T.card2 };
  }
}

/** لون NDVI من القيمة [0..1] عبر منحدر الستّ درجات. */
export function ndviColor(v: number): string {
  if (v < 0.2)  return T.ndvi1;
  if (v < 0.35) return T.ndvi2;
  if (v < 0.5)  return T.ndvi3;
  if (v < 0.65) return T.ndvi4;
  if (v < 0.8)  return T.ndvi5;
  return T.ndvi6;
}

/** نغمة الحالة من شدّة التنبيه (للوسوم). */
export function severityTone(severity?: string | null): Tone {
  const s = (severity ?? '').toLowerCase();
  if (s === 'critical' || s === 'high') return 'danger';
  if (s === 'warning' || s === 'medium') return 'warn';
  if (s === 'info' || s === 'low') return 'info';
  return 'neutral';
}

// ── منحدرات الألوان (Colormaps) لطبقات التحليل المكانيّ ──────────
// مقتبسة نمطاً (لا علامةً) من عرض الطبقات في Operations Center: كلّ طبقة
// منحدر ستّ درجات منخفض→مرتفع. تُستخدم في LayerSwitcher/ColormapLegend.
// (الزراعيّة منها — ndvi/yield — لوحات معياريّة؛ تُضبط من لقطات المستخدم.)
export const CMAP = {
  ndvi:      [T.ndvi1, T.ndvi2, T.ndvi3, T.ndvi4, T.ndvi5, T.ndvi6],
  yield:     ['#8B0000', '#FF4500', '#FFA500', '#FFD700', '#ADFF2F', '#228B22'],
  soil:      ['#F3E5AB', '#D7B899', '#C0956F', '#A17A4E', '#7D5F3A', '#5D3E27'],
  elevation: ['#DDEEFF', '#AACCEE', '#88AACC', '#6688AA', '#446688', '#224466'],
  ec:        ['#FCE4EC', '#F48FB1', '#E91E63', '#C2185B', '#880E4F', '#4A0030'],
  moisture:  ['#E3F2FD', '#90CAF9', '#42A5F5', '#1E88E5', '#1565C0', '#0D47A1'],
} as const;

export type CmapId = keyof typeof CMAP;

export const RADIUS = { sm: 8, md: 12, lg: 16, pill: 999 } as const;
export const SPACE = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 } as const;

/** لون مورد متناقص (وقود/DEF/بطّاريّة): أخضر→برتقاليّ→أحمر حسب النسبة [0..100]. */
export function resourceColor(pct: number): string {
  if (pct > 25) return T.ok;
  if (pct > 10) return T.warn;
  return T.danger;
}
