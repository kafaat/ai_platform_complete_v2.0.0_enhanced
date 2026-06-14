// ═══════════════════════════════════════════════════════════════
// SAHOOL — مركز الخرائط الموحّد (Field Map Center) · شاشة دمج ثانية
// ───────────────────────────────────────────────────────────────
// تصهر «الأقمار الصناعيّة/المؤشّرات المكانيّة» (FieldView) مع نمط طبقات
// «Operations Center · Analyze» في كابينة واحدة: خريطة Leaflet حقيقيّة
// ببلاطات مؤشّر من raster-service، مبدّل طبقات (NDVI/NDMI/الملوحة)، مفتاح
// ألوان مطابق للطبقة، ووضع مقارنة جنباً لجنب (SideBySide) لطبقتين حقيقيّتين.
// يستهلك لبنات الدمج: LayerSwitcher · ColormapLegend · SideBySide ·
// MachineMarker. تجسيد UI_DESIGN_SPEC_UNIFIED.md §3 (الخريطة متعدّدة الطبقات).
//
// صدق البيانات: كلّ طبقة بلاطات حقيقيّة من raster-service فوق حدود الحقل
// الحقيقيّة (geometry/lat/lon من useFields). لا مواقع آليّات ملفّقة —
// المعدّات بلا إحداثيّات (فجوة موثّقة ⛔)، والأجهزة (useDevices) تُعرَض
// كمؤشّرات حالة (MachineMarker) منسوبة للحقل لا كإحداثيّات مزعومة. الحالات
// (تحميل/فراغ/خطأ) صريحة عبر StateViews الضمنيّة. شاشة قراءة فقط (معاينة دمج).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Layers, Satellite, Droplets, FlaskConical, Cpu, Columns2, Square } from 'lucide-react';
import { useFields, useDevices } from '../hooks/useApi';
import { geomToPolygon } from '../lib/geo';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import {
  T, Card, Pill, Badge, SectionLabel, Row,
  LayerSwitcher, ColormapLegend, SideBySide, MachineMarker,
} from '../components/ds';
import type { CmapId } from '../components/ds';

// ── المؤشّرات (طبقات) — مفاتيح raster-service + لوحة الألوان الموحّدة ──
// index: ما يفهمه raster-service (ndvi|ndmi|salinity). cmap: لوحة ألوان DS
// الأقرب دلاليّاً (الرطوبة→moisture، الملوحة→ec). low/highLabel للمفتاح.
type LayerId = 'ndvi' | 'ndmi' | 'salinity';
const LAYERS: {
  id: LayerId; label: string; icon: ReactNode; cmap: CmapId;
  low: string; high: string; hint: string;
}[] = [
  { id: 'ndvi', label: 'NDVI', icon: <Satellite style={{ width: 13, height: 13 }} />, cmap: 'ndvi', low: 'إجهاد', high: 'كثيف', hint: 'صحّة الغطاء النباتيّ' },
  { id: 'ndmi', label: 'NDMI', icon: <Droplets style={{ width: 13, height: 13 }} />, cmap: 'moisture', low: 'جافّ', high: 'رطب', hint: 'رطوبة المحتوى' },
  { id: 'salinity', label: 'الملوحة', icon: <FlaskConical style={{ width: 13, height: 13 }} />, cmap: 'ec', low: 'منخفضة', high: 'مرتفعة', hint: 'مؤشّر الملوحة' },
];
const layerOf = (id: LayerId) => LAYERS.find((l) => l.id === id) ?? LAYERS[0];
// خيارات LayerSwitcher مشتقّة مرّة واحدة (LAYERS ثابتة) — هويّة مصفوفة مستقرّة.
const LAYER_OPTS = LAYERS.map((l) => ({ id: l.id, label: l.label, icon: l.icon }));

interface MapField { id: string; name: string; lat: number | null; lon: number | null; geometry: any }

// نغمة/حالة مؤشّر الجهاز — online→يعمل، غير ذلك→غير متّصل (alert إن غير متّصل).
function deviceMarkerStatus(online?: boolean): 'working' | 'offline' {
  return online ? 'working' : 'offline';
}

// لوحة خريطة واحدة (خريطة حقيقيّة + مفتاح ألوان فوقها). تُعاد استخدامها مفردةً
// وداخل SideBySide. height قابل للضبط (مفرد أطول، مقارنة أقصر).
function MapPanel({
  field, polygon, fallbackBounds, layerId, height,
}: {
  field: MapField;
  polygon?: [number, number][];
  fallbackBounds?: [number, number, number, number];
  layerId: LayerId;
  height: number;
}) {
  const ly = layerOf(layerId);
  return (
    <div style={{ position: 'relative' }}>
      <FieldIndicatorMap
        // المفتاح على الحقل فقط: FieldIndicatorMap يبدّل طبقة بلاطات المؤشّر
        // داخليّاً عند تغيّر index (مفتاحها fieldId-index-date)، فلا داعي لهدم
        // الخريطة/الأساس بالكامل عند تبديل الطبقة (يطابق نمط SatellitePage).
        key={field.id}
        fieldId={field.id}
        index={layerId}
        date="latest"
        fieldPolygon={polygon}
        fallbackBounds={fallbackBounds}
        basemap="satellite"
        height={height}
      />
      <div style={{ position: 'absolute', insetInlineStart: 8, bottom: 8, zIndex: 500, pointerEvents: 'none' }}>
        <ColormapLegend cmap={ly.cmap} title={ly.label} lowLabel={ly.low} highLabel={ly.high} />
      </div>
    </div>
  );
}

export default function FieldMapCenter() {
  const fieldsQ = useFields();
  const devicesQ = useDevices();

  const fields: MapField[] = useMemo(() => {
    const raw = Array.isArray(fieldsQ.data?.fields) ? fieldsQ.data.fields : [];
    return raw.map((f: any) => ({
      id: String(f.field_id ?? f.id),
      name: f.name ?? f.field_code ?? f.field_id ?? 'حقل',
      lat: f.lat ?? f.centroid_lat ?? null,
      lon: f.lon ?? f.centroid_lon ?? null,
      geometry: f.geometry,
    }));
  }, [fieldsQ.data]);

  const [fieldId, setFieldId] = useState('');
  const [compare, setCompare] = useState(false);
  const [leftLayer, setLeftLayer] = useState<LayerId>('ndvi');
  const [rightLayer, setRightLayer] = useState<LayerId>('ndmi');

  // أوّل حقل افتراضيّاً (يفضّل ذا الهندسة) متى وصلت البيانات.
  useEffect(() => {
    if (fieldId || !fields.length) return;
    const withGeom = fields.find((f) => geomToPolygon(f.geometry)) ?? fields[0];
    setFieldId(withGeom.id);
  }, [fields, fieldId]);

  const field = fields.find((f) => f.id === fieldId) ?? fields[0];
  const polygon = field ? geomToPolygon(field.geometry) : undefined;
  const fallbackBounds: [number, number, number, number] | undefined =
    field && field.lat != null && field.lon != null
      ? [field.lon - 0.01, field.lat - 0.01, field.lon + 0.01, field.lat + 0.01]
      : undefined;

  // أجهزة الحقل المختار (نسبة لـfield_id) — مؤشّرات حالة لا إحداثيّات مزعومة.
  const allDevices = Array.isArray(devicesQ.data) ? devicesQ.data : [];
  const fieldDevices = field ? allDevices.filter((d) => d.field_id === field.id) : [];
  const onlineDevices = fieldDevices.filter((d) => d.online).length;

  return (
    <div dir="rtl" style={{ background: T.cream, minHeight: '100%', padding: 16 }}>
      <div
        style={{
          maxWidth: 420, margin: '0 auto', background: T.cream,
          borderRadius: 22, border: `1px solid ${T.line}`, overflow: 'hidden',
          boxShadow: '0 12px 40px rgba(44,26,14,.10)',
        }}
      >
        {/* ── Header ── */}
        <div style={{ background: T.brown, color: '#fff', padding: '18px 16px 22px' }}>
          <div className="flex items-center justify-between">
            <div>
              <div style={{ fontSize: 12, color: T.goldSoft }}>مركز الخرائط</div>
              <div style={{ fontSize: 18, fontWeight: 800 }}>طبقات الحقل</div>
            </div>
            <Pill tone="info" icon={<Layers style={{ width: 12, height: 12 }} />}>
              {LAYERS.length} طبقات
            </Pill>
          </div>
          <div style={{ fontSize: 11, color: '#D8C7B3', marginTop: 6 }}>
            بلاطات مؤشّر حقيقيّة من خدمة الراستر — فوق حدود الحقل
          </div>
        </div>

        <div style={{ padding: 14 }}>
          {/* ── اختيار الحقل + تبديل وضع المقارنة ── */}
          <Card pad={14} style={{ marginBottom: 10 }}>
            <SectionLabel
              action={<Badge tone={fieldsQ.isLoading ? 'neutral' : fieldsQ.isError ? 'danger' : 'ok'}>
                {fieldsQ.isLoading ? 'تحميل…' : fieldsQ.isError ? 'خطأ' : `${fields.length} حقل`}
              </Badge>}
            >
              الحقل
            </SectionLabel>

            {fieldsQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الحقول…</div>
            ) : fieldsQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الحقول.</div>
            ) : fields.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا حقول مُسجّلة.</div>
            ) : (
              <>
                <select
                  value={field?.id ?? ''}
                  onChange={(e) => setFieldId(e.target.value)}
                  style={{
                    width: '100%', padding: '9px 10px', borderRadius: 10,
                    border: `1px solid ${T.line}`, background: T.card, color: T.ink,
                    fontSize: 14, fontWeight: 600, marginBottom: 10,
                  }}
                >
                  {fields.map((f) => (
                    <option key={f.id} value={f.id}>{f.name}{geomToPolygon(f.geometry) ? '' : ' (بلا حدود)'}</option>
                  ))}
                </select>
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: 12, color: T.muted }}>وضع العرض</span>
                  <button
                    type="button"
                    onClick={() => setCompare((v) => !v)}
                    className="inline-flex items-center gap-1"
                    style={{
                      padding: '6px 12px', borderRadius: 999, border: 'none', cursor: 'pointer',
                      fontSize: 12, fontWeight: 700,
                      background: compare ? T.green : T.card2, color: compare ? '#fff' : T.ink,
                    }}
                  >
                    {compare ? <Columns2 style={{ width: 13, height: 13 }} /> : <Square style={{ width: 13, height: 13 }} />}
                    {compare ? 'مقارنة جنباً لجنب' : 'طبقة واحدة'}
                  </button>
                </div>
              </>
            )}
          </Card>

          {/* ── الخريطة / الخرائط ── */}
          {field && (polygon || fallbackBounds) ? (
            compare ? (
              <Card pad={12} style={{ marginBottom: 10 }}>
                <SectionLabel>مقارنة الطبقات</SectionLabel>
                <SideBySide
                  leftLabel={
                    <LayerSwitcher layers={LAYER_OPTS} active={leftLayer} onChange={setLeftLayer} />
                  }
                  rightLabel={
                    <LayerSwitcher layers={LAYER_OPTS} active={rightLayer} onChange={setRightLayer} />
                  }
                  left={<MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={leftLayer} height={220} />}
                  right={<MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={rightLayer} height={220} />}
                />
                <div style={{ fontSize: 11, color: T.muted, marginTop: 8 }}>
                  طبقتان حقيقيّتان لنفس الحقل والتاريخ (latest) — للموازنة البصريّة.
                </div>
              </Card>
            ) : (
              <Card pad={12} style={{ marginBottom: 10 }}>
                <div style={{ marginBottom: 10 }}>
                  <LayerSwitcher layers={LAYER_OPTS} active={leftLayer} onChange={setLeftLayer} />
                </div>
                <MapPanel field={field} polygon={polygon} fallbackBounds={fallbackBounds} layerId={leftLayer} height={320} />
                <div style={{ fontSize: 11, color: T.muted, marginTop: 8 }}>
                  {layerOf(leftLayer).hint} — طبقة <b>{layerOf(leftLayer).label}</b> فوق {field.name}.
                </div>
              </Card>
            )
          ) : field ? (
            <Card pad={14} style={{ marginBottom: 10 }}>
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>
                لا حدود ولا إحداثيّات لهذا الحقل — تعذّر عرض الخريطة. اختر حقلاً ذا هندسة.
              </div>
            </Card>
          ) : null}

          {/* ── أجهزة الحقل (مؤشّرات حالة — لا مواقع ملفّقة) ── */}
          <Card pad={14} style={{ marginBottom: 4 }}>
            <SectionLabel
              action={<Badge tone={fieldDevices.length ? (onlineDevices ? 'ok' : 'warn') : 'neutral'}>
                {fieldDevices.length ? `${onlineDevices}/${fieldDevices.length} متّصل` : '—'}
              </Badge>}
            >
              <span className="inline-flex items-center gap-1">
                <Cpu style={{ width: 13, height: 13 }} /> أجهزة الحقل
              </span>
            </SectionLabel>
            {devicesQ.isLoading ? (
              <div style={{ color: T.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل الأجهزة…</div>
            ) : devicesQ.isError ? (
              <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل الأجهزة.</div>
            ) : fieldDevices.length === 0 ? (
              <div style={{ color: T.muted, fontSize: 13, padding: '6px 0' }}>لا أجهزة منسوبة لهذا الحقل.</div>
            ) : (
              fieldDevices.map((d, i) => (
                <Row
                  key={d.device_id || i}
                  label={d.name || 'جهاز'}
                  value={<Pill tone={d.online ? 'ok' : 'neutral'}>{d.online ? 'متّصل' : 'غير متّصل'}</Pill>}
                  icon={
                    <MachineMarker
                      icon={<Cpu style={{ width: 14, height: 14, color: '#fff' }} />}
                      status={deviceMarkerStatus(d.online)}
                      alert={!d.online}
                      style={{ transform: 'scale(0.7)' }}
                    />
                  }
                />
              ))
            )}
          </Card>
        </div>
      </div>

      <p style={{ textAlign: 'center', color: T.muted, fontSize: 11, marginTop: 14 }}>
        مركز الخرائط الموحّد — بلاطات <code>/raster</code> الحقيقيّة فوق حدود <code>/fields</code>.
        مؤشّرات الأجهزة من <code>/devices</code> (حالة اتّصال، لا إحداثيّات). لا مواقع معدّات
        ملفّقة (فجوة موثّقة). الحالات صادقة.
      </p>
    </div>
  );
}
