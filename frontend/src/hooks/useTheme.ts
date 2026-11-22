import { useState, useEffect, useCallback } from 'react';

export type Theme = 'dark' | 'light' | 'cream';

const STORAGE_KEY = 'sahool-theme';
const THEMES: readonly Theme[] = ['dark', 'light', 'cream'];

export function readStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  let stored: string | null = null;
  try {
    stored = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage that throws on read (Safari private mode, blocked site data) gets the default.
  }
  return THEMES.includes(stored as Theme) ? (stored as Theme) : 'light';
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
