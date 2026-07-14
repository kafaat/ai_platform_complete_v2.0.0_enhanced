// ═══════════════════════════════════════════════════════════════
// appSettings — تفضيلات العميل غير الحسّاسة (لغة/مزود خريطة) المحفوظة محلّيّاً.
// استُخرِجت من SettingsPage.tsx (الكاتب) وSetupCabin.tsx (القارئ) اللذَين كرّرا
// نفس المفتاح ومنطق التحميل الدفاعيّ — مصدر واحد قابل للاختبار يمنع الانحراف.
//
// قيود صريحة (أمان): نحفظ التفضيلات غير الحسّاسة فقط. لا مفاتيح/أسرار أبداً في
// localStorage (تخزينها يعرّضها لسرقة عبر XSS). القراءة دفاعيّة: غياب/فساد
// التخزين ⇒ كائن فارغ (لا قيم مُختلَقة). main.tsx يمسح هذا المفتاح عند فقد
// هويّة المستأجِر (نظافة المتصفّح المشترَك) عبر removeItem(SETTINGS_KEY).
// ═══════════════════════════════════════════════════════════════

export const SETTINGS_KEY = 'sahool_settings';

export interface AppSettings {
  lang?: string;
  map?: string;
}

// قراءة دفاعيّة: غياب التخزين/فساد JSON/قيمة غير كائن ⇒ {} (لا قيم مُختلَقة).
export function loadSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? (parsed as AppSettings) : {};
  } catch {
    return {};
  }
}

// كتابة: تفضيلات غير حسّاسة فقط. تخزين المتصفّح غير المتاح يُتجاهَل بهدوء
// (وضع خاصّ/حصّة ممتلئة) — لا يُسقِط تدفّق الحفظ في الواجهة.
export function saveSettings(settings: AppSettings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    /* تخزين المتصفّح غير متاح — نتجاهل بهدوء */
  }
}
