// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · المودال الموحّد (Modal)
// ───────────────────────────────────────────────────────────────
// مودال قانونيّ واحد للكود الجديد (StepShell/BottomSheet يبقيان للقائم).
// طبقة تعتيم + عنوان + إغلاق + فتحة تذييل (footer)، إغلاق بـESC/خلفيّة،
// حبس التركيز (focus-trap) داخل الحوار، وحركة fade/scale عبر framer-motion
// تحترم prefers-reduced-motion. واعٍ RTL. الألوان من tokens.ts.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { X } from 'lucide-react';
import { T, RADIUS } from './tokens';

const FOCUSABLE =
  'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  maxWidth = 480,
  closeOnBackdrop = true,
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  maxWidth?: number;
  closeOnBackdrop?: boolean;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  // إغلاق بـESC + حبس التركيز (Tab/Shift+Tab يدور داخل الحوار فقط).
  useEffect(() => {
    if (!open) return;
    const prevFocus = document.activeElement as HTMLElement | null;
    // ننقل التركيز أوّل عنصر قابل للتركيز (أو الحوار نفسه).
    const focusFirst = () => {
      const node = dialogRef.current;
      if (!node) return;
      const els = node.querySelectorAll<HTMLElement>(FOCUSABLE);
      (els[0] ?? node).focus();
    };
    focusFirst();

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'Tab') {
        const node = dialogRef.current;
        if (!node) return;
        const els = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (els.length === 0) {
          e.preventDefault();
          return;
        }
        const first = els[0];
        const last = els[els.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      // إعادة التركيز للعنصر المُطلِق عند الإغلاق.
      prevFocus?.focus?.();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(44,26,14,.45)', padding: 16 }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0 : 0.18 }}
          onClick={closeOnBackdrop ? onClose : undefined}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === 'string' ? title : undefined}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96 }}
            transition={{ duration: reduce ? 0 : 0.18 }}
            style={{
              background: T.cream,
              width: '100%',
              maxWidth,
              borderRadius: RADIUS.lg,
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              outline: 'none',
            }}
          >
            {title != null && (
              <div
                className="flex items-center justify-between"
                style={{ padding: '14px 16px', borderBottom: `1px solid ${T.line}`, flexShrink: 0 }}
              >
                <h3 style={{ color: T.ink, fontWeight: 800, fontSize: 16 }}>{title}</h3>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="إغلاق"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: T.muted,
                    padding: 4,
                  }}
                >
                  <X style={{ width: 20, height: 20 }} aria-hidden="true" />
                </button>
              </div>
            )}
            <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>{children}</div>
            {footer != null && (
              <div
                className="flex items-center justify-end gap-2"
                style={{ padding: '12px 16px', borderTop: `1px solid ${T.line}`, flexShrink: 0 }}
              >
                {footer}
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
