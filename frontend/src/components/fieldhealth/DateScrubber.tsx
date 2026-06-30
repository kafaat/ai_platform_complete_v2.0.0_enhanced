// ═══════════════════════════════════════════════════════════════
// SAHOOL — صحّة الحقل (Field Health) · شريط زمنيّ لتمرير تواريخ الصور
// ───────────────────────────────────────────────────────────────
// شريط/منزلق زمنيّ (date scrubber) بنمط FieldView لتصفّح تواريخ اكتساب
// الصور (Sentinel-2 COG) الحقيقيّة. التواريخ تأتي حصراً من
// raster-service (useFieldTimeseries.points[].datetime) — لا تواريخ
// مُختلَقة. عند غياب التواريخ نعرض حالة فارغة صريحة (لا منزلق وهميّ).
//
// كلّ نقطة تحمل (date · value · cloud؟). نسبة الغيوم (cloudy_pct) متاحة
// من raster فقط؛ في مصدر vegetation البديل تكون null فلا نُلوّن الغيوم.
// التمرير يبثّ التاريخ المختار للأعلى (onSelect) فيقود طبقة الخريطة.
// RTL · framer-motion لانتقال السهم.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Calendar, CloudSun } from 'lucide-react';
import { T, RADIUS } from '../ds';

export interface ScrubberPoint {
  date: string;
  value: number;
  cloud: number | null;
  // رابط مُصغَّرة صورة الحقل لهذا التاريخ (cdse-thumbnail) — اختياريّ (يسقط لتدرّج لونيّ).
  thumbUrl?: string | null;
  // فرق المؤشّر عن التاريخ الأسبق (لشارة التغيّر) — اختياريّ.
  delta?: number | null;
}

// تنسيق التاريخ بالعربيّة: "2026-02-23" → "23 فبراير". منتصف اليوم لتفادي إزاحة TZ.
function formatArabicDate(iso: string): string {
  try {
    const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
    if (Number.isNaN(d.getTime())) return iso.slice(5);
    return d.toLocaleDateString('ar', { day: 'numeric', month: 'long' });
  } catch {
    return iso.slice(5);
  }
}

export interface DateScrubberProps {
  points: ScrubberPoint[];
  selected: string;
  onSelect: (date: string) => void;
  // نسبة الغيوم التي يُعتبر اليوم عندها «غائماً» (عرض فقط — لا تصفية هنا).
  cloudThreshold?: number;
  // وسم اختياريّ بجانب العنوان (مثل مصدر البيانات).
  badge?: React.ReactNode;
}

// لون القيمة (نمط NDVI صحّيّ) — أخضر مرتفع، أحمر منخفض.
function valueColor(v: number): string {
  if (v > 0.7) return '#16a34a';
  if (v > 0.5) return '#65a30d';
  if (v > 0.3) return '#ca8a04';
  if (v > 0.1) return '#f97316';
  return '#dc2626';
}

export default function DateScrubber({
  points,
  selected,
  onSelect,
  cloudThreshold = 50,
  badge,
}: DateScrubberProps) {
  // فهرس التاريخ المختار ضمن النقاط (للمنزلق) — -1 إن لم يوجد.
  const selectedIdx = useMemo(
    () => points.findIndex((p) => p.date === selected),
    [points, selected],
  );

  const hasPoints = points.length > 0;
  // المنزلق صالح فقط بنقطتين فأكثر (range بمدى حقيقيّ) — وإلّا نكتفي بالبلاطات.
  const sliderUsable = points.length >= 2;

  return (
    <div
      dir="rtl"
      style={{
        background: T.card,
        border: `1px solid ${T.line}`,
        borderRadius: RADIUS.md,
        padding: 12,
      }}
    >
      <div className="flex items-center gap-2" style={{ marginBottom: 10 }}>
        <Calendar style={{ width: 16, height: 16, color: T.green }} />
        <span style={{ fontSize: 12, fontWeight: 700, color: T.ink }}>الشريط الزمنيّ</span>
        {badge}
        <span style={{ marginInlineStart: 'auto', fontSize: 11, color: T.muted }}>
          {hasPoints ? `${points.length} اكتساب` : 'لا تواريخ'}
        </span>
      </div>

      {!hasPoints ? (
        <p style={{ color: T.muted, fontSize: 12, padding: '10px 0', textAlign: 'center', margin: 0 }}>
          لا توجد تواريخ صور مُعالَجة بعد — شغّل «تحليل الآن» لمعالجة مشاهد Sentinel-2.
        </p>
      ) : (
        <>
          {/* منزلق التمرير (range) — يقفز بين تواريخ COG الحقيقيّة فقط */}
          {sliderUsable && (
            <div style={{ marginBottom: 10 }}>
              <input
                type="range"
                min={0}
                max={points.length - 1}
                step={1}
                value={selectedIdx >= 0 ? selectedIdx : points.length - 1}
                onChange={(e) => {
                  const p = points[parseInt(e.target.value, 10)];
                  if (p?.date) onSelect(p.date);
                }}
                style={{ width: '100%', accentColor: T.green }}
                aria-label="تمرير تاريخ الصورة"
              />
              <div className="flex justify-between" style={{ fontSize: 9, color: T.faint, marginTop: 2 }}>
                <span>{points[points.length - 1]?.date?.slice(5) ?? ''}</span>
                <span>{points[0]?.date?.slice(5) ?? ''}</span>
              </div>
            </div>
          )}

          {/* بطاقات السجلّ الزمنيّ (تمرير أفقيّ): التاريخ أعلى · صورة الحقل · المتوسّط + التغيّر */}
          <div className="flex gap-2.5" style={{ overflowX: 'auto', paddingBottom: 6 }}>
            {points.map((p, i) => {
              const c = valueColor(p.value);
              const isSel = !!p.date && p.date === selected;
              const cloudy = typeof p.cloud === 'number' && p.cloud > cloudThreshold;
              const hasDelta = typeof p.delta === 'number' && Math.abs(p.delta as number) >= 0.005;
              const up = (p.delta ?? 0) >= 0;
              return (
                <button
                  key={p.date || i}
                  type="button"
                  onClick={() => p.date && onSelect(p.date)}
                  title={p.date ? (cloudy ? `${p.date} · غائم (${p.cloud}%)` : p.date) : ''}
                  style={{
                    flexShrink: 0,
                    width: 96,
                    cursor: 'pointer',
                    textAlign: 'center',
                    borderRadius: RADIUS.md,
                    padding: '8px 6px',
                    background: isSel ? T.card : T.card2,
                    border: `2px solid ${isSel ? T.ink : 'transparent'}`,
                    boxShadow: isSel ? '0 2px 8px rgba(0,0,0,.25)' : 'none',
                    position: 'relative',
                    transition: 'all .2s',
                  }}
                >
                  {/* التاريخ (أعلى البطاقة) */}
                  <div style={{ fontSize: 11, fontWeight: 700, color: isSel ? T.ink : T.muted, marginBottom: 6 }}>
                    {p.date ? formatArabicDate(p.date) : ''}
                  </div>

                  {/* صورة الحقل لهذا التاريخ (تسقط لتدرّج لونيّ عند تعذّرها) */}
                  <div
                    style={{
                      height: 56,
                      borderRadius: RADIUS.sm,
                      marginBottom: 6,
                      border: `1px solid ${isSel ? c : T.line}`,
                      background: `linear-gradient(135deg,${c}33,${c}77,${c}33)`,
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                  >
                    {p.thumbUrl && (
                      <img
                        src={p.thumbUrl}
                        alt=""
                        loading="lazy"
                        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                        style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                      />
                    )}
                    {cloudy && (
                      <CloudSun
                        style={{ position: 'absolute', top: 3, insetInlineStart: 3, width: 12, height: 12, color: '#fde68a' }}
                      />
                    )}
                  </div>

                  {/* المتوسّط + شارة التغيّر */}
                  <div className="flex items-center justify-center gap-1">
                    <span style={{ fontSize: 15, fontWeight: 800, color: c }}>{p.value.toFixed(2)}</span>
                    {hasDelta && (
                      <span
                        style={{
                          fontSize: 9, fontWeight: 700, padding: '1px 4px', borderRadius: 4,
                          color: up ? '#16a34a' : '#dc2626',
                          background: up ? '#16a34a22' : '#dc262622',
                        }}
                      >
                        {up ? '+' : ''}{(p.delta as number).toFixed(2)}
                      </span>
                    )}
                  </div>
                  {isSel && (
                    <motion.div
                      layoutId="scrubber-marker"
                      style={{
                        position: 'absolute', insetInlineEnd: 6, top: 6,
                        width: 7, height: 7, borderRadius: '50%', background: c,
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
