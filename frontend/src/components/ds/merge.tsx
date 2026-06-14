// ═══════════════════════════════════════════════════════════════
// SAHOOL — Unified Design System · مكوّنات الدمج (Merge Components)
// ───────────────────────────────────────────────────────────────
// أنماط عرض مقتبسة من «Operations Center» (لا علامته) فوق ذرّات FieldView
// في atoms.tsx — تجسيد UI_DESIGN_SPEC_UNIFIED.md. واعية RTL، مكتوبة الأنواع،
// تُبنى وتُفحَص بـtsc. بلا بيانات وهميّة: المكوّن يعرض ما يُمرَّر إليه فقط؛
// القيم الغائبة تُعرَض «—»/«غير متاح» لا ملفّقة (مسؤوليّة المستدعي).
// ═══════════════════════════════════════════════════════════════
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react';
import { T, RADIUS, toneColors, resourceColor, type Tone, type CmapId, CMAP } from './tokens';

function keyActivate(onClick?: () => void) {
  if (!onClick) return undefined;
  return (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
  };
}

// ── RadialGauge ── عدّاد نصف-قطريّ (وقود/DEF/إنجاز…) ─────────────
// pct قد يكون null ⇒ يُعرَض «—» (مورد غير متاح) لا حلقة مضلّلة.
export function RadialGauge({
  pct, label, size = 56, stroke = 6, color,
}: {
  pct: number | null | undefined;
  label?: string;
  size?: number;
  stroke?: number;
  color?: string;
}) {
  const has = typeof pct === 'number' && Number.isFinite(pct);
  const v = has ? Math.max(0, Math.min(100, pct as number)) : 0;
  const r = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;
  const c = color ?? (has ? resourceColor(v) : T.faint);
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ position: 'relative', display: 'inline-flex' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={T.line} strokeWidth={stroke} />
          {has && (
            <circle
              cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth={stroke}
              strokeDasharray={circ} strokeDashoffset={circ * (1 - v / 100)} strokeLinecap="round"
            />
          )}
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: size * 0.22, fontWeight: 800, color: has ? c : T.faint }}>
            {has ? `${Math.round(v)}%` : '—'}
          </span>
        </div>
      </div>
      {label && <div style={{ fontSize: 10, color: T.muted, marginTop: 2 }}>{label}</div>}
    </div>
  );
}

// ── StatGrid ── شبكة إحصاءات سريعة ──────────────────────────────
export function StatGrid({
  items, cols = 4,
}: {
  items: { label: string; value: ReactNode; unit?: string; color?: string; icon?: ReactNode }[];
  cols?: number;
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 6, textAlign: 'center' }}>
      {items.map((s, i) => (
        <div key={i} style={{ padding: '8px 4px', background: T.card2, borderRadius: RADIUS.sm }}>
          {s.icon && <div style={{ fontSize: 16 }}>{s.icon}</div>}
          <div style={{ fontWeight: 800, fontSize: 18, color: s.color ?? T.ink }}>{s.value}</div>
          <div style={{ fontSize: 10, color: T.muted }}>{s.label}</div>
          {s.unit && <div style={{ fontSize: 9, color: T.faint }}>{s.unit}</div>}
        </div>
      ))}
    </div>
  );
}

// ── AlertChip ── شريحة تنبيه مصنّفة (حرِج/تحذير/عطل/معلومة) ──────
const ALERT_ICON: Record<string, string> = {
  danger: '🔴', warn: '🟡', dtc: '⚠', info: 'ℹ', ok: '✓',
};
export function AlertChip({ type = 'info', label }: { type?: 'danger' | 'warn' | 'dtc' | 'info' | 'ok'; label: ReactNode }) {
  const tone: Tone = type === 'danger' ? 'danger' : type === 'warn' || type === 'dtc' ? 'warn' : type === 'ok' ? 'ok' : 'info';
  const { fg, bg } = toneColors(tone);
  return (
    <div className="flex items-center gap-2" style={{ background: bg, borderRadius: RADIUS.sm, padding: '6px 10px', marginBottom: 6 }}>
      <span style={{ fontSize: 13 }}>{ALERT_ICON[type] ?? 'ℹ'}</span>
      <span style={{ fontSize: 12, color: fg, fontWeight: 600 }}>{label}</span>
    </div>
  );
}

// ── ExpandableCard ── بطاقة مراقبة قابلة للطيّ ──────────────────
export function ExpandableCard({
  header, children, expanded, onToggle,
}: {
  header: ReactNode;
  children: ReactNode;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.line}`, borderRadius: RADIUS.md, padding: 14, marginBottom: 10 }}>
      <div
        onClick={onToggle}
        onKeyDown={keyActivate(onToggle)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        className="flex items-center gap-2"
        style={{ cursor: 'pointer' }}
      >
        <div style={{ flex: 1 }}>{header}</div>
        <span style={{ color: T.muted, fontSize: 13 }}>{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.card2}` }}>{children}</div>
      )}
    </div>
  );
}

// ── Stepper ── معالج خطوات (اختر ← العمليّة ← الإسناد ← الإرسال) ──
export function Stepper({
  steps, active, onStep,
}: {
  steps: string[];
  active: number; // 1-based
  onStep?: (n: number) => void;
}) {
  return (
    <div className="flex" role="navigation">
      {steps.map((s, i) => {
        const n = i + 1;
        const done = active > n;
        const current = active === n;
        return (
          <div
            key={s}
            onClick={onStep ? () => onStep(n) : undefined}
            onKeyDown={onStep ? keyActivate(() => onStep(n)) : undefined}
            role={onStep ? 'button' : undefined}
            tabIndex={onStep ? 0 : undefined}
            className="flex flex-col items-center"
            style={{ flex: 1, cursor: onStep ? 'pointer' : 'default' }}
          >
            <div style={{
              width: 24, height: 24, borderRadius: '50%',
              background: done ? T.gold : current ? T.green : T.card2,
              color: done || current ? '#fff' : T.faint,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 800,
            }}>
              {done ? '✓' : n}
            </div>
            <div style={{ fontSize: 9, marginTop: 3, color: current ? T.green : T.faint }}>{s}</div>
          </div>
        );
      })}
    </div>
  );
}

// ── LayerSwitcher ── مبدّل طبقات الخريطة/التحليل ────────────────
export function LayerSwitcher<TId extends string>({
  layers, active, onChange,
}: {
  layers: { id: TId; label: string; icon?: ReactNode }[];
  active: TId;
  onChange: (id: TId) => void;
}) {
  return (
    <div className="flex gap-1" style={{ overflowX: 'auto' }}>
      {layers.map((l) => {
        const on = active === l.id;
        return (
          <button
            key={l.id}
            type="button"
            onClick={() => onChange(l.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '6px 12px', borderRadius: RADIUS.pill, border: 'none', cursor: 'pointer',
              whiteSpace: 'nowrap', fontSize: 12, fontWeight: on ? 700 : 500,
              background: on ? T.green : T.card2, color: on ? '#fff' : T.ink,
            }}
          >
            {l.icon}{l.label}
          </button>
        );
      })}
    </div>
  );
}

// ── ColormapLegend ── مفتاح ألوان الطبقة ────────────────────────
export function ColormapLegend({
  cmap, title, lowLabel = 'منخفض', highLabel = 'مرتفع',
}: {
  cmap: CmapId;
  title?: string;
  lowLabel?: string;
  highLabel?: string;
}) {
  const colors = CMAP[cmap];
  return (
    <div style={{ background: 'rgba(0,0,0,.72)', borderRadius: RADIUS.sm, padding: '6px 10px', display: 'inline-block' }}>
      {title && <div style={{ color: '#fff', fontSize: 10, fontWeight: 700, marginBottom: 4 }}>{title}</div>}
      <div className="flex" style={{ gap: 2 }}>
        {colors.map((c, i) => <div key={i} style={{ width: 16, height: 10, background: c, borderRadius: 2 }} />)}
      </div>
      <div className="flex justify-between" style={{ fontSize: 9, color: 'rgba(255,255,255,.7)', marginTop: 2 }}>
        <span>{lowLabel}</span><span>{highLabel}</span>
      </div>
    </div>
  );
}

// ── MachineMarker ── مؤشّر آلة على الخريطة (مع نبض الحالة) ───────
const MARKER_TONE: Record<string, string> = {
  working: T.ok, idling: T.warn, transporting: T.info, offline: T.faint,
};
export function MachineMarker({
  icon, status = 'offline', alert = false, onClick, style,
}: {
  icon: ReactNode;
  status?: 'working' | 'idling' | 'transporting' | 'offline';
  alert?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}) {
  return (
    <div
      onClick={onClick}
      onKeyDown={keyActivate(onClick)}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{ position: 'relative', cursor: onClick ? 'pointer' : 'default', ...style }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        background: MARKER_TONE[status] ?? T.faint, border: `3px solid ${T.card}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, boxShadow: '0 2px 8px rgba(0,0,0,.35)',
      }}>
        {icon}
      </div>
      {alert && (
        <div style={{
          position: 'absolute', top: -4, insetInlineEnd: -4, width: 14, height: 14, borderRadius: '50%',
          background: T.danger, border: '2px solid #fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <span style={{ fontSize: 8, color: '#fff', fontWeight: 900 }}>!</span>
        </div>
      )}
    </div>
  );
}

// ── BottomTabBar ── شريط الوجهات الستّ (موبايل أوّلاً، RTL) ──────
export function BottomTabBar<TId extends string>({
  tabs, active, onChange,
}: {
  tabs: { id: TId; label: string; icon?: ReactNode }[];
  active: TId;
  onChange: (id: TId) => void;
}) {
  return (
    <div className="flex" style={{ background: T.card, borderTop: `1px solid ${T.line}`, padding: '4px 0 10px', flexShrink: 0 }}>
      {tabs.map((t) => {
        const on = active === t.id;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className="flex flex-col items-center"
            style={{ flex: 1, background: 'none', border: 'none', cursor: 'pointer', gap: 2, padding: '4px 2px' }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: RADIUS.sm,
              background: on ? T.green : 'transparent', color: on ? '#fff' : T.muted,
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
            }}>
              {t.icon}
            </div>
            <span style={{ fontSize: 9, color: on ? T.green : T.muted, fontWeight: on ? 700 : 400 }}>{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}
