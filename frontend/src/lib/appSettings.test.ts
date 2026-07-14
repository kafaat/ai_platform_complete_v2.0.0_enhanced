import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SETTINGS_KEY, loadSettings, saveSettings, type AppSettings } from './appSettings';

// مخزّن localStorage صغير في الذاكرة للاختبار (jsdom قد يوفّره، لكن نُثبّته صراحةً
// كي نتحكّم بحالات الفساد/الغياب/الرمي).
function makeStore(initial: Record<string, string> = {}) {
  const map = new Map<string, string>(Object.entries(initial));
  return {
    getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    setItem: (k: string, v: string) => { map.set(k, v); },
    removeItem: (k: string) => { map.delete(k); },
    clear: () => map.clear(),
    _map: map,
  };
}

describe('appSettings — مصدر واحد لتفضيلات العميل (لغة/خريطة)', () => {
  const original = globalThis.localStorage;

  afterEach(() => {
    Object.defineProperty(globalThis, 'localStorage', { value: original, configurable: true });
    vi.restoreAllMocks();
  });

  const installStore = (s: ReturnType<typeof makeStore>) =>
    Object.defineProperty(globalThis, 'localStorage', { value: s, configurable: true });

  it('المفتاح ثابت (sahool_settings) — يطابق main.tsx/SetupCabin', () => {
    expect(SETTINGS_KEY).toBe('sahool_settings');
  });

  it('loadSettings يعيد {} عند غياب التخزين', () => {
    installStore(makeStore());
    expect(loadSettings()).toEqual({});
  });

  it('loadSettings يعيد {} عند JSON فاسد (لا رمي)', () => {
    installStore(makeStore({ [SETTINGS_KEY]: '{not json' }));
    expect(loadSettings()).toEqual({});
  });

  it('loadSettings يعيد {} عند قيمة غير كائن (null/رقم/مصفوفة تُرفَض)', () => {
    installStore(makeStore({ [SETTINGS_KEY]: 'null' }));
    expect(loadSettings()).toEqual({});
    installStore(makeStore({ [SETTINGS_KEY]: '42' }));
    expect(loadSettings()).toEqual({});
  });

  it('saveSettings ثمّ loadSettings يُدوّر التفضيلات (round-trip)', () => {
    installStore(makeStore());
    const prefs: AppSettings = { lang: 'en', map: 'osm' };
    saveSettings(prefs);
    expect(loadSettings()).toEqual(prefs);
  });

  it('saveSettings يبتلع فشل التخزين بهدوء (وضع خاصّ/حصّة ممتلئة)', () => {
    const throwing = makeStore();
    throwing.setItem = () => { throw new Error('QuotaExceededError'); };
    installStore(throwing);
    expect(() => saveSettings({ lang: 'ar' })).not.toThrow();
  });

  it('loadSettings يبتلع فشل القراءة بهدوء ⇒ {}', () => {
    const throwing = makeStore();
    throwing.getItem = () => { throw new Error('SecurityError'); };
    installStore(throwing);
    expect(loadSettings()).toEqual({});
  });
});
