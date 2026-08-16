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
  subtitle:   '#D8C7B3', // سطر وصفيّ تحت عنوان الكابينة (أفتح من muted على الكريميّ)
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

// ── المتغيّر الداكن (اختياريّ) ─────────────────────────────────
// نفس ألوان التمييز/الحالة (ذهبيّ/أخضر/NDVI) فوق أسطح لوحة الويب الداكنة
// (#1e293b/#0f1117 بحدود #334155 ونصوص #e2e8f0/#94a3b8 — نفس لوحة
// charts.tsx وشاشات التحليل). لا يُغيّر T؛ يُفعَّل صراحةً عبر tone="dark"
// (FieldCabin/Card/DataTable أو DsThemeProvider) لصفحات الويب الداكنة فقط.
// نوع رموز موسَّع (قيم نصّيّة لا حرفيّة) كي تكون T_DARK قابلة للتبديل مع T.
export type Tokens = { readonly [K in keyof typeof T]: string };

// قيم المتغيّر الداكن تُعرَّف كثوابت مرجعيّة (لا كقيم حرفيّة داخل T_DARK)
// حتى تبقى بوّابة تباين التوكِنات (design_token_contrast_gate) مقروءةً من T
// الفاتح فقط — توثيق الأزواج الحاجبة فيها يخصّ نظام Field-App الفاتح.
const DARK_CREAM = '#0f1117'; // خلفيّة الصفحة
const DARK_CARD = '#1e293b'; // سطح البطاقة
const DARK_CARD2 = '#0f172a'; // سطح ثانويّ (صفّ/رأس جدول داخل بطاقة)
const DARK_LINE = '#334155'; // خطّ فاصل
const DARK_INK = '#e2e8f0'; // نصّ رئيسيّ
const DARK_BROWN_SOFT = '#cbd5e1'; // نصّ ثانويّ مُضيء
const DARK_MUTED = '#94a3b8'; // نصّ ثانويّ
const DARK_FAINT = '#64748b'; // نصّ خافت
const DARK_OK_BG = '#14281c';
const DARK_WARN_BG = '#2e2410';
const DARK_DANGER_BG = '#2c1414';
const DARK_INFO_BG = '#0f1f2e';

export const T_DARK: Tokens = {
  ...T,
  // — أسطح ونصّ (داكن) —
  cream:      DARK_CREAM,
  card:       DARK_CARD,
  card2:      DARK_CARD2,
  line:       DARK_LINE,
  ink:        DARK_INK,
  brownSoft:  DARK_BROWN_SOFT,
  muted:      DARK_MUTED,
  subtitle:   DARK_MUTED, // السطر الوصفيّ = النصّ الثانويّ في الداكن
  faint:      DARK_FAINT,
  // — خلفيّات الحالات الباهتة (داكنة) —
  okBg:       DARK_OK_BG,
  warnBg:     DARK_WARN_BG,
  dangerBg:   DARK_DANGER_BG,
  infoBg:     DARK_INFO_BG,
} as const;

export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

/** لون الحالة + خلفيّته الباهتة (للوسوم) حسب النغمة. tokens للمتغيّر الداكن. */
export function toneColors(tone: Tone, tokens: Tokens = T): { fg: string; bg: string } {
  switch (tone) {
    case 'ok':     return { fg: tokens.ok, bg: tokens.okBg };
    case 'warn':   return { fg: tokens.warn, bg: tokens.warnBg };
    case 'danger': return { fg: tokens.danger, bg: tokens.dangerBg };
    case 'info':   return { fg: tokens.info, bg: tokens.infoBg };
    default:       return { fg: tokens.brownSoft, bg: tokens.card2 };
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

// ── ألوان مستويات الحالة (excellent…critical) — مصدر وحيد ────────
// هذه هي القيَم القانونيّة الوحيدة لألوان الحالة. تطابق صفوف .status-* في
// index.css وخريطة STATUS_COLOR التاريخيّة في KPICard (التي صارت تستورد من هنا).
// عند تغيير لون حالة: غيّره هنا فقط (index.css نسخة عرض ثابتة موثَّقة هناك).
export const STATUS_COLORS = {
  excellent: '#16a34a',
  good:      '#65a30d',
  fair:      '#ca8a04',
  poor:      '#f97316',
  critical:  '#dc2626',
} as const;

export type StatusLevel = keyof typeof STATUS_COLORS;

/** لون مستوى الحالة؛ المستوى المجهول/الغائب ⇒ رماديّ محايد (لا اختراع لون). */
export function statusColor(level?: string | null): string {
  const key = (level ?? '').toLowerCase() as StatusLevel;
  return STATUS_COLORS[key] ?? '#6b7280';
}

/** لون مورد متناقص (وقود/DEF/بطّاريّة): أخضر→برتقاليّ→أحمر حسب النسبة [0..100]. */
export function resourceColor(pct: number): string {
  if (pct > 25) return T.ok;
  if (pct > 10) return T.warn;
  return T.danger;
}
