// ═══════════════════════════════════════════════════════════════
// SAHOOL — Field-App Design System · المكوّنات الذرّيّة (Atoms)
// ───────────────────────────────────────────────────────────────
// منقولة من نموذج الواجهة المهنيّ إلى React+TS، واعية للاتجاه RTL
// (التطبيق dir="rtl" عالميّاً؛ نستخدم الخصائص المنطقيّة والـflex فلا
// نثبّت يميناً/يساراً). الألوان من tokens.ts (لا قيَم سحريّة مكرّرة).
// تُستخدم لكسوة شاشات «تطبيق الحقل». تُبنى وتُفحَص أنواعها بـtsc.
// ═══════════════════════════════════════════════════════════════
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react';
import { ChevronLeft } from 'lucide-react';
import { T, RADIUS, toneColors, type Tone } from './tokens';

// تفعيل العناصر القابلة للنقر عبر الكيبورد (Enter/Space) — وصوليّة a11y:
// أيّ عنصر يحمل role="button" يجب أن يُفعَّل بالمفتاحين لا بالفأرة فقط.
function keyActivate(onClick?: () => void) {
  if (!onClick) return undefined;
  return (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };
}

// ── Card ───────────────────────────────────────────────────────
export function Card({
  children, onClick, className = '', style, pad = 16,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  style?: CSSProperties;
  pad?: number;
}) {
  return (
    <div
      onClick={onClick}
      onKeyDown={keyActivate(onClick)}
      className={className}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{
        background: T.card,
        border: `1px solid ${T.line}`,
        borderRadius: RADIUS.md,
        padding: pad,
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── SectionLabel ───────────────────────────────────────────────
export function SectionLabel({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <span style={{ color: T.muted, fontSize: 12, fontWeight: 700, letterSpacing: 0.3 }}>
        {children}
      </span>
      {action}
    </div>
  );
}

// ── Pill ───────────────────────────────────────────────────────
export function Pill({
  children, tone = 'neutral', icon,
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}) {
  const { fg, bg } = toneColors(tone);
  return (
    <span
      className="inline-flex items-center gap-1"
      style={{
        background: bg,
        color: fg,
        borderRadius: RADIUS.pill,
        padding: '3px 10px',
        fontSize: 11,
        fontWeight: 700,
        whiteSpace: 'nowrap',
      }}
    >
      {icon}
      {children}
    </span>
  );
}

// ── Badge (نقطة حالة + نصّ) ─────────────────────────────────────
export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  const { fg } = toneColors(tone);
  return (
    <span className="inline-flex items-center gap-1.5" style={{ fontSize: 11, color: T.muted, fontWeight: 600 }}>
      <span style={{ width: 7, height: 7, borderRadius: 999, background: fg, flexShrink: 0 }} />
      {children}
    </span>
  );
}

// ── StatBox (تسمية + قيمة كبيرة + وحدة) ─────────────────────────
export function StatBox({
  label, value, unit, color = T.ink, icon,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  color?: string;
  icon?: ReactNode;
}) {
  return (
    <div
      className="text-center"
      style={{ background: T.card2, borderRadius: RADIUS.sm, padding: '10px 6px' }}
    >
      {icon && <div className="flex justify-center mb-1" style={{ color }}>{icon}</div>}
      <div style={{ color, fontWeight: 800, fontSize: 16, lineHeight: 1.1 }}>
        {value}
        {unit && <span style={{ fontSize: 10, fontWeight: 600, marginInlineStart: 2 }}>{unit}</span>}
      </div>
      <div style={{ color: T.muted, fontSize: 10, marginTop: 3 }}>{label}</div>
    </div>
  );
}

// ── ProgressBar ────────────────────────────────────────────────
export function ProgressBar({
  value, color = T.green, height = 6,
}: {
  value: number; // [0..1]
  color?: string;
  height?: number;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div style={{ background: T.line, borderRadius: 999, height, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 999, transition: 'width .4s' }} />
    </div>
  );
}

// ── Row (صفّ: تسمية ⟵ قيمة، مع سهم اختياريّ) ────────────────────
export function Row({
  label, value, icon, onClick, tone,
}: {
  label: ReactNode;
  value?: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
  tone?: Tone;
}) {
  const color = tone ? toneColors(tone).fg : T.ink;
  return (
    <div
      onClick={onClick}
      onKeyDown={keyActivate(onClick)}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      className="flex items-center gap-3 py-2.5"
      style={{ cursor: onClick ? 'pointer' : undefined, borderBottom: `1px solid ${T.line}` }}
    >
      {icon && <span style={{ color: T.muted, flexShrink: 0 }}>{icon}</span>}
      <span style={{ color: T.brownSoft, fontSize: 13, flex: 1 }}>{label}</span>
      {value != null && <span style={{ color, fontSize: 13, fontWeight: 700 }}>{value}</span>}
      {/* في RTL «التقدّم» يتّجه يساراً ⇒ ChevronLeft للإشارة «افتح» */}
      {onClick && <ChevronLeft style={{ width: 16, height: 16, color: T.faint, flexShrink: 0 }} />}
    </div>
  );
}

// ── TabBar (تبويبات أفقيّة) ─────────────────────────────────────
export function TabBar<TId extends string>({
  tabs, active, onChange,
}: {
  tabs: { id: TId; label: string; icon?: ReactNode }[];
  active: TId;
  onChange: (id: TId) => void;
}) {
  return (
    <div
      className="flex items-center gap-1 overflow-x-auto"
      style={{ borderBottom: `1px solid ${T.line}` }}
    >
      {tabs.map((tab) => {
        const on = tab.id === active;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className="inline-flex items-center gap-1.5 whitespace-nowrap"
            style={{
              padding: '10px 12px',
              fontSize: 13,
              fontWeight: on ? 800 : 600,
              color: on ? T.gold : T.muted,
              borderBottom: on ? `2px solid ${T.gold}` : '2px solid transparent',
              background: 'transparent',
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

// ── FAB (زرّ إجراء عائم) ────────────────────────────────────────
export function FAB({ icon, onClick, label }: { icon: ReactNode; onClick?: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="inline-flex items-center justify-center gap-2"
      style={{
        background: T.gold,
        color: '#fff',
        borderRadius: RADIUS.pill,
        padding: label ? '12px 18px' : 14,
        boxShadow: '0 6px 18px rgba(232,160,32,.35)',
        border: 'none',
        cursor: 'pointer',
        fontWeight: 800,
        fontSize: 14,
      }}
    >
      {icon}
      {label}
    </button>
  );
}

// ── Button (زرّ إجراء أساسيّ · CTA) ─────────────────────────────
// زرّ ممتلئ بعرض كامل افتراضيّاً (نمط الكابينة). tone أخضر (تأكيد) أو ذهبيّ
// (إجراء/إعادة). الحالة المعطّلة تُفقِد اللون والنقر. style لضبط التباعد.
export function Button({
  children, onClick, disabled, tone = 'green', full = true, style,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: 'green' | 'gold';
  full?: boolean;
  style?: CSSProperties;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        width: full ? '100%' : undefined,
        padding: '11px 14px', borderRadius: RADIUS.md, border: 'none',
        background: disabled ? T.line : tone === 'gold' ? T.gold : T.green,
        color: disabled ? T.muted : '#fff',
        fontSize: 14, fontWeight: 800,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...style,
      }}
    >
      {children}
    </button>
  );
}

// ── BottomSheet (لوح منزلق سفليّ) ───────────────────────────────
export function BottomSheet({
  open, onClose, title, children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      style={{ background: 'rgba(44,26,14,.45)' }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: T.cream,
          width: '100%',
          maxWidth: 420,
          borderTopLeftRadius: RADIUS.lg,
          borderTopRightRadius: RADIUS.lg,
          padding: 16,
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
      >
        <div style={{ width: 40, height: 4, background: T.line, borderRadius: 999, margin: '0 auto 12px' }} />
        {title && (
          <h3 style={{ color: T.ink, fontWeight: 800, fontSize: 16, marginBottom: 12, textAlign: 'center' }}>
            {title}
          </h3>
        )}
        {children}
      </div>
    </div>
  );
}
