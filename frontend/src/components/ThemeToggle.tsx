// ThemeToggle — مُحدِّد «نمط الواجهة» ثلاثيّ: داكن (قمر)، نهاريّ (شمس)،
// كريميّ (نبتة). عنصر تحكّم مُقسَّم مُدمج للشريط العلويّ، يستدعي setTheme القادم
// من useTheme. مُتاح للوصول (aria-label/title، type="button"، النشط مُميَّز).
import { Sun, Moon, Sprout } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Theme } from '../hooks/useTheme';

interface ThemeToggleProps {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const MODES: { value: Theme; label: string; Icon: LucideIcon }[] = [
  { value: 'dark', label: 'داكن', Icon: Moon },
  { value: 'light', label: 'نهاريّ', Icon: Sun },
  { value: 'cream', label: 'كريميّ', Icon: Sprout },
];

export default function ThemeToggle({ theme, setTheme }: ThemeToggleProps) {
  return (
    <div
      role="group"
      aria-label="نمط الواجهة"
      className="flex items-center gap-0.5 p-0.5 rounded-lg border border-sahool-border bg-sahool-surface-2"
    >
      {MODES.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => setTheme(value)}
            aria-label={label}
            aria-pressed={active}
            title={label}
            className={
              'flex items-center justify-center w-7 h-7 rounded-md transition-colors ' +
              (active
                ? 'bg-sahool-green text-white'
                : 'text-sahool-muted hover:text-sahool-text hover:bg-sahool-surface')
            }
          >
            <Icon className="w-4 h-4" />
          </button>
        );
      })}
    </div>
  );
}
