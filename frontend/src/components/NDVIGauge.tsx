interface NDVIGaugeProps {
  value: number;      // 0 – 1
  size?: number;      // px, default 180
}

function ndviLabel(v: number) {
  if (v >= 0.70) return { text: 'ممتاز',  color: '#16a34a' };
  if (v >= 0.50) return { text: 'جيد',    color: '#65a30d' };
  if (v >= 0.30) return { text: 'متوسط',  color: '#ca8a04' };
  if (v >= 0.10) return { text: 'ضعيف',   color: '#f97316' };
  return               { text: 'حرج',    color: '#dc2626' };
}

// Returns SVG arc path for a semicircle gauge
function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const x1 = cx + r * Math.cos(toRad(startDeg));
  const y1 = cy + r * Math.sin(toRad(startDeg));
  const x2 = cx + r * Math.cos(toRad(endDeg));
  const y2 = cy + r * Math.sin(toRad(endDeg));
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

export function NDVIGauge({ value, size = 180 }: NDVIGaugeProps) {
  const cx = size / 2;
  const cy = size * 0.58;
  const r  = size * 0.38;
  const sw = size * 0.08;

  // Gauge spans 180° (from 180° to 360°/0°)
  const startDeg = 180;
  const totalDeg = 180;
  const fillDeg  = startDeg + Math.min(Math.max(value, 0), 1) * totalDeg;

  const { text, color } = ndviLabel(value);

  // Needle
  const needleDeg = startDeg + value * totalDeg;
  const needleRad = (needleDeg * Math.PI) / 180;
  const nx = cx + (r - sw / 2) * Math.cos(needleRad);
  const ny = cy + (r - sw / 2) * Math.sin(needleRad);

  return (
    <div className="flex flex-col items-center gap-1" dir="ltr">
      <svg width={size} height={size * 0.65} viewBox={`0 0 ${size} ${size * 0.65}`}>
        {/* Track */}
        <path
          d={arcPath(cx, cy, r, 180, 360)}
          fill="none"
          stroke="#334155"
          strokeWidth={sw}
          strokeLinecap="round"
        />
        {/* Fill */}
        {value > 0 && (
          <path
            d={arcPath(cx, cy, r, 180, fillDeg)}
            fill="none"
            stroke={color}
            strokeWidth={sw}
            strokeLinecap="round"
          />
        )}
        {/* Needle */}
        <line
          x1={cx} y1={cy}
          x2={nx} y2={ny}
          stroke="#f1f5f9"
          strokeWidth={size * 0.012}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={size * 0.03} fill="#f1f5f9" />

        {/* Value text */}
        <text x={cx} y={cy - r * 0.25} textAnchor="middle"
          fontSize={size * 0.14} fontWeight="700" fill="#f1f5f9">
          {value.toFixed(3)}
        </text>
        <text x={cx} y={cy - r * 0.02} textAnchor="middle"
          fontSize={size * 0.075} fill={color}>
          {text}
        </text>

        {/* Scale labels */}
        <text x={cx - r - sw / 2} y={cy + size * 0.04} textAnchor="middle"
          fontSize={size * 0.062} fill="#64748b">0</text>
        <text x={cx + r + sw / 2} y={cy + size * 0.04} textAnchor="middle"
          fontSize={size * 0.062} fill="#64748b">1</text>
      </svg>
      <p className="text-xs text-slate-400 font-medium">مؤشر الغطاء النباتي — NDVI</p>
    </div>
  );
}
