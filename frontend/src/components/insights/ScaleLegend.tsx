// ═══════════════════════════════════════════════════════════════
// SAHOOL — insights/ScaleLegend
// سلالم بصريّة قابلة لإعادة الاستخدام لقراءة المؤشّرات والطقس والريّ:
//   • GradientScale  — شريط متدرّج متّصل (min→max) + وحدة + علامة قيمة حاليّة اختياريّة.
//   • SegmentedScale — نطاقات لونيّة منفصلة بعناوين (NDVI/إلحاح الريّ/مخاطر الأمراض…)
//                       مع إبراز النطاق النشط وتلميح قراءة.
// خفيفة (React + أنماط سطريّة) ومتّسقة مع الثيم الداكن. الأرقام LTR ضمن حاوية قد تكون RTL.
// ═══════════════════════════════════════════════════════════════

export interface GradientScaleProps {
  /** ألوان متدرّجة من اليسار (min) إلى اليمين (max). */
  colors: string[];
  min: number;
  max: number;
  unit?: string;
  title?: string;
  /** قيمة حاليّة تُعلَّم على الشريط (اختياريّة). */
  value?: number | null;
  /** علامات وسطيّة اختياريّة (قيم ضمن [min,max]). */
  ticks?: number[];
  height?: number;
  formatValue?: (v: number) => string;
  className?: string;
}

function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

const defaultFmt = (v: number): string =>
  Number.isInteger(v) ? String(v) : v.toFixed(1);

/** شريط متدرّج متّصل مع وحدة وحدّين وعلامة قيمة حاليّة اختياريّة. */
export function GradientScale({
  colors,
  min,
  max,
  unit,
  title,
  value,
  ticks,
  height = 12,
  formatValue = defaultFmt,
  className,
}: GradientScaleProps) {
  const safeColors = colors.length >= 2 ? colors : [colors[0] ?? '#64748b', colors[0] ?? '#64748b'];
  const gradient = `linear-gradient(90deg, ${safeColors.join(', ')})`;
  const span = max - min || 1;
  const valuePct =
    typeof value === 'number' && Number.isFinite(value)
      ? clamp01((value - min) / span) * 100
      : null;

  return (
    <div className={className} style={{ width: '100%' }}>
      {(title || unit) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
          {title && <span style={{ fontSize: 12, fontWeight: 700, color: '#e2e8f0' }}>{title}</span>}
          {unit && <span style={{ fontSize: 11, color: '#94a3b8' }}>{unit}</span>}
        </div>
      )}
      <div style={{ position: 'relative' }}>
        <div
          role="img"
          aria-label={`scale ${title ?? ''} ${formatValue(min)}–${formatValue(max)}${unit ? ' ' + unit : ''}`}
          style={{ height, borderRadius: 999, background: gradient, border: '1px solid rgba(255,255,255,.14)' }}
        />
        {valuePct !== null && (
          <div
            data-testid="scale-value-marker"
            style={{
              position: 'absolute',
              top: -3,
              left: `${valuePct}%`,
              transform: 'translateX(-50%)',
              width: 3,
              height: height + 6,
              borderRadius: 2,
              background: '#f8fafc',
              boxShadow: '0 0 0 1px rgba(0,0,0,.55)',
            }}
          />
        )}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3, fontSize: 10, color: '#64748b', direction: 'ltr' }}>
        <span>{formatValue(min)}</span>
        {ticks?.map((t) => (
          <span key={t}>{formatValue(t)}</span>
        ))}
        <span>{formatValue(max)}</span>
      </div>
      {valuePct !== null && (
        <div style={{ marginTop: 2, fontSize: 11, color: '#cbd5e1', textAlign: 'center' }}>
          القيمة الحاليّة: <b style={{ color: '#f8fafc' }}>{formatValue(value as number)}{unit ? ` ${unit}` : ''}</b>
        </div>
      )}
    </div>
  );
}

export interface ScaleBand {
  label: string;
  color: string;
  /** الحدّ الأدنى للنطاق (شامل) — يُستعمَل لاختيار النطاق النشط من قيمة. */
  from?: number;
  /** الحدّ الأعلى للنطاق (غير شامل). */
  to?: number;
  /** تلميح قراءة قصير يظهر للنطاق النشط. */
  hint?: string;
}

export interface SegmentedScaleProps {
  /** النطاقات بالترتيب (يُعرَض كما هو). */
  bands: ScaleBand[];
  title?: string;
  /** إبراز نطاق بعينه بمؤشّره. */
  activeIndex?: number;
  /** قيمة تُحدِّد النطاق النشط آليّاً عبر from/to (إن لم يُمرَّر activeIndex). */
  value?: number | null;
  unit?: string;
  className?: string;
}

/** يحدّد فهرس النطاق الذي تقع فيه القيمة (عبر from/to)، أو -1. */
export function bandIndexForValue(bands: ScaleBand[], value: number | null | undefined): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return -1;
  for (let i = 0; i < bands.length; i += 1) {
    const b = bands[i];
    const lo = b.from ?? -Infinity;
    const hi = b.to ?? Infinity;
    if (value >= lo && value < hi) return i;
  }
  return -1;
}

/** نطاقات لونيّة منفصلة بعناوين + إبراز النطاق النشط وتلميح قراءته. */
export function SegmentedScale({ bands, title, activeIndex, value, unit, className }: SegmentedScaleProps) {
  const active = activeIndex ?? bandIndexForValue(bands, value);
  const activeBand = active >= 0 && active < bands.length ? bands[active] : null;

  return (
    <div className={className} style={{ width: '100%' }}>
      {(title || unit) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
          {title && <span style={{ fontSize: 12, fontWeight: 700, color: '#e2e8f0' }}>{title}</span>}
          {unit && <span style={{ fontSize: 11, color: '#94a3b8' }}>{unit}</span>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 3, alignItems: 'stretch' }}>
        {bands.map((b, i) => {
          const isActive = i === active;
          return (
            <div
              key={`${b.label}-${i}`}
              data-testid={isActive ? 'scale-band-active' : 'scale-band'}
              title={b.hint || b.label}
              style={{ flex: 1, textAlign: 'center' }}
            >
              <div
                style={{
                  height: isActive ? 16 : 11,
                  borderRadius: 6,
                  background: b.color,
                  border: isActive ? '2px solid #f8fafc' : '1px solid rgba(0,0,0,.25)',
                  boxShadow: isActive ? '0 2px 8px rgba(0,0,0,.45)' : 'none',
                  transition: 'height .15s ease',
                }}
              />
              <div
                style={{
                  marginTop: 3,
                  fontSize: 10,
                  lineHeight: 1.2,
                  fontWeight: isActive ? 800 : 600,
                  color: isActive ? '#f8fafc' : '#94a3b8',
                }}
              >
                {b.label}
              </div>
            </div>
          );
        })}
      </div>
      {activeBand?.hint && (
        <div style={{ marginTop: 6, fontSize: 11, lineHeight: 1.5, color: '#cbd5e1' }}>
          <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: activeBand.color, marginInlineEnd: 6 }} />
          {activeBand.hint}
        </div>
      )}
    </div>
  );
}
