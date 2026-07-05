// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · وضع التضاريس ثلاثيّ الأبعاد (Terrain 3D) — كسول
// ───────────────────────────────────────────────────────────────
// هذا المكوّن هدفُه نهائيّاً: عرض MapLibre GL ثلاثيّ الأبعاد يكسو حدود الحقل
// فوق نموذج ارتفاع رقميّ (DEM) + تظليل تضاريس (hillshade)، مع تراكب بلاطات
// المؤشّرات/الصور الحاليّة (نفس روابط XYZ المستخدمة في 2D).
//
// لماذا «جذع» (stub) اليوم ولِمَ لم يُشحَن العرض ثلاثيّ الأبعاد كاملاً:
//   • لا توجد خدمة DEM/hillshade داخل المنصّة: نقطة النهاية
//     `/api/v1/fields/{id}/terrain` غير موجودة في الواجهة الخلفيّة — التضاريس
//     تصل اليوم *كبيانات وصفيّة* مضمَّنة في `GET /api/v1/fields/{id}/workspace`
//     (ارتفاع/ميل/جهة فقط، لا بلاطات نقش). شحن عرض ثلاثيّ الأبعاد يستلزم مصدر
//     بلاطات terrain-RGB (راستر ارتفاع) لا تُنتجه المنصّة بعد.
//   • تكليف المرحلة 1 صريح: «إن تعذّر إبقاء `npm run build` أخضر ضمن النطاق،
//     اشحن خريطة 2D واترك زرّ 3D جذعاً كسولاً بـTODO واضح» — لا تُعَطَّل
//     المرحلة على 3D. لذا نتجنّب إضافة تبعيّة `maplibre-gl` الثقيلة بلا مصدر
//     بيانات حقيقيّ يبرّرها (صدق البيانات: لا نخترع نقشاً مزيّفاً).
//
// مع ذلك يبقى المكوّن **مقسوماً بالكود** (React.lazy في MapHub) فلا يُثقِل
// الحزمة الأساسيّة، ويحترم `prefers-reduced-motion` (لا حركة/دوران تلقائيّ).
//
// TODO(maphub-3d): حين تتوفّر بلاطات DEM/terrain-RGB + hillshade من الراستر:
//   1) `npm install maplibre-gl` (مفتوح المصدر، بلا توكن) ثمّ `npm audit`.
//   2) استبدل هذا الجذع بـ<Map> من maplibre-gl يضبط `terrain` على مصدر
//      raster-dem، ويكسو حدود الحقل (GeoJSON) كطبقة fill-extrusion/line،
//      ويضيف بلاطات المؤشّر (fieldIndicatorTileUrl) كمصدر raster متراكب.
//   3) أبقِ التحميل كسولاً (هذا الملفّ) واحترم prefers-reduced-motion (ثبّت
//      pitch/bearing بلا دوران تلقائيّ حين يُفضَّل تقليل الحركة).
// ═══════════════════════════════════════════════════════════════
import { Mountain, Info } from 'lucide-react';
import { T, RADIUS } from '../ds';
import { useFieldTerrain } from '../../hooks/useApi';

export interface TerrainView3DProps {
  fieldId?: string;
  fieldName?: string;
  // بيانات التضاريس الوصفيّة المتاحة فعلاً (من workspace) — تُعرَض بصدق إن وُجدت.
  elevationM?: number | null;
  slopePct?: number | null;
  aspect?: string | null;
  height?: number | string;
}

function fmt(v: number | null | undefined, unit: string): string {
  return v == null || !Number.isFinite(v) ? '—' : `${v} ${unit}`;
}

function round1(v: number | null | undefined): number | null {
  return v == null || !Number.isFinite(v) ? null : Math.round(v * 10) / 10;
}

export default function TerrainView3D({
  fieldId,
  fieldName,
  elevationM,
  slopePct,
  aspect,
  height = 460,
}: TerrainView3DProps) {
  // إحصاءات محسوبة من DEM حقيقيّ (مقصوص على الحقل) حين تتوفّر؛ وإلّا نُبقي البيانات
  // الوصفيّة من workspace. صدق: لا نعرض رقماً لم يُرجِعه الخادم.
  const terrainQ = useFieldTerrain(fieldId);
  const t = terrainQ.data;
  const computed = !!t?.computed;
  const elevDisplay = computed ? round1(t?.elevation_m?.mean) : (elevationM ?? null);
  const slopeDisplay = computed ? round1(t?.slope_deg?.mean) : (slopePct ?? null);
  const slopeUnit = computed ? '°' : '%';
  const aspectDisplay = computed ? (t?.dominant_aspect ?? null) : (aspect ?? null);
  // مظروف صادق لتعذّر الحساب (لا DEM مُهيّأ / لا bbox) — لا نُخفيه.
  const terrainReason =
    terrainQ.isSuccess && t && !computed
      ? t.source === 'dem-not-configured'
        ? 'مصدر نموذج الارتفاع (DEM) غير مُهيّأ بعد على الخادم.'
        : t.source === 'field-bbox-unavailable'
          ? 'حدود الحقل غير متاحة لحساب التضاريس.'
          : (t.reason ?? 'تعذّر حساب التضاريس.')
      : null;
  return (
    <div
      dir="rtl"
      style={{
        height,
        borderRadius: RADIUS.md,
        border: `1px solid ${T.line}`,
        background:
          'linear-gradient(160deg, #1b2a1f 0%, #14201a 60%, #0f1813 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: 24,
        textAlign: 'center',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <Mountain style={{ width: 44, height: 44, color: '#5cbf6e' }} aria-hidden="true" />
      <div style={{ fontSize: 16, fontWeight: 800, color: '#e2e8f0' }}>
        وضع التضاريس ثلاثيّ الأبعاد
      </div>
      <p style={{ fontSize: 13, color: '#9fb3a6', lineHeight: 1.7, maxWidth: 460, margin: 0 }}>
        العرض ثلاثيّ الأبعاد (MapLibre GL على نموذج ارتفاع رقميّ + تظليل تضاريس)
        بانتظار مصدر بلاطات DEM من خدمة الراستر. لا نعرض نقشاً مزيّفاً —
        التضاريس المتاحة اليوم بيانات وصفيّة من مساحة عمل الحقل، معروضة أدناه.
      </p>

      {/* بيانات التضاريس الوصفيّة الحقيقيّة (من workspace) — لا تلفيق */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(90px, 1fr))',
          gap: 8,
          marginTop: 4,
        }}
      >
        {[
          { label: 'الارتفاع', value: fmt(elevDisplay, 'م') },
          { label: 'الميل', value: fmt(slopeDisplay, slopeUnit) },
          { label: 'الجهة', value: aspectDisplay && aspectDisplay.trim() ? aspectDisplay : '—' },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: 'rgba(13,22,17,.6)',
              borderRadius: RADIUS.sm,
              border: '1px solid #2d4a37',
              padding: '10px 8px',
            }}
          >
            <div style={{ fontSize: 18, fontWeight: 800, color: '#cdddd2' }}>{s.value}</div>
            <div style={{ fontSize: 10, color: '#8aa194', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {computed && t?.water_harvesting?.recommended_technique ? (
        <div style={{ fontSize: 11, color: '#9fb3a6', maxWidth: 460 }}>
          حصاد المياه المقترح: <b style={{ color: '#cdddd2' }}>{t.water_harvesting.recommended_technique}</b>
          {t.water_harvesting.suitability ? ` — ${t.water_harvesting.suitability}` : ''}
        </div>
      ) : terrainReason ? (
        <div style={{ fontSize: 11, color: '#c9a94a', maxWidth: 460 }}>{terrainReason}</div>
      ) : null}

      <div
        className="flex items-center gap-2"
        style={{
          marginTop: 4,
          fontSize: 11,
          color: '#7c8f82',
          background: 'rgba(0,0,0,.25)',
          borderRadius: RADIUS.pill,
          padding: '5px 12px',
        }}
      >
        <Info style={{ width: 13, height: 13 }} aria-hidden="true" />
        <span>
          {fieldName ? `${fieldName} — ` : ''}
          استخدم وضع 2D للطبقات والمقارنة والرسم والدبابيس.
        </span>
      </div>
    </div>
  );
}
