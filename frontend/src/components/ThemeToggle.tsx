// ThemeToggle — زرّ تبديل السمة (شمس/قمر). يبدّل بين الفاتح والداكن ويستدعي
// setTheme القادم من useTheme. مُتاح للوصول (aria-label/title، type="button").
import { Sun, Moon } from 'lucide-react';
import type { Theme } from '../hooks/useTheme';

interface ThemeToggleProps {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

export default function ThemeToggle({ theme, setTheme }: ThemeToggleProps) {
  const isDark = theme === 'dark';
  const label = isDark ? 'تفعيل الوضع الفاتح' : 'تفعيل الوضع الداكن';

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      aria-label={label}
      title={label}
      className="flex items-center justify-center w-8 h-8 rounded-lg border border-sahool-border text-sahool-muted hover:text-sahool-text hover:bg-sahool-surface transition-colors"
    >
      {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
}
