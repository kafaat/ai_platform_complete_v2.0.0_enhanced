// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · التلميح (Tooltip)
// ───────────────────────────────────────────────────────────────
// تلميح يظهر عند المرور/التركيز (hover/focus) فوق عنصر مُغلَّف. مُموضَع نسبيّاً
// (top/bottom/start/end)، واعٍ RTL (start/end منطقيّان لا يمين/يسار). a11y:
// يربط المحتوى عبر aria-describedby ويظهر بـfocus أيضاً (لا الفأرة فقط).
// الألوان من tokens.ts.
// ═══════════════════════════════════════════════════════════════
import { useId, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { T, RADIUS } from './tokens';

type Placement = 'top' | 'bottom' | 'start' | 'end';

function bubblePosition(placement: Placement): CSSProperties {
  switch (placement) {
    case 'bottom':
      return { top: '100%', insetInlineStart: '50%', transform: 'translateX(-50%)', marginTop: 6 };
    case 'start':
      return { insetInlineEnd: '100%', top: '50%', transform: 'translateY(-50%)', marginInlineEnd: 6 };
    case 'end':
      return { insetInlineStart: '100%', top: '50%', transform: 'translateY(-50%)', marginInlineStart: 6 };
    case 'top':
    default:
      return { bottom: '100%', insetInlineStart: '50%', transform: 'translateX(-50%)', marginBottom: 6 };
  }
}

export function Tooltip({
  content,
  children,
  placement = 'top',
}: {
  content: ReactNode;
  children: ReactNode;
  placement?: Placement;
}) {
  const [show, setShow] = useState(false);
  const id = useId();
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      <span aria-describedby={show ? id : undefined} style={{ display: 'inline-flex' }}>
        {children}
      </span>
      {show && (
        <span
          id={id}
          role="tooltip"
          style={{
            position: 'absolute',
            zIndex: 60,
            background: T.brown,
            color: '#fff',
            fontSize: 11,
            fontWeight: 600,
            padding: '5px 9px',
            borderRadius: RADIUS.sm,
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            boxShadow: '0 4px 12px rgba(0,0,0,.25)',
            ...bubblePosition(placement),
          }}
        >
          {content}
        </span>
      )}
    </span>
  );
}
