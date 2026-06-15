// useTheme — ثلاثة أنماط للواجهة: داكن/نهاريّ/كريميّ. الافتراضيّ داكن، فلا
// تغيير بصريّ ما لم يُبدّل المستخدم. تُحفظ السمة في localStorage وتُطبَّق على
// عنصر <html> عبر data-theme، فتُحلّ متغيّرات --sahool-* لكل سمة من index.css.
import { useState, useEffect, useCallback } from 'react';

export type Theme = 'dark' | 'light' | 'cream';

const STORAGE_KEY = 'sahool-theme';
const THEMES: readonly Theme[] = ['dark', 'light', 'cream'];

function readStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return THEMES.includes(stored as Theme) ? (stored as Theme) : 'dark';
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readStoredTheme);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // تجاهل (وضع خاصّ/تخزين مُعطَّل) — تبقى السمة في الذاكرة لهذه الجلسة.
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  return { theme, setTheme };
}
