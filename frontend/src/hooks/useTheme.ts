// useTheme — سمة فاتحة/داكنة (المرحلة 1: الأساس). الافتراضيّ داكن، فلا تغيير
// بصريّ ما لم يُبدّل المستخدم. تُحفظ السمة في localStorage وتُطبَّق على عنصر
// <html> عبر data-theme، فتُحلّ متغيّرات --sahool-* لكل سمة من index.css.
import { useState, useEffect, useCallback } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'sahool-theme';

function readStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === 'light' || stored === 'dark' ? stored : 'dark';
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
