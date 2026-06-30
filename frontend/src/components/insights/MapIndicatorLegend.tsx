// ═══════════════════════════════════════════════════════════════
// SAHOOL — insights/MapIndicatorLegend
// أسطورة (legend) عموديّة أنيقة لكلّ المؤشّرات المكانيّة، تُثبَّت على يمين الخريطة
// بارتفاع متوسّط: تدرّج قيم رأسيّ (الأعلى = أعلى قيمة) + عنوان المؤشّر + دلالة
// الطرفين + حدّا المدى + علامة قيمة حاليّة اختياريّة. نمط أفضل المنصّات الزراعيّة:
// زجاج داكن، حوافّ ناعمة، تباين عالٍ للقراءة فوق صور الأقمار.
// ═══════════════════════════════════════════════════════════════

// دلالة طرفَي القيمة لكلّ مؤشّر (الأعلى/الأدنى) — مصدر واحد لكلّ المؤشّرات المدعومة.
// fallback: «مرتفع»/«منخفض» لأيّ مؤشّر غير مُعرَّف هنا (لا ينكسر).
interface IndicatorMeta { name: string; high: string; low: string }
const INDICATOR_META: Record<string, IndicatorMeta> = {
  ndvi: { name: 'NDVI', high: 'غطاء صحّي', low: 'تربة عارية' },
  gndvi: { name: 'GNDVI', high: 'خُضرة عالية', low: 'خُضرة ضعيفة' },
  ndmi: { name: 'NDMI', high: 'رطوبة عالية', low: 'جفاف' },
  ndwi: { name: 'NDWI', high: 'ماء/رطوبة', low: 'جافّ' },
  ndre: { name: 'NDRE', high: 'نيتروجين كافٍ', low: 'نقص نيتروجين' },
  msavi: { name: 'MSAVI', high: 'غطاء صحّي', low: 'تربة عارية' },
  savi: { name: 'SAVI', high: 'غطاء صحّي', low: 'تربة عارية' },
  evi: { name: 'EVI', high: 'غطاء كثيف', low: 'غطاء ضعيف' },
  salinity: { name: 'مؤشّر الملوحة', high: 'ملوحة مرتفعة', low: 'ملوحة منخفضة' },
  si: { name: 'مؤشّر الملوحة', high: 'ملوحة مرتفعة', low: 'ملوحة منخفضة' },
  moisture: { name: 'الرطوبة', high: 'رطوبة عالية', low: 'جفاف' },
};

// تدرّج RdYlGn القياسيّ من القيمة المنخفضة → المرتفعة (أحمر→أصفر→أخضر).
const RD_YL_GN_LOW_TO_HIGH = ['#a50026', '#f46d43', '#fee08b', '#d9ef8b', '#1a9850'];

function clamp01(t: number): number {
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

export interface MapIndicatorLegendProps {
  /** معرّف المؤشّر (ndvi/ndmi/salinity…). */
  index: string;
  vmin: number;
  vmax: number;
  /** true عند المؤشّرات التي «القيمة المرتفعة فيها مشكلة» (مثل الملوحة) — يقلب الألوان. */
  invert?: boolean;
  /** قيمة حاليّة (متوسّط الحقل) لإظهار علامة على السلّم — اختياريّة. */
  value?: number | null;
  /** ارتفاع شريط التدرّج (متوسّط افتراضيّاً). */
  barHeight?: number;
}

/** أسطورة مؤشّر عموديّة لليمين — تعمل لكلّ المؤشّرات عبر INDICATOR_META + invert. */
export function MapIndicatorLegend({
  index,
  vmin,
  vmax,
  invert = false,
  value,
  barHeight = 150,
}: MapIndicatorLegendProps) {
  const key = (index || '').toLowerCase();
  const meta = INDICATOR_META[key] ?? { name: (index || 'مؤشّر').toUpperCase(), high: 'مرتفع', low: 'منخفض' };
  // ألوان القيمة المنخفضة→المرتفعة؛ عند invert (القيمة المرتفعة = مشكلة) نعكسها.
  const lowToHigh = invert ? [...RD_YL_GN_LOW_TO_HIGH].reverse() : RD_YL_GN_LOW_TO_HIGH;
  // العمود: الأعلى = أعلى قيمة ⇒ التدرّج «إلى الأعلى» من لون المنخفض إلى لون المرتفع.
  const gradient = `linear-gradient(to top, ${lowToHigh.join(', ')})`;
  const span = vmax - vmin || 1;
  const valuePct = typeof value === 'number' && Number.isFinite(value) ? clamp01((value - vmin) / span) * 100 : null;
  const fmt = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2));

  return (
    <div
      dir="rtl"
      aria-label={`legend ${meta.name}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 7,
        background: 'rgba(13,22,17,.78)',
        border: '1px solid rgba(255,255,255,.16)',
        borderRadius: 16,
        padding: '12px 12px 11px',
        color: '#e8eee9',
        font: '12px system-ui,-apple-system,Segoe UI,sans-serif',
        boxShadow: '0 12px 34px rgba(0,0,0,.45)',
        backdropFilter: 'blur(10px)',
        WebkitBackdropFilter: 'blur(10px)',
        minWidth: 58,
      }}
    >
      <div style={{ fontWeight: 800, fontSize: 13, color: '#fff', letterSpacing: '.3px' }}>{meta.name}</div>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#86efac' }}>{meta.high}</div>
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 6 }}>
        {/* شريط التدرّج العموديّ + علامة القيمة الحاليّة */}
        <div style={{ position: 'relative', width: 16, height: barHeight }}>
          <div
            style={{
              width: '100%',
              height: '100%',
              borderRadius: 999,
              background: gradient,
              border: '1px solid rgba(255,255,255,.25)',
              boxShadow: 'inset 0 0 6px rgba(0,0,0,.35)',
            }}
          />
          {valuePct !== null && (
            <div
              data-testid="indicator-legend-marker"
              style={{
                position: 'absolute',
                bottom: `${valuePct}%`,
                insetInlineStart: -4,
                width: 24,
                height: 3,
                transform: 'translateY(50%)',
                background: '#fff',
                borderRadius: 2,
                boxShadow: '0 0 0 1px rgba(0,0,0,.6)',
              }}
            />
          )}
        </div>
        {/* حدّا المدى (أعلى=vmax، أسفل=vmin) */}
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: 10, color: '#cdddd2', direction: 'ltr' }}>
          <span>{fmt(vmax)}</span>
          {valuePct !== null && <span style={{ color: '#fff', fontWeight: 700 }}>{fmt(value as number)}</span>}
          <span>{fmt(vmin)}</span>
        </div>
      </div>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#fca5a5' }}>{meta.low}</div>
    </div>
  );
}
