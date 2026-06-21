// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · مسار التنقّل (Breadcrumb)
// ───────────────────────────────────────────────────────────────
// مسار تنقّل واعٍ RTL: الفاصل ChevronLeft (في RTL «التقدّم» يتّجه يساراً).
// العنصر الأخير هو الصفحة الحاليّة (aria-current) بلا نقر. الألوان من tokens.ts.
// ═══════════════════════════════════════════════════════════════
import { ChevronLeft } from 'lucide-react';
import { T } from './tokens';

export interface Crumb {
  label: string;
  onClick?: () => void;
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="مسار التنقّل">
      <ol className="flex items-center flex-wrap" style={{ gap: 4, listStyle: 'none', margin: 0, padding: 0 }}>
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={i} className="flex items-center" style={{ gap: 4 }}>
              {item.onClick && !last ? (
                <button
                  type="button"
                  onClick={item.onClick}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: T.muted,
                    fontSize: 12,
                    fontWeight: 600,
                    padding: 0,
                  }}
                >
                  {item.label}
                </button>
              ) : (
                <span
                  aria-current={last ? 'page' : undefined}
                  style={{ color: last ? T.ink : T.muted, fontSize: 12, fontWeight: last ? 800 : 600 }}
                >
                  {item.label}
                </span>
              )}
              {!last && (
                <ChevronLeft style={{ width: 14, height: 14, color: T.faint, flexShrink: 0 }} aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
